from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Character, Contributor, Dungeon, DungeonRun, RawObservation, RunDeath, RunParticipant, UploadBatch
from app.models.base import utcnow
from app.schemas.api import ActivityItem, MetaOut, OverviewStats
from app.schemas.observations import SCHEMA_VERSION
from app.services.common import dungeon_ref
from app.services.visibility import character_visible, hide_synthetic, run_visible

ADDON_INTERFACE = 16001


def meta(db: Session, settings: Settings) -> MetaOut:
    synthetic = (not hide_synthetic(settings)) and db.scalar(
        select(func.count()).select_from(DungeonRun).where(DungeonRun.is_synthetic.is_(True))
    )
    return MetaOut(
        environment=settings.environment,
        synthetic_data_present=bool(synthetic),
        schema_version=SCHEMA_VERSION,
        addon_interface=ADDON_INTERFACE,
        meter_death_interpretation=settings.meter_death_interpretation,
        last_ingest_at=db.scalar(select(func.max(UploadBatch.processed_at))),
    )


def overview(db: Session, settings: Settings) -> OverviewStats:
    visible_runs = select(DungeonRun.id).where(run_visible(settings)).subquery()
    runs = db.scalar(select(func.count()).select_from(visible_runs)) or 0
    week = db.scalar(
        select(func.count()).select_from(DungeonRun).where(run_visible(settings), DungeonRun.started_at >= utcnow() - timedelta(days=7))
    )
    reconciled = db.scalar(select(func.count()).select_from(DungeonRun).where(run_visible(settings), DungeonRun.contributor_count > 1))
    completions = db.scalar(
        select(func.count()).select_from(DungeonRun).where(
            run_visible(settings), DungeonRun.outcome == "completed", DungeonRun.completion_confidence == "verified"
        )
    )
    deaths = db.scalar(
        select(func.count()).select_from(RunDeath).join(DungeonRun, DungeonRun.id == RunDeath.run_id).where(run_visible(settings))
    )
    contributor_filter = [Contributor.status != "banned"]
    if hide_synthetic(settings):
        contributor_filter.append(Contributor.is_synthetic.is_(False))
    contributors = db.scalar(select(func.count()).select_from(Contributor).where(*contributor_filter))
    characters = db.scalar(select(func.count()).select_from(Character).where(character_visible(settings)))
    top = db.execute(
        select(Dungeon, func.count(DungeonRun.id).label("n"))
        .join(DungeonRun, DungeonRun.dungeon_id == Dungeon.id)
        .where(run_visible(settings))
        .group_by(Dungeon.id)
        .order_by(func.count(DungeonRun.id).desc())
        .limit(9)
    ).all()
    last = db.scalar(select(func.max(DungeonRun.last_observed_at)).where(run_visible(settings)))
    return OverviewStats(
        characters=characters or 0,
        runs=runs,
        runs_last_7_days=week or 0,
        reconciled_runs=reconciled or 0,
        confirmed_completions=completions or 0,
        observed_deaths=deaths or 0,
        contributors=contributors or 0,
        dungeons=[{**dungeon_ref(d).model_dump(), "runs": n} for d, n in top],
        last_observation_at=last,
    )


def recent_activity(db: Session, settings: Settings, limit: int = 12) -> list[ActivityItem]:
    counts = (
        select(RunParticipant.run_id, func.count().label("n")).group_by(RunParticipant.run_id).subquery()
    )
    rows = db.execute(
        select(DungeonRun, Dungeon, counts.c.n)
        .join(Dungeon, Dungeon.id == DungeonRun.dungeon_id)
        .outerjoin(counts, counts.c.run_id == DungeonRun.id)
        .where(run_visible(settings))
        .order_by(DungeonRun.started_at.desc())
        .limit(limit)
    ).all()
    return [
        ActivityItem(
            run_id=run.public_id,
            dungeon=dungeon_ref(d),
            started_at=run.started_at,
            outcome=run.outcome,
            completion_confidence=run.completion_confidence,
            participants=n or 0,
            observers=run.contributor_count,
            is_synthetic=run.is_synthetic,
        )
        for run, d, n in rows
    ]


def dungeons(db: Session, settings: Settings) -> list[dict]:
    rows = db.execute(
        select(Dungeon, func.count(DungeonRun.id))
        .outerjoin(DungeonRun, and_(DungeonRun.dungeon_id == Dungeon.id, run_visible(settings)))
        .group_by(Dungeon.id)
        .order_by(Dungeon.name)
    ).all()
    return [
        {
            **dungeon_ref(d).model_dump(),
            "instance_type": d.instance_type,
            "catalog_status": d.catalog_status,
            "final_encounter_known": d.final_encounter_id is not None,
            "encounters": d.encounters,
            "runs": n,
            "is_synthetic": d.is_synthetic,
        }
        for d, n in rows
        if not (hide_synthetic(settings) and d.is_synthetic)
    ]


def raw_observation_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(RawObservation)) or 0
