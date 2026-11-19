"""Keeping the ForeverTracker addon up to date (packaged Windows app).

The installer leaves a copy of the addon it carries in the app's own folder (``addon\\ForeverTracker``
next to the exe). When that copy is newer than the addon in a game folder, the app replaces the
game's ``Interface\\AddOns\\ForeverTracker`` folder with it:

* only while the game is closed (no program from the game folder is running), so a /reload can never
  load half the files, and the new version loads at the next start;
* only where the addon is installed: one the player removed is never put back;
* never with an older or equal version (by ``## Version`` in ForeverTracker.toc);
* nothing else in the game folder is touched. The copy is staged next to the addon and swapped in
  with two renames, so an interrupted update leaves the old version in place.

The copy arrives with the app's own updates, which are only installed when Windows confirms they are
signed by the same publisher (update.py), so this adds no download of its own. ``"update_addon":
false`` in config.json turns it off.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
from pathlib import Path

from forevertracker_uploader.config import Config
from forevertracker_uploader.files import SV_NAME

log = logging.getLogger("forevertracker.uploader.addon")

ADDON = "ForeverTracker"
TOC = f"{ADDON}.toc"
_VERSION = re.compile(r"^## Version:\s*([0-9]+(?:\.[0-9]+)*)\s*$", re.MULTILINE)


def bundled_addon() -> Path | None:
    """The copy of the addon the installer left next to the packaged exe, if any."""
    if not getattr(sys, "frozen", False):
        return None
    folder = Path(sys.executable).parent / "addon" / ADDON
    return folder if (folder / TOC).is_file() else None


def toc_version(folder: Path) -> tuple[int, ...] | None:
    """The addon's ``## Version`` as numbers, or None when there is no readable one."""
    try:
        text = (folder / TOC).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    m = _VERSION.search(text)
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def _flavors(raw: str | Path) -> list[Path]:
    """Game flavor folders (``_forever_``) for a configured path: a flavor folder, the install root, or
    the SavedVariables file itself (as files.find_savedvariables accepts)."""
    p = Path(raw)
    if p.is_file() and p.name == SV_NAME and len(p.parents) > 4:
        return [p.parents[4]]  # <flavor>\WTF\Account\<account>\SavedVariables\ForeverTracker.lua
    if not p.is_dir():
        return []
    if (p / "WTF").is_dir() or (p / "Interface").is_dir():
        return [p]
    return [d for d in p.iterdir() if d.is_dir() and d.name.startswith("_")]


def installed_addons(wow_paths: list[str]) -> list[Path]:
    """Every ForeverTracker addon folder under the configured game folders."""
    found = set()
    for raw in wow_paths:
        for flavor in _flavors(raw):
            folder = flavor / "Interface" / "AddOns" / ADDON
            if (folder / TOC).is_file():
                found.add(folder)
    return sorted(found)


def running_programs() -> set[str]:
    """Lower-case file names of the running programs (Windows; empty elsewhere). Raises OSError when
    the list cannot be read."""
    if sys.platform != "win32":
        return set()
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (None, ctypes.c_void_p(-1).value):
        raise OSError(ctypes.get_last_error(), "cannot list running programs")
    names: set[str] = set()
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            names.add(entry.szExeFile.lower())
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return names


def game_running(flavor: Path) -> bool:
    """Whether a program from the game's flavor folder (Wow.exe) is running. When that cannot be told,
    it is assumed to be."""
    try:
        programs = {p.name.lower() for p in flavor.glob("*.exe")} or {"wow.exe"}
        return bool(programs & running_programs())
    except OSError:
        return True


def replace_addon(source: Path, target: Path) -> None:
    """Swap ``target`` for a copy of ``source``. On failure the original stays (or is put back)."""
    staging = target.parent / f".{ADDON}.new"
    old = target.parent / f".{ADDON}.old"
    for leftover in (staging, old):
        shutil.rmtree(leftover, ignore_errors=True)
    try:
        shutil.copytree(source, staging)
        os.replace(target, old)
        try:
            os.replace(staging, target)
        except OSError:
            os.replace(old, target)
            raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)


_waiting: set[Path] = set()  # folders already logged as waiting for the game to close


def keep_updated(cfg: Config, *, source: Path | None = None, is_running=game_running) -> list[Path]:
    """Update every installed addon older than the app's copy. Returns the folders updated."""
    if not cfg.update_addon:
        return []
    source = source or bundled_addon()
    new = toc_version(source) if source else None
    if new is None:
        return []
    updated = []
    for folder in installed_addons(cfg.wow_paths):
        have = toc_version(folder)
        if have is None or have >= new:
            continue
        flavor = folder.parents[2]
        version = ".".join(map(str, new))
        if is_running(flavor):
            if folder not in _waiting:
                log.info("addon %s will be installed in %s once the game is closed", version, folder)
                _waiting.add(folder)
            continue
        replace_addon(source, folder)
        _waiting.discard(folder)
        log.info("updated the addon in %s from %s to %s", folder, ".".join(map(str, have)), version)
        updated.append(folder)
    return updated


def keeper_for_this_build():
    """The background loop's addon check, or None: only the packaged Windows exe carries the addon."""
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        return lambda cfg: keep_updated(cfg)
    return None
