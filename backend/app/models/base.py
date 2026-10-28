from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_PUBLIC_ID_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"


def new_public_id(length: int = 10) -> str:
    """Short, unguessable, URL-safe identifier (no 0/o/1/l/i to avoid transcription errors)."""
    return "".join(secrets.choice(_PUBLIC_ID_ALPHABET) for _ in range(length))


def utcnow() -> datetime:
    return datetime.now(UTC)


def from_epoch(value: int | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
