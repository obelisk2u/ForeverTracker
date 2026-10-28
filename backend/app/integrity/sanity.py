"""Plausibility checks for untrusted observations.

Schema validation (app/schemas/observations.py) guarantees shape. These checks look at
meaning and return two lists:

* ``reject``: internally inconsistent records (end before start, unknown unit references).
  They are never stored as accepted.
* ``quarantine``: records that are well-formed but implausible (future timestamps,
  impossible levels or damage). They are stored with status ``quarantined``, excluded from
  every public view, and wait for review.

A passing check does not make an observation *true*. Uploads are self-reported (see
docs/DATA_INTEGRITY.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings
from app.schemas.observations import (
    CharacterSnapshotObservation,
    DungeonRunObservation,
    Observation,
    ProbeReportObservation,
)

MAX_RUN_SECONDS = 6 * 3600
WINDOW_PADDING = 600
MAX_PLAUSIBLE_DPS = 60_000.0
MAX_PLAUSIBLE_HPS = 60_000.0
MAX_COUNT_PER_RUN = {"interrupts": 1500, "dispels": 1500, "deaths": 60}
MAX_DEATH_EVENTS_PER_UNIT = 60


@dataclass
class SanityResult:
    reject: list[str] = field(default_factory=list)
    quarantine: list[str] = field(default_factory=list)


def _max_concurrent(intervals: list[tuple[int, int]]) -> int:
    events: list[tuple[int, int]] = []
    for start, end in intervals:
        events.append((start, 1))
        events.append((end, -1))
    best = current = 0
    for _, delta in sorted(events, key=lambda e: (e[0], e[1])):
        current += delta
        best = max(best, current)
    return best


def _check_time(value: int | None, label: str, settings: Settings, now: int, out: SanityResult) -> None:
    if value is None:
        return
    if value < settings.earliest_valid_timestamp:
        out.quarantine.append(f"{label}_before_forever")
    if value > now + settings.max_future_skew_seconds:
        out.quarantine.append(f"{label}_in_future")


def _check_run(obs: DungeonRunObservation, settings: Settings, now: int, out: SanityResult) -> None:
    t = obs.timing
    _check_time(t.started_at, "started_at", settings, now, out)
    _check_time(t.ended_at, "ended_at", settings, now, out)
    _check_time(t.last_updated_at, "last_updated_at", settings, now, out)
    if t.ended_at is not None and t.ended_at < t.started_at:
        out.reject.append("ended_before_started")
    if t.last_updated_at < t.started_at:
        out.reject.append("updated_before_started")
    end = t.ended_at if t.ended_at is not None else t.last_updated_at
    if end - t.started_at > MAX_RUN_SECONDS:
        out.quarantine.append("implausible_run_duration")
    lo, hi = t.started_at - WINDOW_PADDING, end + WINDOW_PADDING

    if obs.state == "completed" and obs.completion.status != "verified":
        out.quarantine.append("completed_without_evidence")
    if obs.completion.status == "verified" and not obs.completion.evidence:
        out.reject.append("verified_completion_without_evidence")

    refs = [m.ref for m in obs.roster]
    if len(set(refs)) != len(refs):
        out.reject.append("duplicate_roster_ref")
    guids = [m.guid for m in obs.roster if m.guid]
    if len(set(guids)) != len(guids):
        out.reject.append("duplicate_roster_guid")
    observers = [m for m in obs.roster if m.is_observer]
    if len(observers) != 1:
        out.quarantine.append("observer_not_unique")
    else:
        me, rec = observers[0], obs.recorded_by
        if (me.guid and rec.guid and me.guid != rec.guid) or (me.name and rec.name and me.name != rec.name):
            out.quarantine.append("observer_mismatch")

    intervals: list[tuple[int, int]] = []
    for member in obs.roster:
        if member.level is not None and member.level > settings.max_character_level:
            out.quarantine.append("level_above_cap")
        for p in member.presence:
            p_end = p.end if p.end is not None else end
            if p_end < p.start:
                out.reject.append("presence_ends_before_start")
            if p.start < lo or p_end > hi:
                out.quarantine.append("presence_outside_run")
            intervals.append((p.start, p_end))
    limit = obs.instance.max_players or (5 if obs.instance.instance_type == "party" else 40)
    if intervals and _max_concurrent(intervals) > limit:
        out.quarantine.append("too_many_concurrent_members")

    for enc in obs.encounters:
        if enc.ended_at is not None and enc.ended_at < enc.started_at:
            out.reject.append("encounter_ends_before_start")
        if enc.started_at < lo or enc.started_at > hi:
            out.quarantine.append("encounter_outside_run")

    ref_set = set(refs)
    per_unit: dict[str, int] = {}
    for death in obs.deaths:
        if death.unit_ref not in ref_set:
            out.reject.append("death_unknown_unit")
            continue
        per_unit[death.unit_ref] = per_unit.get(death.unit_ref, 0) + 1
        if death.at < lo or death.at > hi:
            out.quarantine.append("death_outside_run")
    if any(n > MAX_DEATH_EVENTS_PER_UNIT for n in per_unit.values()):
        out.quarantine.append("implausible_death_count")

    meter = obs.meter
    if meter is not None:
        combat = meter.combat_seconds
        if combat is not None and combat > (end - t.started_at) + 120:
            out.quarantine.append("meter_combat_longer_than_run")
        for totals in meter.totals:
            if totals.unit_ref is not None and totals.unit_ref not in ref_set:
                out.quarantine.append("meter_unit_unknown")
            for metric, mv in totals.metrics.items():
                if mv.value is None:
                    continue
                cap = MAX_COUNT_PER_RUN.get(metric)
                if cap is not None and mv.value > cap:
                    out.quarantine.append(f"implausible_{metric}")
                if combat and combat > 0:
                    if metric == "damage_done" and mv.value / combat > MAX_PLAUSIBLE_DPS:
                        out.quarantine.append("implausible_dps")
                    if metric == "healing_done" and mv.value / combat > MAX_PLAUSIBLE_HPS:
                        out.quarantine.append("implausible_hps")
        for entry in meter.death_entries:
            if entry.unit_ref is not None and entry.unit_ref not in ref_set:
                out.quarantine.append("meter_unit_unknown")


def _check_snapshot(obs: CharacterSnapshotObservation, settings: Settings, now: int, out: SanityResult) -> None:
    _check_time(obs.observed_at, "observed_at", settings, now, out)
    if obs.subject.level is not None and obs.subject.level > settings.max_character_level:
        out.quarantine.append("level_above_cap")
    if obs.equipment is not None:
        slots = [i.slot for i in obs.equipment.items]
        if len(set(slots)) != len(slots):
            out.reject.append("duplicate_equipment_slot")
        if obs.equipment.average_item_level is not None and obs.equipment.average_item_level > 1000:
            out.quarantine.append("implausible_item_level")


def check_observation(obs: Observation, settings: Settings, now: int) -> SanityResult:
    out = SanityResult()
    if isinstance(obs, DungeonRunObservation):
        _check_run(obs, settings, now, out)
    elif isinstance(obs, CharacterSnapshotObservation):
        _check_snapshot(obs, settings, now, out)
    elif isinstance(obs, ProbeReportObservation):
        _check_time(obs.observed_at, "observed_at", settings, now, out)
    out.reject = sorted(set(out.reject))
    out.quarantine = sorted(set(out.quarantine))
    return out
