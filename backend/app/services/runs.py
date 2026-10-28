from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.wipes import DeathPoint, EncounterPoint, Presence, detect_wipes
from app.config import Settings
from app.models import (
    Character,
    Dungeon,
    DungeonRun,
    MetricObservation,
    Namespace,
    ParticipantMetric,
    RawObservation,
    RunDeath,
    RunEncounter,
    RunObservation,
    RunParticipant,
    UploadBatch,
)
from app.schemas.api import (
    DeathOut,
    EncounterOut,
    MetricCandidateOut,
    NamespaceOut,
    ParticipantOut,
    RunDetail,
    SourceOut,
    WipeOut,
)
from app.services.common import NotFound, dungeon_ref, metric_out, observer_labels, summaries
from app.services.visibility import hide_synthetic

ROLE_ORDER = {"TANK": 0, "HEALER": 1, "DAMAGER": 2}


def run_detail(db: Session, settings: Settings, public_id: str) -> RunDetail:
    run = db.scalar(select(DungeonRun).where(DungeonRun.public_id == public_id))
    if run is None or run.quarantined or (hide_synthetic(settings) and run.is_synthetic):
        raise NotFound(public_id)
    while run.merged_into_id is not None:
        run = db.get(DungeonRun, run.merged_into_id)
    dungeon = db.get(Dungeon, run.dungeon_id)
    namespace = db.get(Namespace, run.namespace_id)

    links = db.execute(
        select(RunObservation, RawObservation, UploadBatch)
        .join(RawObservation, RawObservation.id == RunObservation.raw_observation_id)
        .join(UploadBatch, UploadBatch.id == RawObservation.batch_id)
        .where(RunObservation.run_id == run.id, RawObservation.status == "accepted")
        .order_by(RunObservation.linked_at, RunObservation.id)
    ).all()
    labels = observer_labels([raw.contributor_id for _, raw, _ in links])

    participants = list(db.scalars(select(RunParticipant).where(RunParticipant.run_id == run.id)))
    people = summaries(db, settings, [p.character_id for p in participants])
    public_ids = dict(
        db.execute(select(Character.id, Character.public_id).where(Character.id.in_([p.character_id for p in participants]))).all()
    )
    metrics: dict[int, dict] = defaultdict(dict)
    conflicts: dict[int, dict] = defaultdict(dict)
    for m in db.scalars(select(ParticipantMetric).where(ParticipantMetric.run_id == run.id)):
        metrics[m.character_id][m.metric] = metric_out(m)
        if m.conflict:
            conflicts[m.character_id][m.metric] = m.conflict
    candidates: dict[int, dict[str, list[MetricCandidateOut]]] = defaultdict(lambda: defaultdict(list))
    for c in db.scalars(select(MetricObservation).where(MetricObservation.run_id == run.id).order_by(MetricObservation.id)):
        candidates[c.character_id][c.metric].append(
            MetricCandidateOut(
                observer=labels.get(c.contributor_id, "Observer ?") if c.source != "death_events" else "All observers (deduplicated)",
                value=c.value,
                source=c.source,
                status=c.status,
                coverage=c.coverage,
                coverage_ratio=c.coverage_ratio,
                collected_at=c.collected_at,
            )
        )
    hidden = {p.character_id for p in participants if getattr(people.get(p.character_id), "hidden", False)}

    encounters = list(db.scalars(select(RunEncounter).where(RunEncounter.run_id == run.id).order_by(RunEncounter.started_at)))
    deaths = list(db.scalars(select(RunDeath).where(RunDeath.run_id == run.id).order_by(RunDeath.occurred_at)))
    wipes = detect_wipes(
        [Presence(p.character_id, p.joined_at, p.left_at) for p in participants],
        [DeathPoint(d.character_id, d.occurred_at) for d in deaths],
        [EncounterPoint(e.encounter_id, e.started_at, e.ended_at, e.success) for e in encounters],
        death_coverage=run.coverage.get("deaths", "none"),
    )

    sources = []
    for _, raw, upload in links:
        payload = raw.payload
        timing = payload["timing"]
        sources.append(
            SourceOut(
                observer=labels[raw.contributor_id],
                state=payload["state"],
                revision=raw.revision,
                started_at=raw.observed_start,
                ended_at=raw.observed_end if timing.get("ended_at") is not None else None,
                meter_status=(payload.get("meter") or {}).get("status"),
                collectors=payload.get("collection") or {},
                client_build=payload.get("client_build"),
                uploaded_at=upload.received_at,
            )
        )

    ordered = sorted(participants, key=lambda p: (ROLE_ORDER.get(p.role or "", 3), -(p.presence_ratio or 0), p.character_id))
    return RunDetail(
        run_id=run.public_id,
        dungeon=dungeon_ref(dungeon),
        namespace=NamespaceOut(slug=namespace.slug, region=namespace.region, ruleset=namespace.ruleset, display_name=namespace.display_name),
        difficulty_id=run.difficulty_id,
        difficulty_name=run.difficulty_name,
        started_at=run.started_at,
        ended_at=run.ended_at,
        last_observed_at=run.last_observed_at,
        duration_seconds=run.duration_seconds,
        outcome=run.outcome,
        completion_confidence=run.completion_confidence,
        outcome_evidence=[{k: v for k, v in e.items() if k != "observation"} for e in run.outcome_evidence],
        match_status=run.match_status,
        observation_count=run.observation_count,
        contributor_count=run.contributor_count,
        coverage=run.coverage,
        participants=[
            ParticipantOut(
                character=people[p.character_id],
                role=p.role,
                class_file=p.class_file,
                level=p.level,
                joined_at=p.joined_at,
                left_at=p.left_at,
                presence_ratio=p.presence_ratio,
                observed_by=p.observer_count,
                was_observer=p.was_observer,
                completeness=p.completeness,
                metrics={} if p.character_id in hidden else metrics[p.character_id],
                candidates={} if p.character_id in hidden else {k: v for k, v in candidates[p.character_id].items()},
                conflicts={} if p.character_id in hidden else conflicts[p.character_id],
            )
            for p in ordered
            if p.character_id in people
        ],
        encounters=[
            EncounterOut(
                encounter_id=e.encounter_id,
                name=e.name,
                started_at=e.started_at,
                ended_at=e.ended_at,
                success=e.success,
                observed_by=e.observation_count,
                conflict=e.conflict,
            )
            for e in encounters
        ],
        deaths=[
            DeathOut(
                character_id=None if d.character_id in hidden else public_ids.get(d.character_id),
                occurred_at=d.occurred_at,
                encounter_id=d.encounter_id,
                sources=d.sources,
                observed_by=d.observation_count,
            )
            for d in deaths
        ],
        wipes=[WipeOut(at=w.at, kind=w.kind, inferred=w.inferred, encounter_id=w.encounter_id, detail=w.detail) for w in wipes],
        sources=sources,
        is_synthetic=run.is_synthetic,
    )
