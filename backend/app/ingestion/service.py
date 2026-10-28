"""The ingestion pipeline: untrusted batch in, raw observations stored, derived model updated.

Guarantees:

* **Idempotent.** Re-sending a batch returns the original result. Re-sending an observation
  revision is a no-op (unique ``(contributor, observation_key, revision)``).
* **Revision-aware.** A newer revision of an observation (e.g. the final version of a run that
  was first saved by ``/reload`` while in progress) supersedes the older one. Older revisions
  arriving late are stored as ``superseded`` and never applied.
* **Failure-isolated.** Each observation is applied in its own savepoint. One bad record does
  not reject the batch.
* **Serialised.** Batches are applied under a transaction-scoped advisory lock, so two uploads
  of the same run cannot race into two canonical runs.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from forevertracker_sv.export import canonical_json, observations_digest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.analytics.character_stats import recompute_many
from app.config import Settings
from app.identity.resolver import IdentityConflict
from app.ingestion.apply import ApplyContext, apply_dungeon_run, apply_snapshot, detach
from app.ingestion.contributors import get_or_create_contributor
from app.integrity.sanity import check_observation
from app.models import RawObservation, UploadBatch
from app.models.base import from_epoch, utcnow
from app.reconciliation.consolidate import rebuild_run
from app.schemas.observations import (
    CharacterSnapshotObservation,
    DungeonRunObservation,
    ObservationBatchEnvelope,
    observation_adapter,
)

INGEST_LOCK_KEY = 7_340_001
MAX_RECORDED_ERRORS = 50


class IngestError(Exception):
    def __init__(self, status_code: int, code: str, detail: str):
        self.status_code = status_code
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass
class ObservationResult:
    index: int
    observation_id: str | None
    revision: int | None
    type: str | None
    status: str  # accepted | duplicate | stale | quarantined | rejected
    reasons: list[str] = field(default_factory=list)
    run_id: str | None = None


@dataclass
class IngestResult:
    upload_id: str
    status: str
    duplicate_batch: bool
    synthetic: bool
    counts: dict[str, int]
    observations: list[ObservationResult]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validation_reasons(err: ValidationError) -> list[str]:
    out = []
    for e in err.errors()[:5]:
        loc = ".".join(str(p) for p in e["loc"])
        out.append(f"invalid:{loc}:{e['type']}")
    return out


def _timespan(obs) -> tuple[int | None, int | None]:
    if isinstance(obs, DungeonRunObservation):
        return obs.timing.started_at, obs.timing.ended_at or obs.timing.last_updated_at
    return obs.observed_at, obs.observed_at


def _previous_result(db: Session, upload: UploadBatch) -> IngestResult:
    return IngestResult(
        upload_id=str(upload.id),
        status=upload.status,
        duplicate_batch=True,
        synthetic=upload.is_synthetic,
        counts=dict(upload.counts),
        observations=[],
    )


def ingest_batch(
    db: Session,
    payload: dict[str, Any],
    *,
    source: str,
    payload_sha256: str,
    size_bytes: int,
    settings: Settings,
    now: int | None = None,
) -> IngestResult:
    """Validate and apply one batch. The caller commits (or rolls back) the session."""
    now = int(time.time()) if now is None else now
    try:
        envelope = ObservationBatchEnvelope.model_validate(payload)
    except ValidationError as err:
        raise IngestError(422, "invalid_envelope", "; ".join(_validation_reasons(err))) from err
    if len(envelope.observations) > settings.max_observations_per_batch:
        raise IngestError(413, "too_many_observations", f"at most {settings.max_observations_per_batch} per batch")
    if envelope.synthetic and not settings.allow_synthetic_data:
        raise IngestError(422, "synthetic_not_allowed", "synthetic development data is not accepted in this environment")

    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": INGEST_LOCK_KEY})
    contributor = get_or_create_contributor(db, envelope.installation_id, settings, synthetic=envelope.synthetic)
    if contributor.status == "banned":
        raise IngestError(403, "contributor_banned", "uploads from this installation are not accepted")

    digest = observations_digest(envelope.installation_id, envelope.observations)
    existing = db.scalar(
        select(UploadBatch).where(UploadBatch.contributor_id == contributor.id, UploadBatch.batch_key == envelope.batch_id)
    )
    if existing is not None:
        if existing.content_digest == digest:
            return _previous_result(db, existing)
        raise IngestError(409, "batch_id_reused", "this batch_id was already used for different content")

    upload = UploadBatch(
        id=uuid.uuid4(),
        contributor_id=contributor.id,
        batch_key=envelope.batch_id,
        schema_version=envelope.schema_version,
        content_digest=digest,
        payload_sha256=payload_sha256,
        size_bytes=size_bytes,
        source=source,
        is_synthetic=envelope.synthetic,
        addon_version=envelope.addon.version,
        client_build=envelope.client.build,
    )
    db.add(upload)
    db.flush()

    ctx = ApplyContext(settings=settings, synthetic=envelope.synthetic)
    results: list[ObservationResult] = []
    for index, raw_obs in enumerate(envelope.observations):
        results.append(_ingest_one(db, index, raw_obs, upload, contributor, ctx, now))

    for run_id in sorted(ctx.dirty_runs):
        ctx.dirty_characters |= rebuild_run(db, run_id, settings)
    recompute_many(db, ctx.dirty_characters, settings)

    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    contributor.batch_count += 1
    contributor.accepted_count += counts.get("accepted", 0)
    contributor.quarantined_count += counts.get("quarantined", 0)
    contributor.rejected_count += counts.get("rejected", 0)
    if contributor.status == "active" and contributor.quarantined_count >= settings.contributor_flag_threshold:
        contributor.status = "flagged"
        contributor.status_reason = "quarantine_threshold_reached"

    accepted = counts.get("accepted", 0) + counts.get("duplicate", 0) + counts.get("stale", 0)
    if accepted == len(results):
        upload.status = "processed"
    elif counts.get("quarantined", 0) == len(results):
        upload.status = "quarantined"
    elif accepted == 0 and counts.get("quarantined", 0) == 0:
        upload.status = "rejected"
    else:
        upload.status = "partially_accepted"
    upload.counts = counts
    upload.errors = [
        {"index": r.index, "observation_id": r.observation_id, "status": r.status, "reasons": r.reasons}
        for r in results
        if r.status in ("rejected", "quarantined")
    ][:MAX_RECORDED_ERRORS]
    upload.processed_at = utcnow()
    db.flush()
    return IngestResult(
        upload_id=str(upload.id),
        status=upload.status,
        duplicate_batch=False,
        synthetic=envelope.synthetic,
        counts=counts,
        observations=results,
    )


def _ingest_one(db, index, raw_obs, upload, contributor, ctx: ApplyContext, now: int) -> ObservationResult:
    oid = raw_obs.get("observation_id") if isinstance(raw_obs, dict) else None
    rev = raw_obs.get("revision") if isinstance(raw_obs, dict) else None
    otype = raw_obs.get("type") if isinstance(raw_obs, dict) else None
    result = ObservationResult(
        index=index,
        observation_id=oid if isinstance(oid, str) else None,
        revision=rev if isinstance(rev, int) else None,
        type=otype if isinstance(otype, str) else None,
        status="rejected",
    )
    try:
        obs = observation_adapter.validate_python(raw_obs)
    except ValidationError as err:
        result.reasons = _validation_reasons(err)
        return result

    sanity = check_observation(obs, ctx.settings, now)
    if sanity.reject:
        result.reasons = sanity.reject
        return result

    payload = obs.model_dump(mode="json")
    content_sha = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    same_key = list(
        db.scalars(
            select(RawObservation).where(
                RawObservation.contributor_id == contributor.id, RawObservation.observation_key == obs.observation_id
            )
        )
    )
    same_rev = next((r for r in same_key if r.revision == obs.revision), None)
    if same_rev is not None:
        if same_rev.content_sha256 == content_sha:
            result.status = "duplicate"
        else:
            result.reasons = ["revision_content_conflict"]
        return result

    quarantine = list(sanity.quarantine)
    if contributor.status == "flagged":
        quarantine.append("contributor_flagged")
    start, end = _timespan(obs)
    newer = [r for r in same_key if r.revision > obs.revision and r.status in ("accepted", "quarantined")]
    status = "superseded" if newer else ("quarantined" if quarantine else "accepted")

    def new_row(row_status: str, reasons: list[str]) -> RawObservation:
        row = RawObservation(
            batch_id=upload.id,
            contributor_id=contributor.id,
            observation_key=obs.observation_id,
            revision=obs.revision,
            type=obs.type,
            content_sha256=content_sha,
            payload=payload,
            observed_start=from_epoch(start),
            observed_end=from_epoch(end),
            status=row_status,
            quarantine_reasons=reasons,
            is_synthetic=ctx.synthetic,
        )
        db.add(row)
        db.flush()
        return row

    if status == "superseded":
        new_row("superseded", [])
        result.status = "stale"
        return result
    if status == "quarantined":
        new_row("quarantined", quarantine)
        _supersede_older(db, same_key, obs.revision, ctx, only_quarantined=True)
        result.status, result.reasons = "quarantined", quarantine
        return result

    savepoint = db.begin_nested()
    try:
        preferred_run_id = _supersede_older(db, same_key, obs.revision, ctx)
        row = new_row("accepted", [])
        if isinstance(obs, DungeonRunObservation):
            # If the new revision lands in a different run, the old run stays in
            # ctx.dirty_runs and is rebuilt (or removed) after the batch.
            run = apply_dungeon_run(db, row, obs, ctx, preferred_run_id)
            result.run_id = run.public_id
        elif isinstance(obs, CharacterSnapshotObservation):
            apply_snapshot(db, row, obs, ctx)
        savepoint.commit()
        result.status = "accepted"
    except IdentityConflict as conflict:
        savepoint.rollback()
        new_row("quarantined", [conflict.reason])
        result.status, result.reasons = "quarantined", [conflict.reason]
    return result


def _supersede_older(db: Session, same_key: list[RawObservation], revision: int, ctx: ApplyContext, only_quarantined: bool = False) -> int | None:
    """Mark lower revisions superseded. Returns the run an accepted older revision was linked to."""
    preferred: int | None = None
    for older in sorted((r for r in same_key if r.revision < revision), key=lambda r: r.revision):
        if older.status == "quarantined":
            older.status = "superseded"
        elif older.status == "accepted" and not only_quarantined:
            older.status = "superseded"
            run_id = detach(db, older, ctx, rebuild=False)
            if run_id is not None:
                preferred = run_id
    return preferred
