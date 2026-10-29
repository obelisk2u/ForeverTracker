"""The windowless background mode: start at login, upload each run as the game saves it, idle
cheaply the rest of the time.

It watches the SavedVariables file's modification time. WoW rewrites that file on logout, exit
and /reload, so a change is exactly the moment there is something new to send; between those
moments the loop only stats a file every few seconds. It never crashes the loop on an error, and
a single-instance lock means a manual launch and the login launch cannot both run. Once a day it
also checks for a newer version of itself (update.py) and exits when the installer takes over.

No window, but not hidden: on Windows a tray icon (tray.py) shows it is running and offers Quit, and
autostart.py explains why start-with-Windows uses the visible Run key.
"""

from __future__ import annotations

import logging
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from forevertracker_uploader import files
from forevertracker_uploader.client import Uploader
from forevertracker_uploader.config import Config, State
from forevertracker_uploader.singleinstance import AlreadyRunning, SingleInstance
from forevertracker_uploader.sync import SyncReport, sync_once

log = logging.getLogger("forevertracker.uploader.background")


def configure_logging(home: Path, *, max_bytes: int = 1_000_000) -> None:
    home.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(home / "uploader.log", maxBytes=max_bytes, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger("forevertracker.uploader")
    root.setLevel(logging.INFO)
    root.handlers = [handler]


def sync_now(home: Path, *, uploader_factory=None) -> SyncReport:
    """One upload pass, building the HTTP client from the saved server URL."""
    cfg, state = Config.load(home), State.load(home)
    if cfg.paused:
        return SyncReport(paused=True)
    make = uploader_factory or (lambda url: Uploader(url))
    uploader = make(cfg.server_url)
    try:
        return sync_once(home, cfg, state, uploader)
    finally:
        try:
            uploader.close()
        finally:
            state.save(home)


def _mtimes(cfg: Config) -> dict[str, float]:
    result: dict[str, float] = {}
    for p in files.find_savedvariables(cfg.wow_paths):
        try:
            result[str(p)] = p.stat().st_mtime
        except OSError:
            pass
    return result


def run_background(
    home: Path,
    *,
    iterations: int | None = None,
    sleep=time.sleep,
    uploader_factory=None,
    retry_every: int = 30,
    updater=None,
    update_every: float = 24 * 3600,
    clock=time.monotonic,
    stop: threading.Event | None = None,
    single_instance: bool = True,
) -> int:
    """Run the background loop. ``iterations`` caps the loop for tests (None = until stopped).

    ``updater(home, config)`` runs at start and then every ``update_every`` seconds; when it returns
    True an installer has taken over and the loop stops. Setting ``stop`` (the tray icon's Quit) ends
    the loop at once instead of after the current wait. ``single_instance=False`` is for a caller that
    already holds the lock. Returns the number of passes that uploaded at least one batch.
    """
    lock = None
    if single_instance:
        try:
            lock = SingleInstance(home).acquire()
        except AlreadyRunning as err:
            log.info("not starting: %s", err)
            return 0

    uploaded_passes = 0
    last: dict[str, float] = {}
    first = True
    idle = 0
    next_update = clock()
    try:
        i = 0
        while (iterations is None or i < iterations) and not (stop and stop.is_set()):
            i += 1
            try:
                cfg = Config.load(home)
                if cfg.paused:
                    last = {}
                else:
                    current = _mtimes(cfg)
                    # Sync on the first pass (catch anything saved while we were off), whenever a
                    # watched file changes, and periodically so a failed upload is retried later.
                    due_retry = idle >= max(retry_every, 1)
                    if first or current != last or due_retry:
                        report = sync_now(home, uploader_factory=uploader_factory)
                        last = current
                        idle = 0
                        if report.batches_uploaded:
                            uploaded_passes += 1
                        if report.batches_uploaded or report.errors:
                            log.info("sync: %s", report.summary())
                    else:
                        idle += 1
                    first = False
            except Exception:  # noqa: BLE001 - a background loop must never die on one bad pass
                log.exception("sync pass failed; continuing")
            if updater is not None and clock() >= next_update:
                next_update = clock() + update_every
                try:
                    if updater(home, Config.load(home)):
                        log.info("exiting so the installer can replace this version")
                        break
                except Exception:  # noqa: BLE001 - a failed update check must not stop uploads
                    log.exception("update check failed; trying again later")
            if iterations is None or i < iterations:
                poll = Config.load(home).poll_seconds
                wait = poll if poll and poll > 0 else 10.0
                stop.wait(wait) if stop is not None else sleep(wait)
    finally:
        if lock is not None:
            lock.release()
    return uploaded_passes
