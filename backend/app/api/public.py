"""Public, read-only API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_settings
from app.config import Settings
from app.models import Character, DataReport, DungeonRun
from app.schemas.api import (
    ActivityItem,
    CharacterProfile,
    Companion,
    MetaOut,
    OverviewStats,
    ProgressionResponse,
    ReportIn,
    ReportOut,
    RunDetail,
    RunHistoryResponse,
    SearchResponse,
    UploaderRelease,
)
from app.services import characters, runs, site
from app.services.common import NotFound, Suppressed

router = APIRouter(prefix="/api/v1", tags=["public"])

SUPPRESSED_DETAIL = "This profile has been hidden at the owner's request or by moderators."


def _cache(response: Response, seconds: int = 30) -> None:
    response.headers["Cache-Control"] = f"public, max-age={seconds}"


def _character_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NotFound:
        raise HTTPException(status_code=404, detail="character not found") from None
    except Suppressed:
        raise HTTPException(status_code=410, detail=SUPPRESSED_DETAIL) from None


@router.get("/meta", response_model=MetaOut)
def get_meta(response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    _cache(response, 15)
    return site.meta(db, settings)


@router.get("/uploader/latest", response_model=UploaderRelease)
def get_uploader_release(response: Response, settings: Settings = Depends(get_settings)):
    """The newest desktop app: polled by installed apps to update themselves, and linked from the Download page."""
    if not (settings.uploader_latest_version and settings.uploader_download_url and settings.uploader_sha256):
        raise HTTPException(status_code=404, detail="no desktop app release published")
    _cache(response, 300)
    return UploaderRelease(
        version=settings.uploader_latest_version,
        download_url=settings.uploader_download_url,
        sha256=settings.uploader_sha256.lower(),
        signed=settings.uploader_signed,
    )


@router.get("/stats/overview", response_model=OverviewStats)
def get_overview(response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    _cache(response, 60)
    return site.overview(db, settings)


@router.get("/activity/recent", response_model=list[ActivityItem])
def get_recent(
    response: Response,
    limit: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _cache(response, 30)
    return site.recent_activity(db, settings, limit)


@router.get("/dungeons")
def get_dungeons(response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    _cache(response, 300)
    return site.dungeons(db, settings)


@router.get("/search", response_model=SearchResponse)
def search(
    response: Response,
    q: str = Query(..., min_length=1, max_length=64),
    namespace: str | None = Query(None, max_length=48),
    class_: str | None = Query(None, alias="class", max_length=24),
    exact: bool = False,
    page: int = Query(1, ge=1, le=500),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        result = characters.search(db, settings, q, namespace=namespace, class_file=class_, exact=exact, page=page, page_size=page_size)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from None
    _cache(response, 30)
    return result


@router.get("/characters/{namespace}/{character_id}", response_model=CharacterProfile)
def get_character(
    namespace: str, character_id: str, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
):
    result = _character_call(characters.profile, db, settings, character_id)
    _cache(response, 30)
    return result


@router.get("/characters/{namespace}/{character_id}/runs", response_model=RunHistoryResponse)
def get_character_runs(
    namespace: str,
    character_id: str,
    response: Response,
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(25, ge=1, le=100),
    dungeon: str | None = Query(None, max_length=80),
    role: str | None = Query(None, pattern=r"^(TANK|HEALER|DAMAGER|NONE|tank|healer|damager|none)$"),
    outcome: str | None = Query(None, pattern=r"^(completed|abandoned|left|disconnected|in_progress|unknown)$"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    result = _character_call(
        characters.run_history, db, settings, character_id, page=page, page_size=page_size, dungeon=dungeon, role=role, outcome=outcome
    )
    _cache(response, 30)
    return result


@router.get("/characters/{namespace}/{character_id}/progression", response_model=ProgressionResponse)
def get_character_progression(
    namespace: str, character_id: str, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
):
    result = _character_call(characters.progression, db, settings, character_id)
    _cache(response, 60)
    return result


@router.get("/characters/{namespace}/{character_id}/companions", response_model=list[Companion])
def get_character_companions(
    namespace: str, character_id: str, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
):
    result = _character_call(characters.companions, db, settings, character_id)
    _cache(response, 60)
    return result


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    try:
        result = runs.run_detail(db, settings, run_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="run not found") from None
    _cache(response, 30)
    return result


@router.post("/reports", response_model=ReportOut, status_code=201)
def create_report(body: ReportIn, db: Session = Depends(get_db)):
    character_id = run_id = None
    if body.character_id:
        character_id = db.scalar(select(Character.id).where(Character.public_id == body.character_id))
        if character_id is None:
            raise HTTPException(status_code=404, detail="character not found")
    if body.run_id:
        run_id = db.scalar(select(DungeonRun.id).where(DungeonRun.public_id == body.run_id))
        if run_id is None:
            raise HTTPException(status_code=404, detail="run not found")
    report = DataReport(kind=body.kind, character_id=character_id, run_id=run_id, message=body.message)
    db.add(report)
    db.commit()
    return ReportOut(report_id=report.public_id, status=report.status)
