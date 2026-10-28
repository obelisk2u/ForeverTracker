"""Metric candidates and conflict resolution.

Each observation contributes *candidates* (stored verbatim in ``metric_observations``). For each
(participant, metric) the candidates are resolved into one public value
(``participant_metrics``) according to these rules:

1. Only ``observed``/``incomplete`` candidates with a value can be chosen. Unavailable or secret
   data never becomes a number: the metric is published as ``unavailable`` with no value.
2. Better-scoped evidence wins: complete-session coverage beats partial coverage, then status,
   then source priority (``definitions.SOURCE_PRIORITY``), then coverage ratio.
3. Within the winning tier, agreeing values from two or more distinct contributors are
   ``corroborated``. Disagreeing values are ``conflicted``: the best-covered value is shown with
   low confidence and every candidate is listed in ``conflict``.
4. A disagreement between *sources* (meter vs death events) is resolved by source priority and
   marked ``conflict_resolved`` so it stays visible.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime

from app.analytics.definitions import (
    COMPLETE_COVERAGE_RATIO,
    COUNT_METRICS,
    COVERAGE_RANK,
    DEFAULT_SOURCE_PRIORITY,
    METRICS,
    SOURCE_PRIORITY,
    STATUS_RANK,
)
from app.schemas.observations import DungeonRunObservation


@dataclass
class Candidate:
    character_id: int
    metric: str
    value: float | None
    source: str
    status: str
    coverage: str
    coverage_ratio: float | None
    combat_seconds: float | None
    contributor_ids: frozenset[int]
    raw_observation_id: int
    collected_at: datetime
    details: dict = field(default_factory=dict)

    @property
    def unit(self) -> str:
        return METRICS[self.metric].unit


@dataclass
class Resolved:
    character_id: int
    metric: str
    value: float | None
    source: str
    status: str
    coverage: str
    resolution: str
    confidence: str
    candidate_count: int
    contributor_count: int
    combat_seconds: float | None
    conflict: dict | None
    derived: bool = False


def interval_union_seconds(intervals: list[tuple[datetime, datetime]]) -> float:
    total = 0.0
    cur_start = cur_end = None
    for start, end in sorted(intervals):
        if cur_end is None or start > cur_end:
            if cur_end is not None:
                total += (cur_end - cur_start).total_seconds()
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    if cur_end is not None:
        total += (cur_end - cur_start).total_seconds()
    return total


def intersect_union_seconds(a: list[tuple[datetime, datetime]], b: list[tuple[datetime, datetime]]) -> float:
    pieces = []
    for s1, e1 in a:
        for s2, e2 in b:
            s, e = max(s1, s2), min(e1, e2)
            if e > s:
                pieces.append((s, e))
    return interval_union_seconds(pieces)


def meter_candidates(
    obs: DungeonRunObservation,
    *,
    raw_observation_id: int,
    contributor_id: int,
    ref_to_char: dict[str, int],
    observer_coverage_ratio: float,
    collected_at: datetime,
    death_interpretation: str,
) -> list[Candidate]:
    meter = obs.meter
    if meter is None or meter.status in ("unavailable", "disabled"):
        return []
    seen = len(meter.sessions)
    captured = sum(1 for s in meter.sessions if s.status == "captured")
    session_ratio = captured / seen if seen else 0.0
    complete = (
        meter.status == "observed" and seen > 0 and captured == seen and observer_coverage_ratio >= COMPLETE_COVERAGE_RATIO
    )
    coverage = "complete_session" if complete else "partial_session"
    guid_to_ref = {m.guid: m.ref for m in obs.roster if m.guid}

    death_counts: dict[str, int] = {}
    for entry in meter.death_entries:
        ref = entry.unit_ref or guid_to_ref.get(entry.guid or "")
        if ref:
            death_counts[ref] = death_counts.get(ref, 0) + 1

    out: list[Candidate] = []
    for totals in meter.totals:
        ref = totals.unit_ref or guid_to_ref.get(totals.guid or "")
        character_id = ref_to_char.get(ref) if ref else None
        if character_id is None:
            continue
        for metric, mv in totals.metrics.items():
            if mv.status == "observed":
                status = "observed" if complete else "incomplete"
                value = mv.value
            elif mv.status == "partial":
                status, value = "incomplete", mv.value
            else:
                status, value = "unavailable", None
            details = {"sessions": mv.sessions, "sessions_seen": seen, "sessions_captured": captured, "raw_status": mv.status}
            if metric == "deaths" and status != "unavailable":
                details["total_amount"] = mv.value
                details["death_entries"] = death_counts.get(ref, 0)
                details["interpretation"] = death_interpretation
                if death_interpretation == "entry_per_death":
                    value = float(death_counts.get(ref, 0))
            out.append(
                Candidate(
                    character_id=character_id,
                    metric=metric,
                    value=value,
                    source="native_damage_meter",
                    status=status,
                    coverage=coverage,
                    coverage_ratio=round(observer_coverage_ratio * session_ratio, 4),
                    combat_seconds=meter.combat_seconds,
                    contributor_ids=frozenset({contributor_id}),
                    raw_observation_id=raw_observation_id,
                    collected_at=collected_at,
                    details=details,
                )
            )
    return out


def _agree(metric: str, values: list[float], tolerance: float) -> bool:
    if metric in COUNT_METRICS:
        return len({round(v) for v in values}) == 1
    lo, hi = min(values), max(values)
    return hi == 0 or (hi - lo) / hi <= tolerance


def _rank_key(c: Candidate) -> tuple:
    priority = SOURCE_PRIORITY.get(c.metric, DEFAULT_SOURCE_PRIORITY)
    source_rank = priority.index(c.source) if c.source in priority else len(priority)
    return (
        COVERAGE_RANK.get(c.coverage, 9),
        STATUS_RANK.get(c.status, 9),
        source_rank,
        -(c.coverage_ratio or 0.0),
        -(c.combat_seconds or 0.0),
    )


def resolve(candidates: list[Candidate], tolerance: float) -> Resolved | None:
    if not candidates:
        return None
    first = candidates[0]
    usable = [c for c in candidates if c.status in ("observed", "incomplete") and c.value is not None]
    all_contributors = frozenset().union(*(c.contributor_ids for c in candidates))
    if not usable:
        return Resolved(
            character_id=first.character_id,
            metric=first.metric,
            value=None,
            source=first.source,
            status="unavailable",
            coverage="unknown",
            resolution="single_source",
            confidence="low",
            candidate_count=len(candidates),
            contributor_count=len(all_contributors),
            combat_seconds=None,
            conflict=None,
        )
    usable.sort(key=_rank_key)
    best = usable[0]
    tier = [c for c in usable if c.coverage == best.coverage and c.status == best.status and c.source == best.source]
    tier_contributors = frozenset().union(*(c.contributor_ids for c in tier))
    values = [c.value for c in tier]
    conflict: dict | None = None
    if _agree(best.metric, values, tolerance):
        value = statistics.median(values)
        if len(tier_contributors) >= 2:
            resolution = "corroborated"
            confidence = "high" if best.coverage == "complete_session" and best.status == "observed" else "medium"
        else:
            resolution = "single_source"
            confidence = "medium" if best.coverage == "complete_session" and best.status == "observed" else "low"
    else:
        value = best.value
        resolution = "conflicted"
        confidence = "low"
        conflict = {
            "reason": "observers_disagree",
            "spread": [min(values), max(values)],
            "candidates": [_describe(c) for c in tier],
        }

    # Cross-check against the best candidate from a different source (e.g. meter deaths vs
    # death events). Agreement raises measurement confidence; it does not make the value
    # "corroborated", which requires independent contributors.
    others = [c for c in usable if c.source != best.source and c.coverage == best.coverage]
    if others and resolution != "conflicted":
        other_best = sorted(others, key=_rank_key)[0]
        if not _agree(best.metric, [value, other_best.value], tolerance):
            resolution = "conflict_resolved"
            confidence = "low" if confidence == "low" else "medium"
            conflict = {
                "reason": "sources_disagree",
                "chosen_source": best.source,
                "candidates": [_describe(best), _describe(other_best)],
            }
        elif best.coverage == "complete_session" and best.status == "observed":
            confidence = "high"

    return Resolved(
        character_id=best.character_id,
        metric=best.metric,
        value=value,
        source=best.source,
        status=best.status,
        coverage=best.coverage,
        resolution=resolution,
        confidence=confidence,
        candidate_count=len(candidates),
        contributor_count=len(tier_contributors),
        combat_seconds=best.combat_seconds,
        conflict=conflict,
    )


def _describe(c: Candidate) -> dict:
    return {
        "value": c.value,
        "source": c.source,
        "status": c.status,
        "coverage": c.coverage,
        "coverage_ratio": c.coverage_ratio,
        "observation": c.raw_observation_id,
    }


def derive_rate(base: Resolved, metric: str) -> Resolved | None:
    """dps/hps from a resolved total and the combat seconds of the same evidence."""
    if base.value is None or not base.combat_seconds or base.combat_seconds <= 0:
        return None
    return Resolved(
        character_id=base.character_id,
        metric=metric,
        value=base.value / base.combat_seconds,
        source=base.source,
        status=base.status,
        coverage=base.coverage,
        resolution=base.resolution,
        confidence=base.confidence,
        candidate_count=base.candidate_count,
        contributor_count=base.contributor_count,
        combat_seconds=base.combat_seconds,
        conflict=base.conflict,
        derived=True,
    )
