"""Contributors, upload batches and the raw observation store.

Raw observations are the system of record. Every derived table (runs, participants, metrics,
statistics) can be rebuilt from accepted raw observations (``python -m app.cli rebuild``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Contributor(Base):
    """A pseudonymous source of uploads: one addon installation.

    ``contributor_key`` is an HMAC of the addon's random installation ID, so the raw ID is
    never stored. No account, e-mail or IP address is associated with a contributor.
    """

    __tablename__ = "contributors"
    __table_args__ = (CheckConstraint("status IN ('active','flagged','banned')", name="status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    contributor_key: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(16), default="installation")
    status: Mapped[str] = mapped_column(String(16), default="active")
    status_reason: Mapped[str | None] = mapped_column(String(200))
    batch_count: Mapped[int] = mapped_column(default=0)
    accepted_count: Mapped[int] = mapped_column(default=0)
    quarantined_count: Mapped[int] = mapped_column(default=0)
    rejected_count: Mapped[int] = mapped_column(default=0)
    is_synthetic: Mapped[bool] = mapped_column(default=False)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())


class UploadBatch(Base):
    __tablename__ = "upload_batches"
    __table_args__ = (
        UniqueConstraint("contributor_id", "batch_key", name="contributor_batch"),
        CheckConstraint(
            "status IN ('received','processed','partially_accepted','rejected','quarantined')", name="status"
        ),
        Index("ix_upload_batches_received_at", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    contributor_id: Mapped[int] = mapped_column(ForeignKey("contributors.id"))
    batch_key: Mapped[str] = mapped_column(String(96))
    schema_version: Mapped[int]
    content_digest: Mapped[str] = mapped_column(String(64))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    source: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="received")
    is_synthetic: Mapped[bool] = mapped_column(default=False)
    addon_version: Mapped[str | None] = mapped_column(String(32))
    client_build: Mapped[str | None] = mapped_column(String(16))
    counts: Mapped[dict[str, Any]] = mapped_column(default=dict)
    errors: Mapped[list[Any]] = mapped_column(default=list)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    processed_at: Mapped[datetime | None]

    contributor: Mapped[Contributor] = relationship()


class RawObservation(Base):
    """One validated observation exactly as accepted, kept for audit and reprocessing."""

    __tablename__ = "raw_observations"
    __table_args__ = (
        UniqueConstraint("contributor_id", "observation_key", "revision", name="contributor_observation_revision"),
        CheckConstraint(
            "status IN ('accepted','superseded','quarantined','rejected','invalidated')", name="status"
        ),
        CheckConstraint("type IN ('dungeon_run','character_snapshot','probe_report')", name="type"),
        Index("ix_raw_observations_contributor_key", "contributor_id", "observation_key"),
        Index("ix_raw_observations_status_type", "status", "type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("upload_batches.id"))
    contributor_id: Mapped[int] = mapped_column(ForeignKey("contributors.id"))
    observation_key: Mapped[str] = mapped_column(String(80))
    revision: Mapped[int]
    type: Mapped[str] = mapped_column(String(24))
    content_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]]
    namespace_id: Mapped[int | None] = mapped_column(ForeignKey("namespaces.id"))
    observed_start: Mapped[datetime | None]
    observed_end: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(16), default="accepted")
    quarantine_reasons: Mapped[list[Any]] = mapped_column(default=list)
    is_synthetic: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    batch: Mapped[UploadBatch] = relationship()
    contributor: Mapped[Contributor] = relationship()
