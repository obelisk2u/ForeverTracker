"""Applying accepted observations to the derived model, and removing them again."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.identity.namespaces import get_or_create_namespace
from app.identity.resolver import IdentityCache, IdentityConflict, Subject, resolve_character
from app.models import (
    DungeonRun,
    EquipmentSnapshot,
    LevelObservation,
    RawObservation,
    RunMatchCandidate,
    RunObservation,
)
from app.models.base import from_epoch
from app.reconciliation import cluster
from app.reconciliation.consolidate import rebuild_run
from app.reconciliation.dungeons import get_or_create_dungeon
from app.schemas.observations import CharacterSnapshotObservation, DungeonRunObservation


@dataclass
class ApplyContext:
    settings: Settings
    synthetic: bool
    dirty_characters: set[int] = field(default_factory=set)
    dirty_runs: set[int] = field(default_factory=set)


def apply_dungeon_run(
    db: Session, raw: RawObservation, obs: DungeonRunObservation, ctx: ApplyContext, preferred_run_id: int | None = None
) -> DungeonRun:
    ns = get_or_create_namespace(db, obs.namespace)
    raw.namespace_id = ns.id
    dungeon = get_or_create_dungeon(db, obs.instance, synthetic=ctx.synthetic)
    observed_at = from_epoch(obs.timing.started_at)

    identities: dict[str, int] = {}
    subjects = [
        Subject(
            guid=m.guid,
            name=m.name,
            surname=m.surname,
            identity_status=m.identity_status,
            class_file=m.class_file,
            race_file=m.race_file,
            level=m.level,
            realm_label=obs.realm_label if m.is_observer else None,
        )
        for m in obs.roster
    ]
    cache = IdentityCache.preload(db, ns.id, subjects, ctx.synthetic)
    for m, subject in zip(obs.roster, subjects):
        res = resolve_character(
            db, ns.id, subject, observed_at, synthetic=ctx.synthetic, cache=cache, contributor_id=raw.contributor_id,
            raw_observation_id=raw.id, rename_min_contributors=ctx.settings.identity_rename_min_contributors,
        )
        if res.character is not None:
            identities[m.ref] = res.character.id
        # A class contradiction leaves this roster entry unidentified (recorded as a claim for review).

    # Match against the current evidence of every observation this one could belong with (not against
    # derived rows, and not just against what arrived first): see app/reconciliation/cluster.py.
    seed = cluster.facts(
        raw, obs, identities, namespace_id=ns.id, dungeon_id=dungeon.id, run_id=None, preferred_run_id=preferred_run_id
    )
    extra = {preferred_run_id} if preferred_run_id is not None else set()
    neighbourhood = cluster.neighbourhood(db, seed, ctx.settings, extra_run_ids=extra)
    outcome = cluster.apply(db, neighbourhood, ctx.settings, extra_run_ids=extra)
    for run_id in sorted(outcome.touched_runs):
        ctx.dirty_characters |= rebuild_run(db, run_id, ctx.settings)
        ctx.dirty_runs.discard(run_id)
    return db.get(DungeonRun, outcome.run_of[raw.id])


def apply_snapshot(db: Session, raw: RawObservation, obs: CharacterSnapshotObservation, ctx: ApplyContext) -> int | None:
    ns = get_or_create_namespace(db, obs.namespace)
    raw.namespace_id = ns.id
    s = obs.subject
    observed_at = from_epoch(obs.observed_at)
    res = resolve_character(
        db,
        ns.id,
        Subject(
            guid=s.guid,
            name=s.name,
            surname=s.surname,
            identity_status=s.identity_status,
            class_file=s.class_file,
            race_file=s.race_file,
            level=s.level,
            realm_label=obs.realm_label if obs.source == "self" else None,
        ),
        observed_at,
        synthetic=ctx.synthetic,
        contributor_id=raw.contributor_id,
        raw_observation_id=raw.id,
        rename_min_contributors=ctx.settings.identity_rename_min_contributors,
    )
    if res.character is None:
        if res.claim is not None:
            # The snapshot is about a character whose class it contradicts: hold it for review.
            raise IdentityConflict("guid_class_conflict", s.guid or "", claim=res.claim)
        return None
    char_id = res.character.id
    if obs.equipment is not None or obs.talents is not None:
        db.add(
            EquipmentSnapshot(
                character_id=char_id,
                raw_observation_id=raw.id,
                observed_at=observed_at,
                source=obs.source,
                status=obs.equipment.status if obs.equipment else "unavailable",
                average_item_level=obs.equipment.average_item_level if obs.equipment else None,
                items=[i.model_dump(mode="json") for i in obs.equipment.items] if obs.equipment else [],
                talents=obs.talents.model_dump(mode="json") if obs.talents else None,
                level=s.level,
                is_synthetic=ctx.synthetic,
            )
        )
    if s.level is not None:
        db.add(
            LevelObservation(
                character_id=char_id, raw_observation_id=raw.id, observed_at=observed_at, level=s.level, source="snapshot"
            )
        )
    ctx.dirty_characters.add(char_id)
    return char_id


def detach(db: Session, raw: RawObservation, ctx: ApplyContext, *, rebuild: bool = True) -> int | None:
    """Remove everything derived from ``raw``. Returns the run it was linked to, if any."""
    link = db.scalar(select(RunObservation).where(RunObservation.raw_observation_id == raw.id))
    run_id = link.run_id if link else None
    if link is not None:
        db.delete(link)
    db.execute(delete(RunMatchCandidate).where(RunMatchCandidate.raw_observation_id == raw.id))
    for model in (EquipmentSnapshot, LevelObservation):
        ctx.dirty_characters |= set(db.scalars(select(model.character_id).where(model.raw_observation_id == raw.id)))
        db.execute(delete(model).where(model.raw_observation_id == raw.id))
    db.flush()
    if run_id is not None:
        if rebuild:
            ctx.dirty_characters |= rebuild_run(db, run_id, ctx.settings)
        else:
            ctx.dirty_runs.add(run_id)
    return run_id
