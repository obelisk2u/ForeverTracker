"""Public API response models (they define the OpenAPI schema the frontend is typed against)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NamespaceOut(BaseModel):
    slug: str
    region: str
    ruleset: str
    display_name: str


class DungeonRef(BaseModel):
    slug: str
    name: str
    map_id: int


class CharacterSummary(BaseModel):
    id: str = Field(description="Stable public character ID used in URLs")
    namespace: str
    namespace_display: str
    name: str
    surname: str | None
    full_name: str
    class_file: str | None
    race_file: str | None
    latest_level: int | None
    first_observed_at: datetime
    last_observed_at: datetime
    identity_confidence: str
    runs_observed: int
    is_synthetic: bool


class HiddenCharacter(BaseModel):
    hidden: bool = True
    reason: str = "suppressed"


class SearchResponse(BaseModel):
    query: str
    exact: bool
    total: int
    page: int
    page_size: int
    results: list[CharacterSummary]
    duplicate_names: list[str] = Field(description="Full names that match more than one character in the results")


class StatOut(BaseModel):
    definition: str
    value: float | None
    sample_size: int
    excluded: int = 0
    exclusion_reasons: dict[str, int] = {}
    note: str | None = None


class MetricOut(BaseModel):
    metric: str
    value: float | None
    unit: str
    source: str
    status: str
    coverage: str
    resolution: str
    confidence: str
    contributors: int
    derived: bool


class MetricCandidateOut(BaseModel):
    observer: str
    value: float | None
    source: str
    status: str
    coverage: str
    coverage_ratio: float | None
    collected_at: datetime


class GearItemOut(BaseModel):
    slot: int
    slot_name: str
    item_id: int
    item_level: int | None
    enchant_id: int | None
    gem_ids: list[int]
    quality: int | None
    link: str | None


class GearSnapshotOut(BaseModel):
    observed_at: datetime
    source: str
    status: str
    average_item_level: float | None
    level: int | None
    items: list[GearItemOut]
    talents_status: str | None


class NameHistoryOut(BaseModel):
    full_name: str
    first_seen_at: datetime
    last_seen_at: datetime


class Freshness(BaseModel):
    last_observed_at: datetime
    stats_computed_at: datetime | None
    data_age_seconds: int


class CharacterProfile(BaseModel):
    character: CharacterSummary
    canonical_path: str
    realm_label: str | None
    claim_status: str
    stats: dict[str, Any]
    latest_gear: GearSnapshotOut | None
    name_history: list[NameHistoryOut]
    freshness: Freshness
    notices: list[str]


class PartyMemberOut(BaseModel):
    character: CharacterSummary | HiddenCharacter
    role: str | None
    class_file: str | None


class RunRow(BaseModel):
    run_id: str
    dungeon: DungeonRef
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None
    outcome: str
    completion_confidence: str
    role: str | None
    level: int | None
    presence_ratio: float | None
    party: list[PartyMemberOut]
    metrics: dict[str, MetricOut]
    observers: int
    match_status: str
    is_synthetic: bool


class RunHistoryResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[RunRow]


class Companion(BaseModel):
    character: CharacterSummary
    runs_together: int
    last_together_at: datetime


class ProgressionPoint(BaseModel):
    at: datetime
    value: float | None
    source: str
    sample_size: int | None = None


class RunSeriesPoint(BaseModel):
    run_id: str
    started_at: datetime
    dungeon: str
    deaths: MetricOut | None
    dps: MetricOut | None
    hps: MetricOut | None
    interrupts: MetricOut | None


class ProgressionResponse(BaseModel):
    level: list[ProgressionPoint]
    item_level: list[ProgressionPoint]
    runs: list[RunSeriesPoint]
    weekly: list[dict[str, Any]]
    note: str


class ParticipantOut(BaseModel):
    character: CharacterSummary | HiddenCharacter
    role: str | None
    class_file: str | None
    level: int | None
    joined_at: datetime | None
    left_at: datetime | None
    presence_ratio: float | None
    observed_by: int
    was_observer: bool
    completeness: dict[str, Any]
    metrics: dict[str, MetricOut]
    candidates: dict[str, list[MetricCandidateOut]]
    conflicts: dict[str, Any]


class EncounterOut(BaseModel):
    encounter_id: int
    name: str | None
    started_at: datetime
    ended_at: datetime | None
    success: bool | None
    observed_by: int
    conflict: bool


class DeathOut(BaseModel):
    character_id: str | None
    occurred_at: datetime
    encounter_id: int | None
    sources: list[str]
    observed_by: int


class WipeOut(BaseModel):
    at: datetime
    kind: str
    inferred: bool
    encounter_id: int | None
    detail: str


class SourceOut(BaseModel):
    observer: str
    state: str
    revision: int
    started_at: datetime
    ended_at: datetime | None
    meter_status: str | None
    collectors: dict[str, str]
    client_build: str | None
    uploaded_at: datetime


class RunDetail(BaseModel):
    run_id: str
    dungeon: DungeonRef
    namespace: NamespaceOut
    difficulty_id: int | None
    difficulty_name: str | None
    started_at: datetime
    ended_at: datetime | None
    last_observed_at: datetime
    duration_seconds: int | None
    outcome: str
    completion_confidence: str
    outcome_evidence: list[dict[str, Any]]
    match_status: str
    observation_count: int
    contributor_count: int
    coverage: dict[str, Any]
    participants: list[ParticipantOut]
    encounters: list[EncounterOut]
    deaths: list[DeathOut]
    wipes: list[WipeOut]
    sources: list[SourceOut]
    is_synthetic: bool


class ActivityItem(BaseModel):
    run_id: str
    dungeon: DungeonRef
    started_at: datetime
    outcome: str
    completion_confidence: str
    participants: int
    observers: int
    is_synthetic: bool


class OverviewStats(BaseModel):
    characters: int
    runs: int
    runs_last_7_days: int
    reconciled_runs: int
    confirmed_completions: int
    observed_deaths: int
    contributors: int
    dungeons: list[dict[str, Any]]
    last_observation_at: datetime | None


class MetaOut(BaseModel):
    environment: str
    synthetic_data_present: bool
    schema_version: int
    addon_interface: int
    meter_death_interpretation: str
    last_ingest_at: datetime | None


class UploaderRelease(BaseModel):
    version: str
    download_url: str
    sha256: str
    signed: bool


class UploadObservationOut(BaseModel):
    index: int
    observation_id: str | None
    revision: int | None
    type: str | None
    status: str
    reasons: list[str]
    run_id: str | None


class UploadResult(BaseModel):
    upload_id: str
    status: str
    duplicate_batch: bool
    synthetic: bool
    counts: dict[str, int]
    observations: list[UploadObservationOut]


class SavedVariablesUploadResult(BaseModel):
    batches: list[UploadResult]
    summary: dict[str, Any]


class ReportIn(BaseModel):
    kind: str = Field(pattern=r"^(incorrect_identity|incorrect_statistics|suppression_request|other)$")
    character_id: str | None = Field(default=None, max_length=16)
    run_id: str | None = Field(default=None, max_length=16)
    message: str = Field(min_length=10, max_length=2000)


class ReportOut(BaseModel):
    report_id: str
    status: str


class ErrorOut(BaseModel):
    error: str
    detail: str
