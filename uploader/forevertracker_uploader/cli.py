"""forevertracker-uploader: setup | autostart | status | disclose | sync | watch | background | start | pause | resume | gui"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
import threading
import time
from pathlib import Path

from forevertracker_uploader import __version__, autostart, background, files, notice, update
from forevertracker_uploader.client import Uploader, check_server_url
from forevertracker_uploader.config import Config, State, default_home
from forevertracker_uploader.singleinstance import AlreadyRunning, SingleInstance
from forevertracker_uploader.sync import disclose, sync_once


INSTALLER_CHOICES = "installer.json"  # written by packaging/installer.iss (SaveAppChoices)


def _fmt_time(ts: float | None) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "never"


def _configure(home: Path, server: str | None, wow: list[str] | None) -> Config:
    cfg = Config.load(home)
    if server:
        cfg.server_url = check_server_url(server)
    if wow:
        cfg.wow_paths = wow
    elif not cfg.wow_paths:
        cfg.wow_paths = [str(p) for p in files.candidate_roots()]
    cfg.save(home)
    return cfg


def apply_installer_choices(home: Path) -> None:
    """Save the server and game folder the installer left in installer.json, then remove the file.

    The installer leaves this file rather than running the app hidden, which antivirus heuristics flag."""
    path = home / INSTALLER_CHOICES
    try:
        choices = json.loads(path.read_text(encoding="utf-8-sig"))
        _configure(home, choices.get("server_url"), [str(p) for p in choices.get("wow_paths") or []])
    except FileNotFoundError:
        return
    except (AttributeError, TypeError, ValueError) as e:
        logging.getLogger("forevertracker.uploader").warning("ignoring the installer's settings: %s", e)
    path.unlink(missing_ok=True)


def cmd_setup(args, home: Path) -> int:
    cfg = _configure(home, args.server, args.wow)
    found = files.find_savedvariables(cfg.wow_paths)
    print(f"Configuration saved to {home / 'config.json'}")
    print(f"Server: {cfg.server_url}")
    print("Watching:" if found else "No ForeverTracker.lua found yet (it appears after your first logout with the addon).")
    for f in found:
        print(f"  {f}")
    print("Nothing in your WoW folder is ever modified. Run `disclose` to see what would be uploaded.")
    return 0


def cmd_status(_args, home: Path) -> int:
    cfg, state = Config.load(home), State.load(home)
    print(f"Version:       {__version__}")
    print(f"Server:        {cfg.server_url}")
    print(f"Paused:        {'yes' if cfg.paused else 'no'}")
    print(f"Files:         {', '.join(map(str, files.find_savedvariables(cfg.wow_paths))) or 'none found'}")
    print(f"Last sync:     {_fmt_time(state.last_sync_at)} ({state.last_sync_result or '-'})")
    print(f"Last error:    {state.last_error or '-'}")
    print(f"Archived:      {len(state.versions)} file version(s); {len(state.uploaded_batches)} batch(es) uploaded")
    return 0


def cmd_disclose(_args, home: Path) -> int:
    for line in disclose(Config.load(home)):
        print(line)
    return 0


def _sync(home: Path) -> str:
    cfg, state = Config.load(home), State.load(home)
    uploader = Uploader(cfg.server_url)
    try:
        report = sync_once(home, cfg, state, uploader)
    finally:
        uploader.close()
        state.save(home)
    for err in report.errors:
        print(f"  ! {err}", file=sys.stderr)
    return report.summary()


def cmd_sync(_args, home: Path) -> int:
    print(_sync(home))
    return 0


def cmd_watch(_args, home: Path) -> int:
    print("Watching for new ForeverTracker data (Ctrl+C to stop). WoW saves addon data on logout, exit and /reload.")
    last_mtimes: dict[str, float] = {}
    try:
        while True:
            cfg = Config.load(home)
            if not cfg.paused:
                current = {str(p): p.stat().st_mtime for p in files.find_savedvariables(cfg.wow_paths)}
                if current != last_mtimes:
                    print(f"[{_fmt_time(time.time())}] {_sync(home)}")
                    last_mtimes = current
            time.sleep(cfg.poll_seconds)
    except KeyboardInterrupt:
        return 0


def cmd_pause(args, home: Path) -> int:
    cfg = Config.load(home)
    cfg.paused = args.command == "pause"
    cfg.save(home)
    print("Uploading paused." if cfg.paused else "Uploading resumed.")
    return 0


def cmd_background(_args, home: Path) -> int:
    """Start at login: upload each run as the game saves it, with a tray icon on Windows."""
    return _run_app(home, greeting=None)


def cmd_start(_args, home: Path) -> int:
    """What the shortcuts run: the same, plus a notice saying it is running (or already was)."""
    return _run_app(home, greeting=notice.STARTED)


def _run_app(home: Path, greeting: str | None) -> int:
    """Upload on a worker thread while the main thread shows the tray icon, until the player quits or
    the loop ends by itself (an update is being installed). One copy at a time."""
    background.configure_logging(home)
    try:
        lock = SingleInstance(home).acquire()
    except AlreadyRunning:
        logging.getLogger("forevertracker.uploader").info("not starting: already running")
        if greeting:
            notice.show(notice.ALREADY_RUNNING)
        return 0
    stop = threading.Event()
    worker = threading.Thread(
        target=background.run_background,
        args=(home,),
        kwargs={"updater": update.updater_for_this_build(), "stop": stop, "single_instance": False},
        name="uploads",
    )
    try:
        worker.start()
        try:
            if _has_tray():
                _show_tray(home, stop, worker, greeting)
            elif greeting:
                notice.show(greeting)
        except Exception:  # noqa: BLE001 - without a tray icon, keep uploading anyway
            logging.getLogger("forevertracker.uploader").exception("tray icon unavailable")
        worker.join()
    finally:
        lock.release()
    return 0


def _has_tray() -> bool:
    return sys.platform == "win32"


def _show_tray(home: Path, stop: threading.Event, worker: threading.Thread, greeting: str | None) -> None:
    from forevertracker_uploader import tray  # Windows only

    tray.run(home, stop, worker, greeting)


def cmd_autostart(args, home: Path) -> int:
    if sys.platform != "win32":
        print("Start-with-Windows is only available on Windows.")
        return 1
    action = args.action or "status"
    if action == "enable":
        cmd = autostart.enable(home if args.home else None)
        print(f"ForeverTracker will start with Windows (visible in Settings > Startup):\n  {cmd}")
    elif action == "disable":
        print("Start-with-Windows removed." if autostart.disable() else "Start-with-Windows was not set.")
    else:
        current = autostart.status()
        print(f"Start-with-Windows: ON\n  {current}" if current else "Start-with-Windows: OFF")
    return 0


def cmd_gui(_args, home: Path) -> int:
    from forevertracker_uploader.gui import run

    run(home)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forevertracker-uploader", description=__doc__)
    parser.add_argument("--home", type=Path, default=None, help="where settings, state and the archive are kept")
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup", help="choose the WoW folder and server")
    setup.add_argument("--wow", nargs="+", help="World of Warcraft folder, flavor folder (e.g. _forever_) or ForeverTracker.lua")
    setup.add_argument("--server", help="ForeverTracker server URL (https)")
    setup.set_defaults(fn=cmd_setup)
    auto = sub.add_parser("autostart", help="turn start-with-Windows on or off (Windows only)")
    auto.add_argument("action", nargs="?", choices=["enable", "disable", "status"], help="default: status")
    auto.set_defaults(fn=cmd_autostart)
    for name, fn, text in (
        ("status", cmd_status, "show settings and the last synchronisation"),
        ("disclose", cmd_disclose, "show exactly what would be uploaded"),
        ("sync", cmd_sync, "upload new data once"),
        ("watch", cmd_watch, "keep uploading after each logout or /reload (console)"),
        ("background", cmd_background, "upload in the background with a tray icon; start this at login"),
        ("start", cmd_start, "like background, plus a notice that it is running (the shortcuts)"),
        ("pause", cmd_pause, "stop uploading"),
        ("resume", cmd_pause, "resume uploading"),
        ("gui", cmd_gui, "open a small status window"),
    ):
        sub.add_parser(name, help=text).set_defaults(fn=fn)
    args = parser.parse_args(argv)
    home = args.home or default_home()
    apply_installer_choices(home)
    return args.fn(args, home)


if __name__ == "__main__":
    sys.exit(main())
