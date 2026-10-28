from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.ingestion.service import IngestResult, ingest_batch
from app.models import Character, DungeonRun, ParticipantMetric


def ingest(db: Session, settings: Settings, payload: dict[str, Any], *, now: int | None = None) -> IngestResult:
    raw = json.dumps(payload).encode()
    result = ingest_batch(
        db,
        payload,
        source="api",
        payload_sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        settings=settings,
        now=now or 1_850_000_000,
    )
    db.commit()
    return result


def count(db: Session, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def runs(db: Session) -> list[DungeonRun]:
    return list(db.scalars(select(DungeonRun).order_by(DungeonRun.id)))


def character(db: Session, full_name: str) -> Character:
    return db.scalar(select(Character).where(Character.full_name == full_name))


def metric(db: Session, run_id: int, character_id: int, name: str) -> ParticipantMetric | None:
    return db.scalar(
        select(ParticipantMetric).where(
            ParticipantMetric.run_id == run_id,
            ParticipantMetric.character_id == character_id,
            ParticipantMetric.metric == name,
        )
    )
