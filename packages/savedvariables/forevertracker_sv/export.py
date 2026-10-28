"""Turn a parsed ``ForeverTrackerDB`` SavedVariable into canonical upload batches.

This module performs *structural* extraction only. Field-level validation of every
observation happens on the server (``backend/app/schemas/observations.py``), because the
server must treat every upload as untrusted regardless of which client produced it.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from forevertracker_sv.errors import SavedVariablesError

SV_GLOBAL = "ForeverTrackerDB"
SV_FORMAT = "forevertracker.savedvariables"
BATCH_FORMAT = "forevertracker.batch"
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})
INSTALLATION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def canonical_json(value: Any) -> str:
    """Deterministic JSON used for digests on both the uploader and the server."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def observations_digest(installation_id: str, observations: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    h.update(installation_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(canonical_json(observations).encode("utf-8"))
    return h.hexdigest()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        # A sparse Lua array (e.g. after a manual edit) arrives as a dict of int keys.
        int_keys = sorted(k for k in value if isinstance(k, int))
        return [value[k] for k in int_keys]
    raise SavedVariablesError(f"expected a list, found {type(value).__name__}")


def _load_db(parsed: dict[str, Any]) -> dict[str, Any]:
    db = parsed.get(SV_GLOBAL)
    if not isinstance(db, dict):
        raise SavedVariablesError(f"{SV_GLOBAL} was not found; is this the ForeverTracker.lua SavedVariables file?")
    if db.get("format") != SV_FORMAT:
        raise SavedVariablesError(f"{SV_GLOBAL}.format is not {SV_FORMAT!r}")
    version = db.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SavedVariablesError(f"unsupported schema_version {version!r}")
    installation_id = db.get("installation_id")
    if not isinstance(installation_id, str) or not INSTALLATION_ID_RE.match(installation_id):
        raise SavedVariablesError("missing or malformed installation_id")
    return db


def _collect_observations(db: dict[str, Any], include_active_run: bool) -> tuple[list[dict[str, Any]], int]:
    raw = _as_list(db.get("observations"))
    active = db.get("active_run")
    if include_active_run and isinstance(active, dict):
        raw = [*raw, active]
    latest: dict[str, dict[str, Any]] = {}
    skipped = 0
    for obs in raw:
        if not isinstance(obs, dict):
            skipped += 1
            continue
        oid = obs.get("observation_id")
        rev = obs.get("revision")
        if not isinstance(oid, str) or not isinstance(rev, int):
            skipped += 1
            continue
        current = latest.get(oid)
        if current is None or rev > current["revision"]:
            latest[oid] = obs
    ordered = sorted(latest.values(), key=lambda o: (str(o.get("type")), o["observation_id"]))
    return ordered, skipped


def extract_batches(
    parsed: dict[str, Any],
    *,
    max_per_batch: int = 200,
    include_active_run: bool = True,
    created_at: int | None = None,
) -> list[dict[str, Any]]:
    """Return canonical batches for every observation in the export.

    Batch IDs are derived from content, so extracting the same file twice yields the same
    batch IDs, and the server treats a re-upload as a duplicate.
    """
    db = _load_db(parsed)
    observations, _ = _collect_observations(db, include_active_run)
    installation_id: str = db["installation_id"]
    client = db.get("client") if isinstance(db.get("client"), dict) else {}
    addon = {
        "name": "ForeverTracker",
        "version": str(db.get("addon_version", "unknown"))[:32],
        "schema_version": db["schema_version"],
    }
    batches: list[dict[str, Any]] = []
    for start in range(0, len(observations), max_per_batch):
        chunk = observations[start : start + max_per_batch]
        digest = observations_digest(installation_id, chunk)
        batches.append(
            {
                "format": BATCH_FORMAT,
                "schema_version": db["schema_version"],
                "batch_id": f"sv-{digest[:40]}",
                "installation_id": installation_id,
                "created_at": created_at,
                "synthetic": bool(db.get("synthetic", False)),
                "addon": addon,
                "client": client,
                "observations": chunk,
            }
        )
    return batches


@dataclass
class ExportSummary:
    """What a ForeverTracker export contains, for disclosure before upload."""

    installation_id: str
    addon_version: str
    observation_counts: dict[str, int] = field(default_factory=dict)
    dungeon_runs: int = 0
    in_progress_runs: int = 0
    characters_observed: list[str] = field(default_factory=list)
    observers: list[str] = field(default_factory=list)
    earliest: int | None = None
    latest: int | None = None
    skipped_records: int = 0
    synthetic: bool = False

    def disclosure_lines(self) -> list[str]:
        lines = [
            f"Installation ID (random, created by the addon): {self.installation_id}",
            f"Dungeon runs: {self.dungeon_runs} ({self.in_progress_runs} still in progress)",
            f"Character/equipment snapshots: {self.observation_counts.get('character_snapshot', 0)}",
            f"Diagnostic probe reports: {self.observation_counts.get('probe_report', 0)}",
            f"Characters named in these records: {len(self.characters_observed)}",
            "Each record contains only what the game client showed the addon: character names, class,"
            " race, level, group role, dungeon, timestamps, boss encounters, deaths, native damage-meter"
            " totals and inspected equipment.",
            "It contains no account name, Battle.net ID, chat, IP address or real name.",
        ]
        if self.synthetic:
            lines.append("This file is marked SYNTHETIC (development data).")
        return lines


def summarize_export(parsed: dict[str, Any]) -> ExportSummary:
    db = _load_db(parsed)
    observations, skipped = _collect_observations(db, include_active_run=True)
    counts = Counter(str(o.get("type")) for o in observations)
    names: set[str] = set()
    observers: set[str] = set()
    times: list[int] = []
    in_progress = 0
    for obs in observations:
        rec = obs.get("recorded_by")
        if isinstance(rec, dict):
            observers.add(_display_name(rec))
        if obs.get("type") == "dungeon_run":
            if obs.get("state") == "in_progress":
                in_progress += 1
            for member in _as_list(obs.get("roster")):
                if isinstance(member, dict) and member.get("name"):
                    names.add(_display_name(member))
            timing = obs.get("timing") if isinstance(obs.get("timing"), dict) else {}
            for key in ("started_at", "ended_at"):
                if isinstance(timing.get(key), int):
                    times.append(timing[key])
        elif obs.get("type") == "character_snapshot":
            subject = obs.get("subject")
            if isinstance(subject, dict) and subject.get("name"):
                names.add(_display_name(subject))
            if isinstance(obs.get("observed_at"), int):
                times.append(obs["observed_at"])
    return ExportSummary(
        installation_id=db["installation_id"],
        addon_version=str(db.get("addon_version", "unknown")),
        observation_counts=dict(counts),
        dungeon_runs=counts.get("dungeon_run", 0),
        in_progress_runs=in_progress,
        characters_observed=sorted(names),
        observers=sorted(observers),
        earliest=min(times) if times else None,
        latest=max(times) if times else None,
        skipped_records=skipped,
        synthetic=bool(db.get("synthetic", False)),
    )


def _display_name(entry: dict[str, Any]) -> str:
    name = str(entry.get("name") or "?")
    surname = entry.get("surname")
    return f"{name} {surname}" if surname else name
