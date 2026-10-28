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
