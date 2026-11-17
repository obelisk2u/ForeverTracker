"""Metric and statistic definitions.

Every public number is defined here once: what it measures, its unit, and which
observations are eligible. ``docs/ANALYTICS_DEFINITIONS.md`` is the human-readable copy.
Bump the version when a definition changes so stored aggregates can be rebuilt.
"""

from __future__ import annotations

from dataclasses import dataclass

METRIC_VERSION = 1
STATS_DEFINITIONS_VERSION = 1

# A participant must have been present for this share of the run for per-run statistics.
MIN_PRESENCE_RATIO = 0.9
# An observer must have covered this share of the run for its meter data to be "complete".
COMPLETE_COVERAGE_RATIO = 0.95
# A group member in the run for less than this, and at no boss pull, only passed through (left as
# the run began and was replaced): not a participant, so the run is not theirs and not counted.
PASSED_THROUGH_SECONDS = 300
# Addon versions before 0.2.10 could read a fight's meter session as the group pulled (before the
# recording player was in combat) and never again: "captured", but this long at most and nearly
# empty. Such a fight's numbers are lost.
PULL_READ_FIXED_IN = (0, 2, 10)
PULL_READ_MAX_SECONDS = 1.0
# A boss attempt whose meter covers PULL_READ_MAX_SECONDS or less of a fight at least this long has
# no usable numbers, whichever version recorded it.
PULL_READ_FIGHT_SECONDS = 5.0


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    unit: str  # "amount" | "count" | "per_second"
    higher_is_better: bool | None
    derived_from: str | None = None


METRICS: dict[str, MetricDef] = {
    m.key: m
    for m in [
        MetricDef("damage_done", "Damage done", "amount", True),
        MetricDef("healing_done", "Healing done", "amount", True),
        MetricDef("absorbs", "Absorbs", "amount", True),
        MetricDef("interrupts", "Interrupts", "count", True),
        MetricDef("dispels", "Dispels", "count", True),
        MetricDef("damage_taken", "Damage taken", "amount", None),
        MetricDef("avoidable_damage_taken", "Avoidable damage taken", "amount", False),
        MetricDef("deaths", "Deaths", "count", False),
        # Derived: total divided by the native meter's combat seconds for the same observation.
        MetricDef("dps", "Damage per second (combat time)", "per_second", True, derived_from="damage_done"),
        MetricDef("hps", "Healing per second (combat time)", "per_second", True, derived_from="healing_done"),
    ]
}

COUNT_METRICS = frozenset(k for k, m in METRICS.items() if m.unit == "count")

# Where a metric can come from, best first. "death_events" is the deduplicated set of
# timestamped deaths seen by any observer (unit death-state transitions and PLAYER_DEAD).
SOURCE_PRIORITY: dict[str, tuple[str, ...]] = {
    "deaths": ("native_damage_meter", "death_events"),
}
DEFAULT_SOURCE_PRIORITY = ("native_damage_meter",)

STATUS_RANK = {"observed": 0, "incomplete": 1, "estimated": 2, "unverified": 3, "unavailable": 4}
COVERAGE_RANK = {"complete_session": 0, "partial_session": 1, "unknown": 2}
