"""Start-with-Windows registration.

Writes a value under the per-user ``Run`` key, which is the ordinary, visible way to start
with Windows: the entry shows up in Settings -> Apps -> Startup and in Task Manager's Startup
tab, where the player can turn it off, and it is removed cleanly on uninstall. We deliberately
do not use a service, a scheduled task, or any mechanism that hides the entry from that list.

On a packaged build the Windows installer sets this entry; these functions let a source install
toggle it too, and back the ``autostart`` CLI command.
"""

from __future__ import annotations

import sys
from pathlib import Path

RUN_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ForeverTrackerUploader"


def run_command(home: Path | None = None) -> str:
    """The command Windows should run at login: the uploader's windowless background mode."""
    args = ["background"]
    if home is not None:
        args = ["--home", str(home)] + args
    if getattr(sys, "frozen", False):  # PyInstaller build: the exe is itself the entry point
        exe = sys.executable
    else:  # source install: use pythonw.exe so no console window appears
        exe = str(Path(sys.executable).with_name("pythonw.exe"))
        args = ["-m", "forevertracker_uploader.cli"] + args
    return " ".join(_quote(part) for part in [exe, *args])


def _quote(part: str) -> str:
    return f'"{part}"' if (" " in part or "\t" in part) else part


def enable(home: Path | None = None, *, command: str | None = None, subkey: str = RUN_SUBKEY, value_name: str = VALUE_NAME) -> str:
    """Register start-with-Windows. Returns the command written. Windows only."""
    cmd = command or run_command(home)
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, cmd)
    return cmd


def disable(*, subkey: str = RUN_SUBKEY, value_name: str = VALUE_NAME) -> bool:
    """Remove the start-with-Windows entry. Returns True if one was present. Windows only."""
    import winreg

    try:
        with winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, value_name)
        return True
    except FileNotFoundError:
        return False


def status(*, subkey: str = RUN_SUBKEY, value_name: str = VALUE_NAME) -> str | None:
    """The registered command, or None if start-with-Windows is off. Windows only."""
    import winreg

    try:
        with winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_QUERY_VALUE) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
        return value
    except FileNotFoundError:
        return None
