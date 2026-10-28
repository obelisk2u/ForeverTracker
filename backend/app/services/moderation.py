"""Administrative actions. Every action is written to ``audit_log``.

Invalidation never deletes raw observations: their status becomes ``invalidated``, their
derived contributions are removed, and every affected run and character is recomputed.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.character_stats import recompute_many
from app.config import Settings
from app.ingestion.apply import ApplyContext, apply_dungeon_run, apply_snapshot, detach
from app.models import AuditLog, Character, CharacterStats, Contributor, DataReport, DungeonRun, RawObservation, UploadBatch
from app.models.base import utcnow
from app.reconciliation.consolidate import rebuild_run
from app.schemas.observations import CharacterSnapshotObservation, DungeonRunObservation, observation_adapter
from app.services.common import NotFound


def _audit(db: Session, actor: str, action: str, target_type: str, target_id: Any, **details: Any) -> None:
    db.add(AuditLog(actor=actor, action=action, target_type=target_type, target_id=str(target_id), details=details))


def _finish(db: Session, ctx: ApplyContext) -> dict[str, int]:
    for run_id in sorted(ctx.dirty_runs):
        ctx.dirty_characters |= rebuild_run(db, run_id, ctx.settings)
    recompute_many(db, ctx.dirty_characters, ctx.settings)
    db.flush()
    return {"runs_recomputed": len(ctx.dirty_runs), "characters_recomputed": len(ctx.dirty_characters)}


def invalidate_observations(db: Session, settings: Settings, raws: list[RawObservation], reason: str, actor: str) -> dict:
    ctx = ApplyContext(settings=settings, synthetic=False)
    changed = 0
    for raw in raws:
        if raw.status == "invalidated":
            continue
        if raw.status == "accepted":
            detach(db, raw, ctx, rebuild=False)
        raw.status = "invalidated"
        raw.quarantine_reasons = [*raw.quarantine_reasons, f"invalidated:{reason}"]
        changed += 1
    summary = _finish(db, ctx)
    return {"invalidated": changed, **summary}


def invalidate_observation(db: Session, settings: Settings, raw_id: int, reason: str, actor: str) -> dict:
    raw = db.get(RawObservation, raw_id)
    if raw is None:
        raise NotFound(raw_id)
    result = invalidate_observations(db, settings, [raw], reason, actor)
    _audit(db, actor, "invalidate_observation", "raw_observation", raw_id, reason=reason, **result)
    return result


def invalidate_batch(db: Session, settings: Settings, upload_id: str, reason: str, actor: str) -> dict:
    upload = db.get(UploadBatch, uuid.UUID(upload_id))
    if upload is None:
        raise NotFound(upload_id)
    raws = list(db.scalars(select(RawObservation).where(RawObservation.batch_id == upload.id)))
    result = invalidate_observations(db, settings, raws, reason, actor)
    _audit(db, actor, "invalidate_batch", "upload_batch", upload_id, reason=reason, **result)
    return result


def set_contributor_status(
    db: Session, settings: Settings, contributor_id: int, status: str, reason: str, actor: str, *, invalidate_all: bool = False
) -> dict:
    contributor = db.get(Contributor, contributor_id)
    if contributor is None:
        raise NotFound(contributor_id)
    if status not in ("active", "flagged", "banned"):
        raise ValueError("status must be active, flagged or banned")
    contributor.status = status
    contributor.status_reason = reason
    result: dict = {"status": status}
    if invalidate_all:
        raws = list(db.scalars(select(RawObservation).where(RawObservation.contributor_id == contributor_id)))
        result |= invalidate_observations(db, settings, raws, reason, actor)
    _audit(db, actor, "set_contributor_status", "contributor", contributor_id, reason=reason, **result)
    return result


def release_quarantined(db: Session, settings: Settings, raw_id: int, actor: str) -> dict:
    raw = db.get(RawObservation, raw_id)
    if raw is None:
        raise NotFound(raw_id)
    if raw.status != "quarantined":
        raise ValueError(f"observation is {raw.status}, not quarantined")
    newer = db.scalar(
        select(RawObservation.id).where(
            RawObservation.contributor_id == raw.contributor_id,
            RawObservation.observation_key == raw.observation_key,
            RawObservation.revision > raw.revision,
            RawObservation.status == "accepted",
        )
    )
    if newer is not None:
        raise ValueError("a newer revision of this observation is already accepted")
    obs = observation_adapter.validate_python(raw.payload)
    ctx = ApplyContext(settings=settings, synthetic=raw.is_synthetic)
    raw.status = "accepted"
    db.flush()
    if isinstance(obs, DungeonRunObservation):
        apply_dungeon_run(db, raw, obs, ctx)
    elif isinstance(obs, CharacterSnapshotObservation):
        apply_snapshot(db, raw, obs, ctx)
    summary = _finish(db, ctx)
    _audit(db, actor, "release_quarantined", "raw_observation", raw_id, **summary)
    return summary


def set_character_visibility(db: Session, settings: Settings, public_id: str, visibility: str, note: str, actor: str) -> dict:
    character = db.scalar(select(Character).where(Character.public_id == public_id))
    if character is None:
        raise NotFound(public_id)
    if visibility not in ("public", "suppressed"):
        raise ValueError("visibility must be public or suppressed")
    character.visibility = visibility
    _audit(db, actor, "set_character_visibility", "character", public_id, visibility=visibility, note=note)
    return {"character": public_id, "visibility": visibility}


def resolve_report(db: Session, report_public_id: str, status: str, note: str, actor: str) -> dict:
    report = db.scalar(select(DataReport).where(DataReport.public_id == report_public_id))
    if report is None:
        raise NotFound(report_public_id)
    report.status = status
    report.resolution_note = note
    report.resolved_at = utcnow()
    _audit(db, actor, "resolve_report", "data_report", report_public_id, status=status)
    return {"report": report_public_id, "status": status}


def rebuild_all(db: Session, settings: Settings) -> dict:
    """Recompute every canonical run and every character's statistics from linked raw observations."""
    ctx = ApplyContext(settings=settings, synthetic=False)
    for run_id in db.scalars(select(DungeonRun.id).order_by(DungeonRun.id)):
        ctx.dirty_characters |= rebuild_run(db, run_id, settings)
    ctx.dirty_characters |= set(db.scalars(select(CharacterStats.character_id)))
    recompute_many(db, ctx.dirty_characters, settings)
    db.flush()
    return {"characters_recomputed": len(ctx.dirty_characters)}
