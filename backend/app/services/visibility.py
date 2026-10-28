"""What the public API may show.

* Suppressed characters are excluded from search and appear as "hidden" in rosters.
* Merged characters resolve to the character they were merged into.
* Quarantined runs are never shown.
* In production, synthetic data is filtered out even though ingestion already refuses it.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, and_

from app.config import Settings
from app.models import Character, DungeonRun


def character_visible(settings: Settings) -> ColumnElement[bool]:
    conds = [Character.visibility == "public", Character.merged_into_id.is_(None)]
    if settings.environment == "production":
        conds.append(Character.is_synthetic.is_(False))
    return and_(*conds)


def run_visible(settings: Settings) -> ColumnElement[bool]:
    conds = [DungeonRun.quarantined.is_(False), DungeonRun.merged_into_id.is_(None)]
    if settings.environment == "production":
        conds.append(DungeonRun.is_synthetic.is_(False))
    return and_(*conds)


def hide_synthetic(settings: Settings) -> bool:
    return settings.environment == "production"
