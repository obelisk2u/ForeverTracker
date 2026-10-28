from __future__ import annotations

from collections import defaultdict

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.analytics.character_stats import compute_stats, load_run_facts, trend_buckets
from app.config import Settings
from app.identity.names import normalize_name, search_pattern
from app.models import (
    Character,
    CharacterIdentityEvidence,
    CharacterStats,
    Dungeon,
    DungeonRun,
    EquipmentSnapshot,
    LevelObservation,
    Namespace,
    ParticipantMetric,
    RunParticipant,
)
from app.models.base import utcnow
from app.schemas.api import (
    CharacterProfile,
    Companion,
    Freshness,
    GearItemOut,
    GearSnapshotOut,
    NameHistoryOut,
    PartyMemberOut,
    ProgressionPoint,
    ProgressionResponse,
    RunHistoryResponse,
    RunRow,
    RunSeriesPoint,
    SearchResponse,
)
from app.services.common import SLOT_NAMES, NotFound, Suppressed, dungeon_ref, metric_out, summaries, summarize
from app.services.visibility import character_visible, run_visible

HISTORY_METRICS = ("damage_done", "dps", "healing_done", "hps", "deaths", "interrupts")


def search(
    db: Session,
    settings: Settings,
    query: str,
    *,
    namespace: str | None = None,
    class_file: str | None = None,
    exact: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> SearchResponse:
    norm = normalize_name(query)
    if len(norm) < 2:
        raise ValueError("query must be at least 2 characters")
    pattern = search_pattern(query)
    if exact:
        name_cond = or_(Character.full_name_normalized == norm, Character.full_name_normalized.like(pattern + " %", escape="\\"))
    else:
        name_cond = Character.full_name_normalized.like(f"%{pattern}%", escape="\\")
    conds = [character_visible(settings), name_cond]
    if namespace:
        conds.append(Namespace.slug == namespace)
    if class_file:
        conds.append(Character.class_file == class_file.upper())
    rank = case(
        (Character.full_name_normalized == norm, 0),
        (Character.full_name_normalized.like(pattern + "%", escape="\\"), 1),
        else_=2,
    )
    base = (
        select(Character, Namespace, CharacterStats.runs_observed)
        .join(Namespace, Namespace.id == Character.namespace_id)
        .outerjoin(CharacterStats, CharacterStats.character_id == Character.id)
        .where(and_(*conds))
    )
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(
        base.order_by(rank, func.coalesce(CharacterStats.runs_observed, 0).desc(), Character.last_observed_at.desc(), Character.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    results = [summarize(c, ns, runs) for c, ns, runs in rows]
    counts: dict[str, int] = defaultdict(int)
    for r in results:
        counts[r.full_name.casefold()] += 1
    duplicates = sorted({r.full_name for r in results if counts[r.full_name.casefold()] > 1})
    return SearchResponse(
        query=query, exact=exact, total=total or 0, page=page, page_size=page_size, results=results, duplicate_names=duplicates
    )


def _load_character(db: Session, settings: Settings, public_id: str) -> tuple[Character, Namespace]:
    character = db.scalar(select(Character).where(Character.public_id == public_id))
    if character is None:
        raise NotFound(public_id)
    seen = set()
    while character.merged_into_id is not None and character.id not in seen:
        seen.add(character.id)
        character = db.get(Character, character.merged_into_id)
    if character.visibility != "public":
        raise Suppressed(public_id)
    if settings.environment == "production" and character.is_synthetic:
        raise NotFound(public_id)
    return character, db.get(Namespace, character.namespace_id)


def profile(db: Session, settings: Settings, public_id: str) -> CharacterProfile:
    character, namespace = _load_character(db, settings, public_id)
    stats_row = db.get(CharacterStats, character.id)
    stats = stats_row.stats if stats_row else compute_stats(load_run_facts(db, character.id), settings)
    snapshot = db.scalar(
        select(EquipmentSnapshot)
        .where(EquipmentSnapshot.character_id == character.id, EquipmentSnapshot.status != "unavailable")
        .order_by(EquipmentSnapshot.observed_at.desc())
        .limit(1)
    )
    gear = None
    if snapshot is not None:
        gear = GearSnapshotOut(
            observed_at=snapshot.observed_at,
            source=snapshot.source,
            status=snapshot.status,
            average_item_level=snapshot.average_item_level,
            level=snapshot.level,
            items=[
                GearItemOut(
                    slot=i["slot"],
                    slot_name=SLOT_NAMES.get(i["slot"], str(i["slot"])),
                    item_id=i["item_id"],
                    item_level=i.get("item_level"),
                    enchant_id=i.get("enchant_id"),
                    gem_ids=i.get("gem_ids") or [],
                    quality=i.get("quality"),
                    link=i.get("link"),
                )
                for i in sorted(snapshot.items, key=lambda i: i["slot"])
            ],
            talents_status=(snapshot.talents or {}).get("status"),
        )
    names = db.scalars(
        select(CharacterIdentityEvidence)
        .where(CharacterIdentityEvidence.character_id == character.id, CharacterIdentityEvidence.kind == "name")
        .order_by(CharacterIdentityEvidence.first_seen_at)
    ).all()
    notices = ["Observed history only: runs appear here when a ForeverTracker user was in the group."]
    if character.identity_confidence == "name_only":
        notices.append("Identity is based on the character name only; no character GUID has been observed.")
    if character.claim_status == "unclaimed":
        notices.append("This profile is not claimed. Being listed here does not identify the account owner.")
    if character.is_synthetic:
        notices.append("SYNTHETIC DEVELOPMENT DATA: this character and its history were generated by the simulator.")
    return CharacterProfile(
        character=summarize(character, namespace, stats_row.runs_observed if stats_row else None),
        canonical_path=f"/character/{namespace.slug}/{character.public_id}",
        realm_label=character.realm_label,
        claim_status=character.claim_status,
        stats=stats,
        latest_gear=gear,
        name_history=[
            NameHistoryOut(full_name=n.display_value or n.value, first_seen_at=n.first_seen_at, last_seen_at=n.last_seen_at)
            for n in names
        ],
        freshness=Freshness(
            last_observed_at=character.last_observed_at,
            stats_computed_at=stats_row.computed_at if stats_row else None,
            data_age_seconds=int((utcnow() - character.last_observed_at).total_seconds()),
        ),
        notices=notices,
    )


def run_history(
    db: Session,
    settings: Settings,
    public_id: str,
    *,
    page: int = 1,
    page_size: int = 25,
    dungeon: str | None = None,
    role: str | None = None,
    outcome: str | None = None,
) -> RunHistoryResponse:
    character, _ = _load_character(db, settings, public_id)
    conds = [RunParticipant.character_id == character.id, run_visible(settings)]
    if dungeon:
        conds.append(Dungeon.slug == dungeon)
    if role:
        conds.append(RunParticipant.role == role.upper())
    if outcome:
        conds.append(DungeonRun.outcome == outcome)
    base = (
        select(RunParticipant, DungeonRun, Dungeon)
        .join(DungeonRun, DungeonRun.id == RunParticipant.run_id)
        .join(Dungeon, Dungeon.id == DungeonRun.dungeon_id)
        .where(and_(*conds))
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(DungeonRun.started_at.desc(), DungeonRun.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    run_ids = [r.DungeonRun.id for r in rows]
    party: dict[int, list[RunParticipant]] = defaultdict(list)
    metrics: dict[int, dict] = defaultdict(dict)
    if run_ids:
        for p in db.scalars(select(RunParticipant).where(RunParticipant.run_id.in_(run_ids))):
            party[p.run_id].append(p)
        for m in db.scalars(
            select(ParticipantMetric).where(
                ParticipantMetric.run_id.in_(run_ids),
                ParticipantMetric.character_id == character.id,
                ParticipantMetric.metric.in_(HISTORY_METRICS),
            )
        ):
            metrics[m.run_id][m.metric] = metric_out(m)
    people = summaries(db, settings, [p.character_id for ps in party.values() for p in ps])
    items = [
        RunRow(
            run_id=run.public_id,
            dungeon=dungeon_ref(dg),
            started_at=run.started_at,
            ended_at=run.ended_at,
            duration_seconds=run.duration_seconds,
            outcome=run.outcome,
            completion_confidence=run.completion_confidence,
            role=me.role,
            level=me.level,
            presence_ratio=me.presence_ratio,
            party=[
                PartyMemberOut(character=people[p.character_id], role=p.role, class_file=p.class_file)
                for p in sorted(party[run.id], key=lambda p: (p.character_id != character.id, p.role or "", p.character_id))
                if p.character_id in people
            ],
            metrics=metrics[run.id],
            observers=run.contributor_count,
            match_status=run.match_status,
            is_synthetic=run.is_synthetic,
        )
        for me, run, dg in rows
    ]
    return RunHistoryResponse(total=total, page=page, page_size=page_size, items=items)


def companions(db: Session, settings: Settings, public_id: str, limit: int = 12) -> list[Companion]:
    character, _ = _load_character(db, settings, public_id)
    me = aliased(RunParticipant)
    other = aliased(RunParticipant)
    rows = db.execute(
        select(other.character_id, func.count().label("n"), func.max(DungeonRun.started_at).label("last"))
        .select_from(me)
        .join(other, and_(other.run_id == me.run_id, other.character_id != me.character_id))
        .join(DungeonRun, DungeonRun.id == me.run_id)
        .where(me.character_id == character.id, run_visible(settings))
        .group_by(other.character_id)
        .order_by(func.count().desc(), func.max(DungeonRun.started_at).desc())
        .limit(limit * 2)
    ).all()
    people = summaries(db, settings, [r.character_id for r in rows])
    out = []
    for r in rows:
        summary = people.get(r.character_id)
        if summary is None or getattr(summary, "hidden", False):
            continue
        out.append(Companion(character=summary, runs_together=r.n, last_together_at=r.last))
    return out[:limit]


def progression(db: Session, settings: Settings, public_id: str) -> ProgressionResponse:
    character, _ = _load_character(db, settings, public_id)
    levels = db.execute(
        select(LevelObservation.observed_at, LevelObservation.level, LevelObservation.source)
        .where(LevelObservation.character_id == character.id)
        .order_by(LevelObservation.observed_at)
    ).all()
    level_points: list[ProgressionPoint] = []
    for at, level, source in levels:
        if level_points and level_points[-1].value == level:
            continue  # keep the first observation of each level; no interpolation
        level_points.append(ProgressionPoint(at=at, value=level, source=source))
    ilvl = db.execute(
        select(EquipmentSnapshot.observed_at, EquipmentSnapshot.average_item_level, EquipmentSnapshot.source)
        .where(EquipmentSnapshot.character_id == character.id, EquipmentSnapshot.average_item_level.is_not(None))
        .order_by(EquipmentSnapshot.observed_at)
        .limit(500)
    ).all()
    facts = [f for f in load_run_facts(db, character.id) if not (settings.environment == "production" and f.run.is_synthetic)]
    runs = [
        RunSeriesPoint(
            run_id=f.run.public_id,
            started_at=f.run.started_at,
            dungeon=f.dungeon.name,
            deaths=metric_out(f.metrics["deaths"]) if "deaths" in f.metrics else None,
            dps=metric_out(f.metrics["dps"]) if "dps" in f.metrics else None,
            hps=metric_out(f.metrics["hps"]) if "hps" in f.metrics else None,
            interrupts=metric_out(f.metrics["interrupts"]) if "interrupts" in f.metrics else None,
        )
        for f in facts[-300:]
    ]
    return ProgressionResponse(
        level=level_points,
        item_level=[ProgressionPoint(at=at, value=v, source=src) for at, v, src in ilvl],
        runs=runs,
        weekly=trend_buckets(facts),
        note=(
            "Each point is an individual observation. Gaps are periods without observations and are not"
            " interpolated. Per-run values whose coverage is incomplete are marked and excluded from averages."
        ),
    )
