"""A single-instance lock, so starting at boot and a manual launch cannot run two copies.

The lock is an exclusive OS lock on a file in the uploader's home directory. It is held for
the life of the process and released automatically when the process exits (even on a crash),
so a stale lock never blocks the next start.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO


class AlreadyRunning(Exception):
    """Another uploader instance already holds the lock."""


class SingleInstance:
    def __init__(self, home: Path):
        self._path = home / "uploader.lock"
        self._fh: IO[str] | None = None

    def acquire(self) -> "SingleInstance":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self._path, "a+", encoding="utf-8")
        try:
            _lock(fh)
        except OSError as err:
            fh.close()
            raise AlreadyRunning(f"another ForeverTracker uploader is already running ({self._path})") from err
        self._fh = fh
        return self

    def release(self) -> None:
        if self._fh is not None:
            try:
                _unlock(self._fh)
            finally:
                self._fh.close()
                self._fh = None

    def __enter__(self) -> "SingleInstance":
        return self.acquire()

    def __exit__(self, *_exc) -> None:
        self.release()


if sys.platform == "win32":
    import msvcrt

    def _lock(fh: IO[str]) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(fh: IO[str]) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fh: IO[str]) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fh: IO[str]) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
