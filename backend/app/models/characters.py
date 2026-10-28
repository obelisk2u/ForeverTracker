"""Characters, the evidence that identifies them, and what has been observed about them over time."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_public_id


class Namespace(Base):
    """The scope in which a character name is unique.

    Forever is realmless: a full name ("First Surname") is unique within a region (S8 in
    docs/RESEARCH_FOREVER_API.md). Rulesets are kept apart until proven to share a name space.
    """

    __tablename__ = "namespaces"
    __table_args__ = (UniqueConstraint("game", "region", "ruleset", name="game_region_ruleset"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(48), unique=True)
    game: Mapped[str] = mapped_column(String(16), default="forever")
    region: Mapped[str] = mapped_column(String(16))
    ruleset: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(64))
    is_synthetic: Mapped[bool] = mapped_column(default=False)


class Character(TimestampMixin, Base):
    __tablename__ = "characters"
    __table_args__ = (
        CheckConstraint("identity_confidence IN ('guid_confirmed','name_only')", name="identity_confidence"),
        CheckConstraint("visibility IN ('public','suppressed')", name="visibility"),
        CheckConstraint("claim_status IN ('unclaimed','pending','verified')", name="claim_status"),
        Index("ix_characters_namespace_name", "namespace_id", "full_name_normalized"),
        Index("ix_characters_last_observed", "last_observed_at"),
        Index("ix_characters_class", "class_file"),
        # Partial-name search; requires the pg_trgm extension (created in the initial migration).
        Index(
            "ix_characters_name_trgm",
            "full_name_normalized",
            postgresql_using="gin",
            postgresql_ops={"full_name_normalized": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(16), unique=True, default=new_public_id)
    namespace_id: Mapped[int] = mapped_column(ForeignKey("namespaces.id"))
    name: Mapped[str] = mapped_column(String(48))
    surname: Mapped[str | None] = mapped_column(String(48))
    full_name: Mapped[str] = mapped_column(String(100))
    full_name_normalized: Mapped[str] = mapped_column(String(100))
    realm_label: Mapped[str | None] = mapped_column(String(120))
    class_file: Mapped[str | None] = mapped_column(String(24))
    race_file: Mapped[str | None] = mapped_column(String(32))
    latest_level: Mapped[int | None]
    latest_level_at: Mapped[datetime | None]
    first_observed_at: Mapped[datetime]
    last_observed_at: Mapped[datetime]
    identity_confidence: Mapped[str] = mapped_column(String(16), default="name_only")
    claim_status: Mapped[str] = mapped_column(String(16), default="unclaimed")
    visibility: Mapped[str] = mapped_column(String(16), default="public")
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id"))
    is_synthetic: Mapped[bool] = mapped_column(default=False)

    namespace: Mapped[Namespace] = relationship()


class CharacterIdentityEvidence(Base):
    """Why we believe observations belong to a character.

    A GUID can belong to only one character within a namespace (partial unique index).
    Names are evidence, not identity: the same full name may appear on several character
    records (renames, deleted-and-recreated names, uncertain matches).
    """

    __tablename__ = "character_identity_evidence"
    __table_args__ = (
        CheckConstraint("kind IN ('guid','name')", name="kind"),
        CheckConstraint("strength IN ('strong','weak')", name="strength"),
        UniqueConstraint("character_id", "kind", "value", name="character_kind_value"),
        Index(
            "uq_identity_evidence_guid",
            "namespace_id",
            "value",
            unique=True,
            postgresql_where=text("kind = 'guid'"),
        ),
        Index("ix_identity_evidence_lookup", "namespace_id", "kind", "value"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    namespace_id: Mapped[int] = mapped_column(ForeignKey("namespaces.id"))
    kind: Mapped[str] = mapped_column(String(8))
    value: Mapped[str] = mapped_column(String(100))
    display_value: Mapped[str | None] = mapped_column(String(100))
    strength: Mapped[str] = mapped_column(String(8))
    observation_count: Mapped[int] = mapped_column(default=1)
    first_seen_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]


class EquipmentSnapshot(Base):
    __tablename__ = "equipment_snapshots"
    __table_args__ = (Index("ix_equipment_character_time", "character_id", "observed_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    raw_observation_id: Mapped[int] = mapped_column(ForeignKey("raw_observations.id", ondelete="CASCADE"))
    observed_at: Mapped[datetime]
    source: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    average_item_level: Mapped[float | None]
    items: Mapped[list[Any]] = mapped_column(default=list)
    talents: Mapped[dict[str, Any] | None]
    level: Mapped[int | None]
    is_synthetic: Mapped[bool] = mapped_column(default=False)


class LevelObservation(Base):
    __tablename__ = "level_observations"
    __table_args__ = (
        Index("ix_level_character_time", "character_id", "observed_at"),
        UniqueConstraint("character_id", "raw_observation_id", name="character_raw_observation"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    raw_observation_id: Mapped[int] = mapped_column(ForeignKey("raw_observations.id", ondelete="CASCADE"))
    observed_at: Mapped[datetime]
    level: Mapped[int]
    source: Mapped[str] = mapped_column(String(16))


class CharacterStats(Base):
    """Materialised profile aggregates. Rebuilt from runs; never edited by hand."""

    __tablename__ = "character_stats"

    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True)
    definitions_version: Mapped[int]
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    runs_observed: Mapped[int] = mapped_column(default=0)
    completions_confirmed: Mapped[int] = mapped_column(default=0)
    last_run_at: Mapped[datetime | None]
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict)
