"""A minimal status window (tkinter, part of the Python standard library)."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext

from forevertracker_uploader import files
from forevertracker_uploader.client import Uploader
from forevertracker_uploader.config import Config, State
from forevertracker_uploader.sync import disclose, sync_once


def run(home: Path) -> None:
    root = tk.Tk()
    root.title("ForeverTracker uploader")
    root.geometry("560x420")
    status = tk.StringVar()
    log = scrolledtext.ScrolledText(root, height=14, wrap="word")
    busy = threading.Lock()
    mtimes: dict[str, float] = {}

    def refresh():
        cfg, state = Config.load(home), State.load(home)
        last = time.strftime("%Y-%m-%d %H:%M", time.localtime(state.last_sync_at)) if state.last_sync_at else "never"
        status.set(f"{'PAUSED' if cfg.paused else 'Active'} · last sync {last}: {state.last_sync_result or '-'}")
        pause_btn.config(text="Resume" if cfg.paused else "Pause")

    def write(text: str):
        log.insert("end", text + "\n")
        log.see("end")

    def do_sync():
        if not busy.acquire(blocking=False):
            return
        def work():
            try:
                cfg, state = Config.load(home), State.load(home)
                uploader = Uploader(cfg.server_url)
                try:
                    report = sync_once(home, cfg, state, uploader)
                finally:
                    uploader.close()
                    state.save(home)
                root.after(0, write, f"[{time.strftime('%H:%M:%S')}] {report.summary()}")
                for err in report.errors:
                    root.after(0, write, f"  ! {err}")
            except Exception as err:  # noqa: BLE001 - shown to the user
                root.after(0, write, f"  ! {err}")
            finally:
                busy.release()
                root.after(0, refresh)
        threading.Thread(target=work, daemon=True).start()

    def toggle_pause():
        cfg = Config.load(home)
        cfg.paused = not cfg.paused
        cfg.save(home)
        refresh()

    def show_disclosure():
        write("\n".join(disclose(Config.load(home))))

    def poll():
        cfg = Config.load(home)
        if not cfg.paused:
            current = {str(p): p.stat().st_mtime for p in files.find_savedvariables(cfg.wow_paths)}
            if current != mtimes:
                mtimes.clear()
                mtimes.update(current)
                do_sync()
        root.after(int(cfg.poll_seconds * 1000), poll)

    tk.Label(root, textvariable=status, anchor="w").pack(fill="x", padx=8, pady=6)
    bar = tk.Frame(root)
    bar.pack(fill="x", padx=8)
    tk.Button(bar, text="Sync now", command=do_sync).pack(side="left")
    pause_btn = tk.Button(bar, text="Pause", command=toggle_pause)
    pause_btn.pack(side="left", padx=6)
    tk.Button(bar, text="What is uploaded?", command=show_disclosure).pack(side="left")
    log.pack(fill="both", expand=True, padx=8, pady=8)
    write("Uploads start after WoW saves the addon file (logout, exit or /reload). Nothing in the WoW folder is modified.")
    refresh()
    root.after(500, poll)
    root.mainloop()
