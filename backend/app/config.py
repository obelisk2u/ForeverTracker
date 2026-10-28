"""Environment-based configuration.

Every setting can be supplied as an environment variable of the same name (case-insensitive).
Production refuses to start with development defaults for secrets.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]

# Forever's beta opened 2026-09-17. Nothing legitimate can be older than the beta.
FOREVER_BETA_START_EPOCH = 1_789_603_200  # 2026-09-17T00:00:00Z


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Environment = "development"
    database_url: str = "postgresql+psycopg://forevertracker:forevertracker_dev@localhost:5433/forevertracker"
    db_pool_size: int = 5
    db_echo: bool = False
    # None = automatic (disabled on Windows only; see app/db.py).
    db_disable_pipeline: bool | None = None

    admin_token: str = "dev-admin-token"
    cors_origins: str = "http://localhost:3000"

    log_level: str = "INFO"
    log_json: bool = True

    # Synthetic (simulator-generated) data is accepted only outside production.
    allow_synthetic_data: bool | None = None

    # Ingestion limits (untrusted input).
    max_upload_bytes: int = 2_000_000
    max_savedvariables_bytes: int = 8_000_000
    max_observations_per_batch: int = 500
    rate_limit_uploads_per_hour: int = 120
    rate_limit_uploads_per_hour_per_ip: int = 300
    earliest_valid_timestamp: int = FOREVER_BETA_START_EPOCH
    max_future_skew_seconds: int = 600
    max_character_level: int = 60
    contributor_flag_threshold: int = 5

    # Reconciliation.
    match_time_padding_seconds: int = 900
    match_min_shared_characters: int = 2
    death_dedupe_window_seconds: int = 3
    metric_agreement_tolerance: float = 0.01

    stats_min_sample: int = 1

    # How the native meter's Deaths sessions are interpreted until validated in-game
    # (see docs/RESEARCH_FOREVER_API.md section 8.2).
    meter_death_interpretation: Literal["entry_per_death", "total_amount"] = "entry_per_death"

    public_base_url: str = "http://localhost:3000"
    metrics_enabled: bool = True

    # The newest desktop app, served at /api/v1/uploader/latest for its self-update and the Download
    # page. Installed apps only accept an installer signed by their own publisher. Unset = none offered.
    uploader_latest_version: str | None = None
    uploader_download_url: str | None = None
    uploader_sha256: str | None = None
    # Until the installer is code-signed, the Download page explains Windows' warning before downloading.
    uploader_signed: bool = False

    contributor_id_salt: str = Field(default="dev-contributor-salt")

    @model_validator(mode="after")
    def _derive_and_guard(self) -> "Settings":
        if self.allow_synthetic_data is None:
            self.allow_synthetic_data = self.environment != "production"
        if self.environment == "production":
            if self.allow_synthetic_data:
                raise ValueError("ALLOW_SYNTHETIC_DATA must be false in production")
            if self.admin_token in ("", "dev-admin-token") or len(self.admin_token) < 32:
                raise ValueError("ADMIN_TOKEN must be set to a random value of at least 32 characters in production")
            if self.contributor_id_salt == "dev-contributor-salt":
                raise ValueError("CONTRIBUTOR_ID_SALT must be set in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
