from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_public_id


class DataReport(Base):
    """A public report: wrong identity, wrong statistics, or a request to suppress a profile.

    Deliberately collects no contact details.
    """

    __tablename__ = "data_reports"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('incorrect_identity','incorrect_statistics','suppression_request','other')", name="kind"
        ),
        CheckConstraint("status IN ('open','resolved','rejected')", name="status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(16), unique=True, default=new_public_id)
    kind: Mapped[str] = mapped_column(String(32))
    character_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id", ondelete="SET NULL"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("dungeon_runs.id", ondelete="SET NULL"))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None]


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
