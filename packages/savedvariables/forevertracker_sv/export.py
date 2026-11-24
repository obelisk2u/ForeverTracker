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
from forevertracker_sv.shapes import ShapeError, _position, normalize

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


def _as_list(value: Any, path: str, string_indices: bool) -> list[Any]:
    """A list of records. A Lua list with holes becomes a list; a table that is not a list is refused."""
    if value is None:
        return []
    if isinstance(value, dict):
        positions = {_position(k, string_indices): v for k, v in value.items()}
        if None in positions:
            raise ShapeError(path, "is not a list of records")
        value = [positions[i] for i in sorted(positions)]
    if not isinstance(value, list):
        raise SavedVariablesError(f"{path}: expected a list, found {type(value).__name__}")
    return value


@dataclass
class RejectedRecord:
    """A record left out of every batch, and why. The file it came from is never changed."""

    index: int | None
    observation_id: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"index": self.index, "observation_id": self.observation_id, "reason": self.reason}


@dataclass
class Extraction:
    batches: list[dict[str, Any]]
    rejected: list[RejectedRecord]
    skipped: int


def _load_db(parsed: dict[str, Any], string_indices: bool = False) -> dict[str, Any]:
    db = parsed.get(SV_GLOBAL)
    if not isinstance(db, dict):
        raise SavedVariablesError(f"{SV_GLOBAL} was not found; is this the ForeverTracker.lua SavedVariables file?")
    if any(not isinstance(k, str) for k in db):
        raise ShapeError(SV_GLOBAL, "mixes list positions with named fields")
    if db.get("format") != SV_FORMAT:
        raise SavedVariablesError(f"{SV_GLOBAL}.format is not {SV_FORMAT!r}")
    version = db.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SavedVariablesError(f"unsupported schema_version {version!r}")
    installation_id = db.get("installation_id")
    if not isinstance(installation_id, str) or not INSTALLATION_ID_RE.match(installation_id):
        raise SavedVariablesError("missing or malformed installation_id")
    return db


def _client(db: dict[str, Any], string_indices: bool) -> dict[str, Any]:
    client = db.get("client")
    if not isinstance(client, dict):
        return {}
    value = normalize(client, f"{SV_GLOBAL}.client", string_indices=string_indices)
    return value if isinstance(value, dict) else {}


def _collect_observations(
    db: dict[str, Any], include_active_run: bool, string_indices: bool = False
) -> tuple[list[dict[str, Any]], int, list[RejectedRecord]]:
    """The newest revision of every record, normalized. Records with an ambiguous table are rejected."""
    raw: list[tuple[int | None, Any]] = list(
        enumerate(_as_list(db.get("observations"), f"{SV_GLOBAL}.observations", string_indices), 1)
    )
    active = db.get("active_run")
    if include_active_run and isinstance(active, dict):
        raw.append((None, active))
    latest: dict[str, dict[str, Any]] = {}
    skipped = 0
    rejected: list[RejectedRecord] = []
    for index, obs in raw:
        if not isinstance(obs, dict):
            skipped += 1
            continue
        path = f"{SV_GLOBAL}.observations[{index}]" if index is not None else f"{SV_GLOBAL}.active_run"
        raw_id = obs.get("observation_id")
        try:
            obs = normalize(obs, path, string_indices=string_indices)
        except ShapeError as err:
            rejected.append(RejectedRecord(index, raw_id if isinstance(raw_id, str) else None, str(err)))
            continue
        if not isinstance(obs, dict):
            rejected.append(RejectedRecord(index, None, f"{path}: is a list, not a record"))
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
    return ordered, skipped, rejected


MAX_BATCH_BYTES = 4_000_000  # half the server's default upload limit (8 MB), leaving room for the envelope


def _encoded_size(observation: dict[str, Any]) -> int:
    """Bytes the observation takes in an upload (the uploader sends compact UTF-8 JSON)."""
    return len(json.dumps(observation, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _chunks(observations: list[dict[str, Any]], max_per_batch: int, max_batch_bytes: int) -> list[list[dict[str, Any]]]:
    """Consecutive chunks of at most ``max_per_batch`` records and, where records allow, ``max_batch_bytes``.

    A record larger than the byte budget on its own gets a batch to itself. Files whose chunks fit the budget
    are cut exactly as by count alone, so their batch IDs do not change.
    """
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for obs in observations:
        n = _encoded_size(obs)
        if current and (len(current) >= max_per_batch or size + n > max_batch_bytes):
            chunks.append(current)
            current, size = [], 0
        current.append(obs)
        size += n
    if current:
        chunks.append(current)
    return chunks


def extract(
    parsed: dict[str, Any],
    *,
    max_per_batch: int = 200,
    max_batch_bytes: int = MAX_BATCH_BYTES,
    include_active_run: bool = True,
    created_at: int | None = None,
    string_indices: bool = False,
) -> Extraction:
    """Canonical batches for every usable observation, plus the records left out and why.

    Batch IDs are derived from content, so extracting the same file twice yields the same
    batch IDs, and the server treats a re-upload as a duplicate. A batch holds at most
    ``max_per_batch`` records and, unless one record alone is larger, ``max_batch_bytes`` of them
    (raid-sized runs are hundreds of kilobytes each). ``string_indices`` is for the
    ``/ft export`` JSON string (see :mod:`forevertracker_sv.shapes`).
    """
    db = _load_db(parsed, string_indices)
    observations, skipped, rejected = _collect_observations(db, include_active_run, string_indices)
    installation_id: str = db["installation_id"]
    client = _client(db, string_indices)
    addon = {
        "name": "ForeverTracker",
        "version": str(db.get("addon_version", "unknown"))[:32],
        "schema_version": db["schema_version"],
    }
    batches: list[dict[str, Any]] = []
    for chunk in _chunks(observations, max_per_batch, max_batch_bytes):
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
    return Extraction(batches=batches, rejected=rejected, skipped=skipped)


def extract_batches(
    parsed: dict[str, Any],
    *,
    max_per_batch: int = 200,
    max_batch_bytes: int = MAX_BATCH_BYTES,
    include_active_run: bool = True,
    created_at: int | None = None,
    string_indices: bool = False,
) -> list[dict[str, Any]]:
    """The batches of :func:`extract` (records it rejects are left out)."""
    return extract(
        parsed,
        max_per_batch=max_per_batch,
        max_batch_bytes=max_batch_bytes,
        include_active_run=include_active_run,
        created_at=created_at,
        string_indices=string_indices,
    ).batches


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
    rejected_records: list[RejectedRecord] = field(default_factory=list)
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
        for record in self.rejected_records:
            lines.append(f"Not sent (unreadable record {record.observation_id or record.index}): {record.reason}")
        return lines


def summarize_export(parsed: dict[str, Any], *, string_indices: bool = False) -> ExportSummary:
    db = _load_db(parsed, string_indices)
    observations, skipped, rejected = _collect_observations(db, include_active_run=True, string_indices=string_indices)
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
            roster = obs.get("roster")
            for member in roster if isinstance(roster, list) else []:
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
        rejected_records=rejected,
        synthetic=bool(db.get("synthetic", False)),
    )


def _display_name(entry: dict[str, Any]) -> str:
    name = str(entry.get("name") or "?")
    surname = entry.get("surname")
    return f"{name} {surname}" if surname else name
