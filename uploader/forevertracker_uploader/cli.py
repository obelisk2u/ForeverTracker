"""forevertracker-uploader: setup | autostart | status | disclose | sync | watch | background | pause | resume | gui"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from forevertracker_uploader import __version__, autostart, background, files, update
from forevertracker_uploader.client import Uploader, check_server_url
from forevertracker_uploader.config import Config, State, default_home
from forevertracker_uploader.sync import disclose, sync_once


def _fmt_time(ts: float | None) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "never"


def cmd_setup(args, home: Path) -> int:
    cfg = Config.load(home)
    if args.server:
        cfg.server_url = check_server_url(args.server)
    if args.wow:
        cfg.wow_paths = args.wow
    elif not cfg.wow_paths:
        cfg.wow_paths = [str(p) for p in files.candidate_roots()]
    cfg.save(home)
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
    """Run with no window: start at login, upload each run as the game saves it, idle otherwise."""
    background.configure_logging(home)
    background.run_background(home, updater=update.updater_for_this_build())
    return 0


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
        ("background", cmd_background, "run with no window; start this at login"),
        ("pause", cmd_pause, "stop uploading"),
        ("resume", cmd_pause, "resume uploading"),
        ("gui", cmd_gui, "open a small status window"),
    ):
        sub.add_parser(name, help=text).set_defaults(fn=fn)
    args = parser.parse_args(argv)
    return args.fn(args, args.home or default_home())


if __name__ == "__main__":
    sys.exit(main())
