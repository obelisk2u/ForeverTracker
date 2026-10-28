"""Builders for addon-shaped observations used across the backend tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

T0 = 1_792_000_000  # 2026-10-15, inside the Forever beta window
MAP_ID = 990_001  # synthetic map ID (real Forever IDs are unknown until launch)


@dataclass
class Member:
    ref: str
    name: str
    surname: str | None
    guid: str | None
    class_file: str = "MAGE"
    race_file: str = "Human"
    level: int = 20
    role: str = "DAMAGER"
    presence: list[tuple[int, int | None]] | None = None
    identity_status: str = "ok"

    def as_dict(self, observer: bool, start: int, end: int) -> dict[str, Any]:
        presence = self.presence or [(start, end)]
        return {
            "ref": self.ref,
            "guid": self.guid,
            "name": self.name,
            "surname": self.surname,
            "identity_status": self.identity_status,
            "class_file": self.class_file,
            "race_file": self.race_file,
            "level": self.level,
            "role": self.role,
            "is_observer": observer,
            "presence": [{"start": s, "end": e} for s, e in presence],
        }


def party(prefix: str = "") -> list[Member]:
    return [
        Member("u1", "Autumn", "Redleaf", f"Player-4620-{prefix}0000A1", "MAGE", "Human", 18, "DAMAGER"),
        Member("u2", "Mah", "Beardlong", f"Player-4620-{prefix}0000A2", "WARRIOR", "Dwarf", 18, "TANK"),
        Member("u3", "Phineas", "Longhorn", f"Player-4620-{prefix}0000A3", "PRIEST", "Human", 17, "HEALER"),
        Member("u4", "Asha", "Brightvale", f"Player-4620-{prefix}0000A4", "ROGUE", "NightElf", 18, "DAMAGER"),
        Member("u5", "Thalen", "Brightvale", f"Player-4620-{prefix}0000A5", "HUNTER", "Dwarf", 19, "DAMAGER"),
    ]


@dataclass
class RunSpec:
    observation_id: str
    observer: str  # ref of the observing member
    members: list[Member] = field(default_factory=party)
    start: int = T0
    duration: int = 1800
    map_id: int = MAP_ID
    name: str = "Hall of Thanes"
    state: str = "completed"
    verified: bool = True
    revision: int = 1
    party_guid: str | None = None
    difficulty_id: int | None = 1
    deaths: dict[str, list[int]] = field(default_factory=dict)  # ref -> offsets
    meter: dict[str, dict[str, float]] | None = None  # ref -> metric -> value
    meter_status: str = "observed"
    meter_deaths: dict[str, int] | None = None
    sessions: int = 6
    combat_seconds: float = 900.0
    encounters: list[tuple[int, int, bool]] = field(default_factory=lambda: [(3001, 300, True), (3002, 900, True)])
    track_deaths: bool = True
    region_id: int = 1
    ruleset: str = "pve"


def default_meter(members: list[Member]) -> dict[str, dict[str, float]]:
    base = {"TANK": 300_000.0, "HEALER": 60_000.0, "DAMAGER": 540_000.0}
    return {
        m.ref: {
            "damage_done": base[m.role] + 1000 * i,
            "healing_done": 400_000.0 if m.role == "HEALER" else 5_000.0,
            "interrupts": float(i % 3),
            "damage_taken": 100_000.0,
        }
        for i, m in enumerate(members)
    }


def run_observation(spec: RunSpec) -> dict[str, Any]:
    start, end = spec.start, spec.start + spec.duration
    in_progress = spec.state == "in_progress"
    roster = [m.as_dict(m.ref == spec.observer, start, None if in_progress else end) for m in spec.members]
    observer = next(m for m in spec.members if m.ref == spec.observer)
    deaths = [
        {"unit_ref": ref, "at": start + off, "source": "unit_state"} for ref, offsets in spec.deaths.items() for off in offsets
    ]
    meter_values = spec.meter if spec.meter is not None else default_meter(spec.members)
    meter_deaths = spec.meter_deaths if spec.meter_deaths is not None else {r: len(v) for r, v in spec.deaths.items()}
    totals = []
    for m in spec.members:
        metrics = {k: {"value": v, "status": "observed", "sessions": spec.sessions} for k, v in meter_values.get(m.ref, {}).items()}
        metrics["deaths"] = {"value": float(meter_deaths.get(m.ref, 0)), "status": "observed", "sessions": spec.sessions}
        totals.append({"unit_ref": m.ref, "guid": m.guid, "name": m.name, "class_file": m.class_file, "metrics": metrics})
    death_entries = [
        {"unit_ref": ref, "session_id": 100 + i, "death_time_sec": 12.0, "death_recap_id": 5000 + i, "total": 1.0}
        for ref, n in meter_deaths.items()
        for i in range(n)
    ]
    return {
        "type": "dungeon_run",
        "observation_id": spec.observation_id,
        "revision": spec.revision,
        "recorded_by": {"guid": observer.guid, "name": observer.name, "surname": observer.surname},
        "namespace": {"region_id": spec.region_id, "region_name": "", "ruleset": spec.ruleset},
        "realm_label": "70",
        "client_build": "70532",
        "instance": {
            "map_id": spec.map_id,
            "name": spec.name,
            "instance_type": "party",
            "difficulty_id": spec.difficulty_id,
            "difficulty_name": "Normal",
            "max_players": 5,
        },
        "party_guid": spec.party_guid,
        "timing": {"started_at": start, "ended_at": None if in_progress else end, "last_updated_at": end, "clock": "server"},
        "state": spec.state,
        "completion": {
            "status": "verified" if spec.verified and spec.state == "completed" else "none",
            "evidence": [{"kind": "lfg_completion_reward", "at": end}] if spec.verified and spec.state == "completed" else [],
        },
        "timeline": [{"at": start, "kind": "entered", "detail": {}}],
        "roster": roster,
        "encounters": [
            {"encounter_id": eid, "name": f"Boss {eid}", "started_at": start + off, "ended_at": start + off + 90, "success": ok}
            for eid, off, ok in spec.encounters
        ],
        "deaths": deaths,
        "meter": {
            "status": spec.meter_status,
            "combat_seconds": spec.combat_seconds,
            "sessions": [{"session_id": 100 + i, "duration_sec": spec.combat_seconds / spec.sessions, "status": "captured"} for i in range(spec.sessions)],
            "totals": totals,
            "death_entries": death_entries,
        },
        "collection": {
            "identity": "active",
            "roster": "active",
            "encounters": "active",
            "deaths_unit_state": "active" if spec.track_deaths else "disabled",
            "meter": "active",
        },
        "flags": {},
    }


def batch(installation_id: str, observations: list[dict[str, Any]], *, synthetic: bool = True) -> dict[str, Any]:
    digest = hashlib.sha256((installation_id + json.dumps(observations, sort_keys=True)).encode()).hexdigest()
    return {
        "format": "forevertracker.batch",
        "schema_version": 1,
        "batch_id": f"test-{digest[:32]}",
        "installation_id": installation_id,
        "synthetic": synthetic,
        "addon": {"name": "ForeverTracker", "version": "0.1.0", "schema_version": 1},
        "client": {"game_version": "1.60.1", "build": "70532", "interface": 16001},
        "observations": observations,
    }
