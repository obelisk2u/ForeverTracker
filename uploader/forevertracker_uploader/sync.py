"""One synchronisation pass: archive new file versions, extract batches, upload new ones."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from forevertracker_sv import SavedVariablesError, extract_batches, parse_savedvariables, summarize_export

from forevertracker_uploader import files
from forevertracker_uploader.client import UploadError, Uploader
from forevertracker_uploader.config import Config, State


@dataclass
class SyncReport:
    files_seen: int = 0
    new_versions: int = 0
    batches_uploaded: int = 0
    batches_skipped: int = 0
    observations: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    paused: bool = False

    def summary(self) -> str:
        if self.paused:
            return "paused"
        parts = [f"{self.batches_uploaded} batch(es) uploaded", f"{self.new_versions} new file version(s)"]
        if self.observations:
            parts.append(", ".join(f"{n} {k}" for k, n in sorted(self.observations.items())))
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        return "; ".join(parts)


def _versions_to_process(home: Path, cfg: Config, state: State, report: SyncReport, sleep) -> list[tuple[str, bytes]]:
    pending: list[tuple[str, bytes]] = []
    for path in files.find_savedvariables(cfg.wow_paths):
        report.files_seen += 1
        if not files.is_stable(path, cfg.stability_seconds, sleep=sleep):
            report.errors.append(f"{path}: still being written; will retry")
            continue
        data = files.read_bytes(path)
        digest = files.sha256(data)
        if digest not in state.versions:
            files.archive(home, data, digest)
            state.versions[digest] = {"source": str(path), "archived_at": time.time(), "processed": False}
            report.new_versions += 1
        if not state.versions[digest]["processed"]:
            pending.append((digest, data))
    if cfg.upload_archived_versions:
        # Versions archived earlier but not yet uploaded (e.g. the server was unreachable).
        for digest, info in state.versions.items():
            if not info["processed"] and all(d != digest for d, _ in pending):
                archived = home / "archive" / f"{digest}.lua"
                if archived.exists():
                    pending.append((digest, archived.read_bytes()))
    return pending


def sync_once(home: Path, cfg: Config, state: State, uploader: Uploader, *, sleep=time.sleep) -> SyncReport:
    report = SyncReport()
    if cfg.paused:
        report.paused = True
        return report
    for digest, data in _versions_to_process(home, cfg, state, report, sleep):
        try:
            batches = extract_batches(parse_savedvariables(data))
        except SavedVariablesError as err:
            report.errors.append(f"version {digest[:12]}: {err}")
            state.versions[digest]["processed"] = True  # malformed files are not retried
            state.versions[digest]["error"] = str(err)
            continue
        complete = True
        for batch in batches:
            if batch["batch_id"] in state.uploaded_batches:
                report.batches_skipped += 1
                continue
            try:
                result = uploader.upload_batch(json.dumps(batch, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
            except UploadError as err:
                report.errors.append(str(err))
                if err.permanent:
                    state.uploaded_batches[batch["batch_id"]] = "rejected"
                else:
                    complete = False
                continue
            state.uploaded_batches[batch["batch_id"]] = result.get("status", "unknown")
            report.batches_uploaded += 1
            for obs in result.get("observations", []):
                report.observations[obs["status"]] = report.observations.get(obs["status"], 0) + 1
        if complete:
            state.versions[digest]["processed"] = True
    state.last_sync_at = time.time()
    state.last_sync_result = report.summary()
    state.last_error = report.errors[-1] if report.errors else None
    return report


def disclose(cfg: Config) -> list[str]:
    """Describe exactly what the next sync would send, without sending anything."""
    lines: list[str] = []
    paths = files.find_savedvariables(cfg.wow_paths)
    if not paths:
        return ["No ForeverTracker.lua file found. Run `setup --wow <folder>` first."]
    for path in paths:
        lines.append(f"File: {path}")
        try:
            parsed = parse_savedvariables(files.read_bytes(path))
            summary = summarize_export(parsed)
            batches = extract_batches(parsed)
        except SavedVariablesError as err:
            lines.append(f"  Cannot read it: {err}")
            continue
        lines += [f"  {line}" for line in summary.disclosure_lines()]
        names = ", ".join(summary.characters_observed[:20])
        more = len(summary.characters_observed) - 20
        lines.append(f"  Characters named: {names}{f' (+{more} more)' if more > 0 else ''}")
        lines.append(f"  Would send {len(batches)} batch(es) to {cfg.server_url}")
    return lines
