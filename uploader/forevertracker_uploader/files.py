"""Finding, reading and archiving SavedVariables files. Read-only toward the game folder."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import time
from pathlib import Path

SV_NAME = "ForeverTracker.lua"

DEFAULT_ROOTS = {
    "win32": [r"C:\Program Files (x86)\World of Warcraft", r"C:\Program Files\World of Warcraft"],
    "darwin": ["/Applications/World of Warcraft"],
}


def candidate_roots() -> list[Path]:
    return [Path(p) for p in DEFAULT_ROOTS.get(sys.platform, []) if Path(p).is_dir()]


def find_savedvariables(paths: list[str] | list[Path]) -> list[Path]:
    """Return ForeverTracker.lua files under the given game folders (or explicit files).

    Accepts the install root (``World of Warcraft``), a flavor folder (``_forever_``)
    or a direct path to the file. Only looks in WTF/Account/*/SavedVariables.
    """
    found: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_file() and p.name == SV_NAME:
            found.append(p)
            continue
        if not p.is_dir():
            continue
        flavors = [p] if (p / "WTF").is_dir() else [d for d in p.iterdir() if d.is_dir() and d.name.startswith("_")]
        for flavor in flavors:
            for sv in (flavor / "WTF" / "Account").glob(f"*/SavedVariables/{SV_NAME}"):
                found.append(sv)
    return sorted(set(found))


def is_stable(path: Path, seconds: float, *, sleep=time.sleep, now=time.time) -> bool:
    """True when the file has not changed for `seconds` (WoW may be writing it right now)."""
    try:
        first = path.stat()
    except FileNotFoundError:
        return False
    if now() - first.st_mtime < seconds:
        sleep(seconds - (now() - first.st_mtime))
    try:
        second = path.stat()
    except FileNotFoundError:
        return False
    return (first.st_size, first.st_mtime_ns) == (second.st_size, second.st_mtime_ns)


def read_bytes(path: Path) -> bytes:
    # Plain read-only open; never takes a write lock on the game's file.
    with open(path, "rb") as f:
        return f.read()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive(home: Path, data: bytes, digest: str) -> Path:
    """Keep a private copy of this file version (outside the WoW folder)."""
    target = home / "archive" / f"{digest}.lua"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
    return target


def purge_archive(home: Path) -> None:
    shutil.rmtree(home / "archive", ignore_errors=True)
