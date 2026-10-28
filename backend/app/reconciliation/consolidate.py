"""Rebuild a canonical run from every accepted observation linked to it.

The rebuild is deterministic and idempotent: running it twice yields the same rows. It is
called after every link/unlink, after invalidation, and by ``python -m app.cli rebuild``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import delete, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.analytics.definitions import COMPLETE_COVERAGE_RATIO, METRIC_VERSION, METRICS
from app.config import Settings
from app.models import (
    Character,
    Dungeon,
    DungeonRun,
    LevelObservation,
    MetricObservation,
    ParticipantMetric,
    RawObservation,
    RunDeath,
    RunEncounter,
    RunMatchCandidate,
    RunObservation,
    RunParticipant,
)
from app.models.base import from_epoch
from app.reconciliation.matcher import member_intervals
from app.reconciliation.metrics import (
    Candidate,
    Resolved,
    derive_rate,
    interval_union_seconds,
    intersect_union_seconds,
    meter_candidates,
    resolve,
)
from app.schemas.observations import DungeonRunObservation

ENCOUNTER_CLUSTER_SECONDS = 120


@dataclass
class LinkedObservation:
    raw: RawObservation
    obs: DungeonRunObservation
    identities: dict[str, int]

    @property
    def observer_ref(self) -> str | None:
        return next((m.ref for m in self.obs.roster if m.is_observer), None)


@dataclass
class _ParticipantAcc:
    intervals: list[tuple[datetime, datetime]] = field(default_factory=list)
    roles: Counter = field(default_factory=Counter)
    levels: list[int] = field(default_factory=list)
    classes: Counter = field(default_factory=Counter)
    contributors: set[int] = field(default_factory=set)
    was_observer: bool = False


def _clamp(interval: tuple[datetime, datetime], lo: datetime, hi: datetime) -> tuple[datetime, datetime] | None:
    s, e = max(interval[0], lo), min(interval[1], hi)
    return (s, e) if e > s else None


def _load_links(db: Session, run_id: int) -> list[LinkedObservation]:
    rows = db.execute(
        select(RunObservation, RawObservation)
        .join(RawObservation, RawObservation.id == RunObservation.raw_observation_id)
        .where(RunObservation.run_id == run_id, RawObservation.status == "accepted")
        .order_by(RawObservation.id)
    ).all()
    return [
        LinkedObservation(
            raw=raw,
            obs=DungeonRunObservation.model_validate(raw.payload),
            identities={k: int(v) for k, v in (link.match_evidence.get("identities") or {}).items()},
        )
        for link, raw in rows
    ]


def _outcome(links: list[LinkedObservation], dungeon: Dungeon, encounters: list[RunEncounter]) -> tuple[str, str, list]:
    evidence: list[dict] = []
    for link in links:
        if link.obs.completion.status == "verified":
            for ev in link.obs.completion.evidence:
                evidence.append({"kind": ev.kind, "at": ev.at, "observation": link.raw.id})
    if evidence:
        return "completed", "verified", evidence
    if dungeon.final_encounter_id is not None:
        kills = [e for e in encounters if e.encounter_id == dungeon.final_encounter_id and e.success]
        if kills:
            return "completed", "probable", [{"kind": "final_encounter_killed", "encounter_id": dungeon.final_encounter_id}]
    states = [link.obs.state for link in links]
    if "abandoned" in states:
        return "abandoned", "none", [{"kind": "abandon_vote_passed"}]
    if all(s == "in_progress" for s in states):
        return "in_progress", "none", []
    finished = [s for s in states if s != "in_progress"]
    if finished and all(s == "disconnected" for s in finished):
        return "disconnected", "none", []
    if finished and all(s in ("left", "disconnected") for s in finished):
        return "left", "none", []
    return "unknown", "none", []


def _bulk_insert(db: Session, model, objects: list) -> None:
    """Insert transient ORM objects as one multi-row INSERT ... VALUES per chunk.

    (A list passed to session.execute(insert(...), rows) goes through the driver's
    executemany, which costs one round trip per row with psycopg 3.)
    """
    if not objects:
        return
    table = model.__table__
    rows = [{k: v for k, v in o.__dict__.items() if k in table.c and k != "id"} for o in objects]
    keys = set().union(*rows)
    for row in rows:
        for key in keys - row.keys():
            default = table.c[key].default
            row[key] = default.arg if default is not None and not callable(default.arg) else None
    for start in range(0, len(rows), 1000):
        db.execute(insert(table).values(rows[start : start + 1000]))


def rebuild_run(db: Session, run_id: int, settings: Settings) -> set[int]:
    """Recompute everything derived for one run. Returns the IDs of affected characters."""
    with db.no_autoflush:
        return _rebuild_run(db, run_id, settings)


def _rebuild_run(db: Session, run_id: int, settings: Settings) -> set[int]:
    run = db.get(DungeonRun, run_id)
    if run is None:
        return set()
    previous_chars = set(db.scalars(select(RunParticipant.character_id).where(RunParticipant.run_id == run_id)))
    links = _load_links(db, run_id)

    for model in (ParticipantMetric, MetricObservation, RunDeath, RunEncounter, RunParticipant):
        db.execute(delete(model).where(model.run_id == run_id))

    if not links:
        db.delete(run)
        db.flush()
        return previous_chars

    dungeon = db.get(Dungeon, run.dungeon_id)
    starts = [l.obs.timing.started_at for l in links]
    ended = [l.obs.timing.ended_at for l in links if l.obs.timing.ended_at is not None and l.obs.state != "in_progress"]
    run.started_at = from_epoch(min(starts))
    run.ended_at = from_epoch(max(ended)) if ended else None
    run.last_observed_at = from_epoch(max(l.obs.timing.last_updated_at for l in links))
    run.duration_seconds = int((run.ended_at - run.started_at).total_seconds()) if run.ended_at else None
    window_end = run.ended_at or run.last_observed_at
    window_seconds = max(1.0, (window_end - run.started_at).total_seconds())

    guids = {l.obs.party_guid for l in links if l.obs.party_guid}
    run.party_guid = next(iter(guids)) if len(guids) == 1 else None
    difficulties = Counter(l.obs.instance.difficulty_id for l in links if l.obs.instance.difficulty_id is not None)
    run.difficulty_id = difficulties.most_common(1)[0][0] if difficulties else None
    names = Counter(l.obs.instance.difficulty_name for l in links if l.obs.instance.difficulty_name)
    run.difficulty_name = names.most_common(1)[0][0] if names else None

    # Participants.
    acc: dict[int, _ParticipantAcc] = defaultdict(_ParticipantAcc)
    unidentified = 0
    observer_tracking: dict[int, list[tuple[datetime, datetime]]] = defaultdict(list)  # contributor -> intervals
    observer_presence: dict[int, list[tuple[datetime, datetime]]] = {}  # raw id -> intervals
    for link in links:
        for member in link.obs.roster:
            intervals = [c for i in member_intervals(link.obs, member.ref) if (c := _clamp(i, run.started_at, window_end))]
            if member.is_observer:
                observer_presence[link.raw.id] = intervals
                if link.obs.collection.get("deaths_unit_state") == "active":
                    observer_tracking[link.raw.contributor_id].extend(intervals)
            char_id = link.identities.get(member.ref)
            if char_id is None:
                unidentified += 1
                continue
            a = acc[char_id]
            a.intervals.extend(intervals)
            if member.role and member.role != "NONE":
                a.roles[member.role] += 1
            if member.level is not None:
                a.levels.append(member.level)
            if member.class_file:
                a.classes[member.class_file] += 1
            a.contributors.add(link.raw.contributor_id)
            a.was_observer = a.was_observer or member.is_observer

    characters = {c.id: c for c in db.scalars(select(Character).where(Character.id.in_(list(acc))))}
    participants: dict[int, RunParticipant] = {}
    for char_id, a in acc.items():
        presence = interval_union_seconds(a.intervals)
        character = characters.get(char_id)
        p = RunParticipant(
            run_id=run.id,
            character_id=char_id,
            role=a.roles.most_common(1)[0][0] if a.roles else None,
            class_file=a.classes.most_common(1)[0][0] if a.classes else (character.class_file if character else None),
            level=max(a.levels) if a.levels else None,
            joined_at=min(i[0] for i in a.intervals) if a.intervals else None,
            left_at=max(i[1] for i in a.intervals) if a.intervals else None,
            presence_seconds=int(presence),
            presence_ratio=round(min(1.0, presence / window_seconds), 4),
            observer_count=len(a.contributors),
            was_observer=a.was_observer,
            identity_confidence=character.identity_confidence if character else "name_only",
        )
        participants[char_id] = p

    # Encounters: cluster the same boss pull reported by several observers.
    pulls: list[tuple[int, datetime, datetime | None, bool | None, str | None, int]] = []
    for link in links:
        for enc in link.obs.encounters:
            pulls.append(
                (enc.encounter_id, from_epoch(enc.started_at), from_epoch(enc.ended_at), enc.success, enc.name, link.raw.contributor_id)
            )
    pulls.sort(key=lambda p: (p[0], p[1]))
    encounters: list[RunEncounter] = []
    for enc_id, start, end, success, name, contributor in pulls:
        current = encounters[-1] if encounters else None
        if (
            current is not None
            and current.encounter_id == enc_id
            and abs((start - current.started_at).total_seconds()) <= ENCOUNTER_CLUSTER_SECONDS
        ):
            current.observation_count += 1
            if end and (current.ended_at is None or end > current.ended_at):
                current.ended_at = end
            if success is not None:
                if current.success is None and not current.conflict:
                    current.success = success
                elif current.success is not None and current.success != success:
                    current.success, current.conflict = None, True
            continue
        encounters.append(
            RunEncounter(
                run_id=run.id,
                encounter_id=enc_id,
                name=name,
                started_at=start,
                ended_at=end,
                success=success,
                observation_count=1,
                conflict=False,
            )
        )
    encounters.sort(key=lambda e: e.started_at)
    _learn_encounters(dungeon, encounters)

    # Deaths: the same death seen by several observers (or sources) is counted once.
    window = timedelta(seconds=settings.death_dedupe_window_seconds)
    events: dict[int, list[tuple[datetime, str, int, int | None]]] = defaultdict(list)
    for link in links:
        for d in link.obs.deaths:
            char_id = link.identities.get(d.unit_ref)
            if char_id is not None:
                events[char_id].append((from_epoch(d.at), d.source, link.raw.contributor_id, d.encounter_id))
    death_counts: dict[int, int] = {}
    death_rows: list[RunDeath] = []
    for char_id, evs in events.items():
        evs.sort()
        clusters: list[list[tuple[datetime, str, int, int | None]]] = []
        for ev in evs:
            if clusters and ev[0] - clusters[-1][-1][0] <= window:
                clusters[-1].append(ev)
            else:
                clusters.append([ev])
        death_counts[char_id] = len(clusters)
        for cluster in clusters:
            death_rows.append(
                RunDeath(
                    run_id=run.id,
                    character_id=char_id,
                    occurred_at=cluster[0][0],
                    encounter_id=next((c[3] for c in cluster if c[3] is not None), None),
                    sources=sorted({f"{c[1]}" for c in cluster}),
                    observation_count=len({c[2] for c in cluster}),
                )
            )

    run.outcome, run.completion_confidence, run.outcome_evidence = _outcome(links, dungeon, encounters)

    # Metric candidates.
    candidates: list[Candidate] = []
    for link in links:
        presence = observer_presence.get(link.raw.id, [])
        coverage_ratio = min(1.0, interval_union_seconds(presence) / window_seconds)
        candidates.extend(
            meter_candidates(
                link.obs,
                raw_observation_id=link.raw.id,
                contributor_id=link.raw.contributor_id,
                ref_to_char=link.identities,
                observer_coverage_ratio=coverage_ratio,
                collected_at=from_epoch(link.obs.timing.last_updated_at),
                death_interpretation=settings.meter_death_interpretation,
            )
        )
    tracked_all = [i for ivs in observer_tracking.values() for i in ivs]
    if tracked_all:
        latest_link = max(links, key=lambda l: l.obs.timing.last_updated_at)
        for char_id, a in acc.items():
            own = interval_union_seconds(a.intervals)
            covered = intersect_union_seconds(a.intervals, tracked_all)
            ratio = covered / own if own > 0 else 0.0
            complete = ratio >= COMPLETE_COVERAGE_RATIO
            trackers = frozenset(
                contributor
                for contributor, ivs in observer_tracking.items()
                if intersect_union_seconds(a.intervals, ivs) > 0
            )
            candidates.append(
                Candidate(
                    character_id=char_id,
                    metric="deaths",
                    value=float(death_counts.get(char_id, 0)),
                    source="death_events",
                    status="observed" if complete else "incomplete",
                    coverage="complete_session" if complete else "partial_session",
                    coverage_ratio=round(ratio, 4),
                    combat_seconds=None,
                    contributor_ids=trackers,
                    raw_observation_id=latest_link.raw.id,
                    collected_at=from_epoch(latest_link.obs.timing.last_updated_at),
                    details={"trackers": len(trackers)},
                )
            )

    metric_rows: list[MetricObservation] = []
    for c in candidates:
        metric_rows.append(
            MetricObservation(
                run_id=run.id,
                character_id=c.character_id,
                raw_observation_id=c.raw_observation_id,
                contributor_id=min(c.contributor_ids),
                metric=c.metric,
                value=c.value,
                unit=c.unit,
                source=c.source,
                status=c.status,
                coverage=c.coverage,
                coverage_ratio=c.coverage_ratio,
                combat_seconds=c.combat_seconds,
                collected_at=c.collected_at,
                details={**c.details, "contributors": len(c.contributor_ids)},
            )
        )

    grouped: dict[tuple[int, str], list[Candidate]] = defaultdict(list)
    for c in candidates:
        grouped[(c.character_id, c.metric)].append(c)
    resolved: list[Resolved] = []
    for (char_id, metric), cands in grouped.items():
        r = resolve(cands, settings.metric_agreement_tolerance)
        if r is None:
            continue
        resolved.append(r)
        if metric in ("damage_done", "healing_done"):
            rate = derive_rate(r, "dps" if metric == "damage_done" else "hps")
            if rate is not None:
                resolved.append(rate)

    resolved_rows: list[ParticipantMetric] = []
    for r in resolved:
        resolved_rows.append(
            ParticipantMetric(
                run_id=run.id,
                character_id=r.character_id,
                metric=r.metric,
                value=r.value,
                unit="per_second" if r.derived else _unit(r.metric),
                source=r.source,
                status=r.status,
                coverage=r.coverage,
                resolution=r.resolution,
                confidence=r.confidence,
                candidate_count=r.candidate_count,
                contributor_count=r.contributor_count,
                derived=r.derived,
                metric_version=METRIC_VERSION,
                conflict=r.conflict,
            )
        )

    # Completeness and coverage summaries.
    by_char_metric = {(r.character_id, r.metric): r for r in resolved}
    for char_id, p in participants.items():
        deaths = by_char_metric.get((char_id, "deaths"))
        dmg = by_char_metric.get((char_id, "damage_done"))
        p.completeness = {
            "identity": "guid" if p.identity_confidence == "guid_confirmed" else "name",
            "deaths": deaths.coverage if deaths and deaths.value is not None else "none",
            "meter": dmg.coverage if dmg and dmg.value is not None else "none",
            "presence_ratio": p.presence_ratio,
        }

    contributors = {l.raw.contributor_id for l in links}
    run.observation_count = len(links)
    run.contributor_count = len(contributors)
    unresolved = db.scalar(
        select(RunMatchCandidate.id).where(
            RunMatchCandidate.raw_observation_id.in_([l.raw.id for l in links]), RunMatchCandidate.status == "unresolved"
        )
    )
    run.match_status = "unresolved" if unresolved else ("reconciled" if len(links) > 1 else "single")
    run.is_synthetic = any(l.raw.is_synthetic for l in links)
    run.coverage = {
        "observers": len(contributors),
        "participants_identified": len(participants),
        "roster_entries_unidentified": unidentified,
        "meter": _coverage_summary([by_char_metric.get((c, "damage_done")) for c in participants]),
        "deaths": _coverage_summary([by_char_metric.get((c, "deaths")) for c in participants]),
        "full_run_observed": any(
            interval_union_seconds(observer_presence.get(l.raw.id, [])) / window_seconds >= COMPLETE_COVERAGE_RATIO
            for l in links
        ),
        "party_guid_conflict": len(guids) > 1,
    }

    _bulk_insert(db, RunParticipant, list(participants.values()))
    _bulk_insert(db, RunEncounter, encounters)
    _bulk_insert(db, RunDeath, death_rows)
    _bulk_insert(db, MetricObservation, metric_rows)
    _bulk_insert(db, ParticipantMetric, resolved_rows)
    _record_levels(db, links)
    db.flush()
    return previous_chars | set(participants)


def _unit(metric: str) -> str:
    return METRICS[metric].unit


def _coverage_summary(values: list[Resolved | None]) -> str:
    if not values:
        return "none"
    if all(v is not None and v.value is not None and v.coverage == "complete_session" for v in values):
        return "complete"
    if any(v is not None and v.value is not None for v in values):
        return "partial"
    return "none"


def _learn_encounters(dungeon: Dungeon, encounters: list[RunEncounter]) -> None:
    known = {e["encounter_id"] for e in dungeon.encounters}
    added = [{"encounter_id": e.encounter_id, "name": e.name} for e in encounters if e.encounter_id not in known]
    if added:
        unique = {a["encounter_id"]: a for a in added}
        dungeon.encounters = [*dungeon.encounters, *unique.values()]


def _record_levels(db: Session, links: list[LinkedObservation]) -> None:
    rows = []
    for link in links:
        observed_at = from_epoch(link.obs.timing.started_at)
        for member in link.obs.roster:
            char_id = link.identities.get(member.ref)
            if char_id is not None and member.level is not None:
                rows.append(
                    {
                        "character_id": char_id,
                        "raw_observation_id": link.raw.id,
                        "observed_at": observed_at,
                        "level": member.level,
                        "source": "run",
                    }
                )
    if rows:
        db.execute(pg_insert(LevelObservation).values(rows).on_conflict_do_nothing())
