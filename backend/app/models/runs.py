"""Dungeons, canonical (reconciled) dungeon runs, participants, encounters, deaths and metrics.

A *canonical run* is ForeverTracker's best reconstruction of one real dungeon run. It is
assembled from one or more raw ``dungeon_run`` observations (one per observer, per revision).
All columns here are derived and can be recomputed from the linked raw observations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_public_id
from app.models.characters import Character, Namespace


class Dungeon(TimestampMixin, Base):
    """Dungeon catalog, learned from observations and optionally curated.

    ``final_encounter_id`` stays NULL until a maintainer verifies it in-game; only then can
    "final boss killed" be used as *probable* completion evidence.
    """

    __tablename__ = "dungeons"
    __table_args__ = (CheckConstraint("catalog_status IN ('observed','curated')", name="catalog_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    map_id: Mapped[int] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    instance_type: Mapped[str] = mapped_column(String(16))
    max_players: Mapped[int | None]
    catalog_status: Mapped[str] = mapped_column(String(16), default="observed")
    final_encounter_id: Mapped[int | None]
    encounters: Mapped[list[Any]] = mapped_column(default=list)
    is_synthetic: Mapped[bool] = mapped_column(default=False)


class DungeonRun(TimestampMixin, Base):
    __tablename__ = "dungeon_runs"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('completed','abandoned','left','disconnected','in_progress','unknown')", name="outcome"
        ),
        CheckConstraint("completion_confidence IN ('verified','probable','none')", name="completion_confidence"),
        CheckConstraint("match_status IN ('single','reconciled','unresolved')", name="match_status"),
        Index("ix_runs_match_window", "namespace_id", "dungeon_id", "started_at"),
        Index("ix_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(16), unique=True, default=new_public_id)
    namespace_id: Mapped[int] = mapped_column(ForeignKey("namespaces.id"))
    dungeon_id: Mapped[int] = mapped_column(ForeignKey("dungeons.id"))
    difficulty_id: Mapped[int | None]
    difficulty_name: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
    last_observed_at: Mapped[datetime]
    duration_seconds: Mapped[int | None]
    outcome: Mapped[str] = mapped_column(String(16), default="unknown")
    completion_confidence: Mapped[str] = mapped_column(String(16), default="none")
    outcome_evidence: Mapped[list[Any]] = mapped_column(default=list)
    party_guid: Mapped[str | None] = mapped_column(String(96))
    observation_count: Mapped[int] = mapped_column(default=0)
    contributor_count: Mapped[int] = mapped_column(default=0)
    match_status: Mapped[str] = mapped_column(String(16), default="single")
    coverage: Mapped[dict[str, Any]] = mapped_column(default=dict)
    quarantined: Mapped[bool] = mapped_column(default=False)
    is_synthetic: Mapped[bool] = mapped_column(default=False)
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("dungeon_runs.id"))

    dungeon: Mapped[Dungeon] = relationship()
    namespace: Mapped[Namespace] = relationship()
    participants: Mapped[list[RunParticipant]] = relationship(back_populates="run", cascade="all, delete-orphan")


class RunObservation(Base):
    """Links a raw observation to the canonical run it was reconciled into."""

    __tablename__ = "run_observations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("dungeon_runs.id", ondelete="CASCADE"), index=True)
    raw_observation_id: Mapped[int] = mapped_column(
        ForeignKey("raw_observations.id", ondelete="CASCADE"), unique=True
    )
    match_score: Mapped[float]
    match_evidence: Mapped[dict[str, Any]] = mapped_column(default=dict)
    linked_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RunMatchCandidate(Base):
    """An ambiguous match kept for review instead of being guessed."""

    __tablename__ = "run_match_candidates"
    __table_args__ = (UniqueConstraint("raw_observation_id", "candidate_run_id", name="raw_candidate"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    raw_observation_id: Mapped[int] = mapped_column(ForeignKey("raw_observations.id", ondelete="CASCADE"))
    candidate_run_id: Mapped[int] = mapped_column(ForeignKey("dungeon_runs.id", ondelete="CASCADE"))
    score: Mapped[float]
    evidence: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16), default="unresolved")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RunParticipant(Base):
    __tablename__ = "run_participants"
    __table_args__ = (
        UniqueConstraint("run_id", "character_id", name="run_character"),
        Index("ix_participants_character", "character_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("dungeon_runs.id", ondelete="CASCADE"))
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    role: Mapped[str | None] = mapped_column(String(8))
    class_file: Mapped[str | None] = mapped_column(String(24))
    level: Mapped[int | None]
    joined_at: Mapped[datetime | None]
    left_at: Mapped[datetime | None]
    presence_seconds: Mapped[int | None]
    presence_ratio: Mapped[float | None]
    observer_count: Mapped[int] = mapped_column(default=0)
    was_observer: Mapped[bool] = mapped_column(default=False)
    identity_confidence: Mapped[str] = mapped_column(String(16), default="name_only")
    completeness: Mapped[dict[str, Any]] = mapped_column(default=dict)

    run: Mapped[DungeonRun] = relationship(back_populates="participants")
    character: Mapped[Character] = relationship()


class RunEncounter(Base):
    __tablename__ = "run_encounters"
    __table_args__ = (Index("ix_run_encounters_run", "run_id", "started_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("dungeon_runs.id", ondelete="CASCADE"))
    encounter_id: Mapped[int]
    name: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
    success: Mapped[bool | None]
    observation_count: Mapped[int] = mapped_column(default=1)
    conflict: Mapped[bool] = mapped_column(default=False)


class RunDeath(Base):
    """One deduplicated death. ``sources`` lists every (observer, source) that saw it."""

    __tablename__ = "run_deaths"
    __table_args__ = (Index("ix_run_deaths_run_character", "run_id", "character_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("dungeon_runs.id", ondelete="CASCADE"))
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    occurred_at: Mapped[datetime]
    encounter_id: Mapped[int | None]
    sources: Mapped[list[Any]] = mapped_column(default=list)
    observation_count: Mapped[int] = mapped_column(default=1)


class MetricObservation(Base):
    """Every candidate value for a participant metric, with full provenance. Never overwritten."""

    __tablename__ = "metric_observations"
    __table_args__ = (Index("ix_metric_obs_lookup", "run_id", "character_id", "metric"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("dungeon_runs.id", ondelete="CASCADE"))
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    raw_observation_id: Mapped[int] = mapped_column(ForeignKey("raw_observations.id", ondelete="CASCADE"))
    contributor_id: Mapped[int] = mapped_column(ForeignKey("contributors.id"))
    metric: Mapped[str] = mapped_column(String(32))
    value: Mapped[float | None]
    unit: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    coverage: Mapped[str] = mapped_column(String(24))
    coverage_ratio: Mapped[float | None]
    combat_seconds: Mapped[float | None]
    collected_at: Mapped[datetime]
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)


class ParticipantMetric(Base):
    """The resolved value shown publicly, with its resolution and confidence."""

    __tablename__ = "participant_metrics"
    __table_args__ = (
        UniqueConstraint("run_id", "character_id", "metric", name="run_character_metric"),
        CheckConstraint(
            "resolution IN ('single_source','corroborated','conflicted','conflict_resolved')", name="resolution"
        ),
        CheckConstraint("confidence IN ('high','medium','low')", name="confidence"),
        Index("ix_participant_metrics_character", "character_id", "metric"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("dungeon_runs.id", ondelete="CASCADE"))
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    metric: Mapped[str] = mapped_column(String(32))
    value: Mapped[float | None]
    unit: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    coverage: Mapped[str] = mapped_column(String(24))
    resolution: Mapped[str] = mapped_column(String(24))
    confidence: Mapped[str] = mapped_column(String(8))
    candidate_count: Mapped[int]
    contributor_count: Mapped[int]
    derived: Mapped[bool] = mapped_column(default=False)
    metric_version: Mapped[int] = mapped_column(default=1)
    conflict: Mapped[dict[str, Any] | None]
