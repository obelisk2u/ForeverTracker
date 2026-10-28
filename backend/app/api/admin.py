"""Internal moderation API. Requires ``Authorization: Bearer $ADMIN_TOKEN``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_settings, require_admin
from app.config import Settings
from app.models import Contributor, DataReport, RawObservation, RunMatchCandidate
from app.services import moderation
from app.services.common import NotFound

# Not advertised in the public OpenAPI document; documented in docs/OPERATIONS.md.
router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)], include_in_schema=False)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


class ContributorStatusIn(ReasonIn):
    status: str = Field(pattern=r"^(active|flagged|banned)$")
    invalidate_all: bool = False


class VisibilityIn(BaseModel):
    visibility: str = Field(pattern=r"^(public|suppressed)$")
    note: str = Field(default="", max_length=500)


class ReportResolutionIn(BaseModel):
    status: str = Field(pattern=r"^(resolved|rejected)$")
    note: str = Field(default="", max_length=2000)


def _do(db: Session, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        db.commit()
        return result
    except NotFound:
        db.rollback()
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as err:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(err)) from None


@router.get("/quarantine")
def list_quarantine(limit: int = Query(50, le=500), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(RawObservation).where(RawObservation.status == "quarantined").order_by(RawObservation.id.desc()).limit(limit)
    ).all()
    return [
        {
            "raw_observation_id": r.id,
            "type": r.type,
            "observation_key": r.observation_key,
            "revision": r.revision,
            "contributor_id": r.contributor_id,
            "reasons": r.quarantine_reasons,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/unresolved-matches")
def list_unresolved(limit: int = Query(50, le=500), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(RunMatchCandidate).where(RunMatchCandidate.status == "unresolved").order_by(RunMatchCandidate.id.desc()).limit(limit)
    ).all()
    return [{"raw_observation_id": r.raw_observation_id, "candidate_run_id": r.candidate_run_id, "score": r.score, "evidence": r.evidence} for r in rows]


@router.get("/contributors")
def list_contributors(status: str | None = None, limit: int = Query(50, le=500), db: Session = Depends(get_db)):
    stmt = select(Contributor).order_by(Contributor.quarantined_count.desc(), Contributor.id).limit(limit)
    if status:
        stmt = stmt.where(Contributor.status == status)
    return [
        {
            "contributor_id": c.id,
            "status": c.status,
            "status_reason": c.status_reason,
            "batches": c.batch_count,
            "accepted": c.accepted_count,
            "quarantined": c.quarantined_count,
            "rejected": c.rejected_count,
            "synthetic": c.is_synthetic,
            "last_seen_at": c.last_seen_at,
        }
        for c in db.scalars(stmt)
    ]


@router.get("/reports")
def list_reports(status: str = "open", db: Session = Depends(get_db)):
    rows = db.scalars(select(DataReport).where(DataReport.status == status).order_by(DataReport.created_at)).all()
    return [{"report_id": r.public_id, "kind": r.kind, "message": r.message, "created_at": r.created_at} for r in rows]


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    by_status = dict(db.execute(select(RawObservation.status, func.count()).group_by(RawObservation.status)).all())
    return {"raw_observations": by_status}


@router.post("/observations/{raw_id}/invalidate")
def invalidate_observation(raw_id: int, body: ReasonIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return _do(db, moderation.invalidate_observation, db, settings, raw_id, body.reason, "admin")


@router.post("/observations/{raw_id}/release")
def release_observation(raw_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return _do(db, moderation.release_quarantined, db, settings, raw_id, "admin")


@router.post("/uploads/{upload_id}/invalidate")
def invalidate_upload(upload_id: str, body: ReasonIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return _do(db, moderation.invalidate_batch, db, settings, upload_id, body.reason, "admin")


@router.post("/contributors/{contributor_id}/status")
def contributor_status(
    contributor_id: int, body: ContributorStatusIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
):
    return _do(
        db, moderation.set_contributor_status, db, settings, contributor_id, body.status, body.reason, "admin", invalidate_all=body.invalidate_all
    )


@router.post("/characters/{public_id}/visibility")
def character_visibility(public_id: str, body: VisibilityIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return _do(db, moderation.set_character_visibility, db, settings, public_id, body.visibility, body.note, "admin")


@router.post("/reports/{report_id}/resolve")
def resolve_report(report_id: str, body: ReportResolutionIn, db: Session = Depends(get_db)):
    return _do(db, moderation.resolve_report, db, report_id, body.status, body.note, "admin")


@router.post("/rebuild")
def rebuild(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return _do(db, moderation.rebuild_all, db, settings)
