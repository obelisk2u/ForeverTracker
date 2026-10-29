"""Small cards in the website's style: the "running" notice and the tray icon's status card.

The app has no main window, so these are what the player sees: a notice when they start it from a
shortcut, and a card with a Quit button when they click the tray icon (tray.py). Cards appear above
the taskbar, bottom right. Notices fade out on their own or when clicked. If a card cannot be drawn,
show() falls back to a plain Windows message box.

assets/: emblem-*.png and forevertracker.ico are frontend/public/favicon.svg rendered at the sizes
Windows asks for, and Cinzel-SemiBold.ttf is the site's heading font (@fontsource/cinzel, SIL Open
Font License, see Cinzel-OFL.txt), loaded for this process only.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

log = logging.getLogger("forevertracker.uploader.notice")

TITLE = "ForeverTracker"
STARTED = "Running in the background"
ALREADY_RUNNING = "Already running in the background"
DETAIL = "Your dungeon runs upload after you log out, exit or /reload in World of Warcraft."

ASSETS = Path(__file__).with_name("assets")
ICON = ASSETS / "forevertracker.ico"
EMBLEM_SIZES = (40, 50, 60, 70, 80)
SHOW_MS = 6000

# The website's palette (frontend/app/globals.css).
SURFACE, SURFACE_2, SURFACE_3 = "#111724", "#172031", "#1f2a3f"
LINE, LINE_STRONG = "#263249", "#34425f"
TEXT, MUTED, FAINT = "#e7eaf1", "#96a2bb", "#66728b"
GOLD, GOOD, WARN = "#e2b356", "#4fd07f", "#f2a93b"


def show(status: str) -> None:
    """Show a notice on its own (no tray running) and return once it has gone."""
    if sys.platform != "win32":
        print(f"{TITLE}: {status}. {DETAIL}")
        return
    try:
        import tkinter as tk

        heading = prepare()
        root = tk.Tk()
        root.withdraw()
        toast(root, status, heading, then=root.destroy)
        root.mainloop()
    except Exception:  # noqa: BLE001 - a cosmetic notice must never stop the app from starting
        log.exception("could not draw the notice; showing a message box instead")
        import ctypes

        MB_ICONINFORMATION, MB_SETFOREGROUND = 0x40, 0x10000
        ctypes.windll.user32.MessageBoxW(None, f"{status}.\n\n{DETAIL}", TITLE, MB_ICONINFORMATION | MB_SETFOREGROUND)


def last_synced(state, now: float | None = None) -> str:
    """One line for the tray card: when the app last synced, or that it is waiting for a first run."""
    if state.last_error:
        return "The last upload failed; it will try again shortly."
    if not state.last_sync_at:
        return "Waiting for your first run. Runs upload after you log out, exit or /reload."
    minutes = int(((now or time.time()) - state.last_sync_at) // 60)
    if minutes < 1:
        ago = "just now"
    elif minutes < 60:
        ago = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif minutes < 48 * 60:
        ago = f"{minutes // 60} hour{'s' if minutes // 60 != 1 else ''} ago"
    else:
        ago = f"{minutes // 1440} days ago"
    return f"Last synced {ago}."


def prepare() -> str:
    """Make the process DPI-aware (so text is sharp) and load the heading font. Call before Tk starts.
    Returns the heading font family."""
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()
    font = ASSETS / "Cinzel-SemiBold.ttf"
    FR_PRIVATE = 0x10
    loaded = font.is_file() and ctypes.windll.gdi32.AddFontResourceExW(str(font), FR_PRIVATE, 0) > 0
    return "Cinzel SemiBold" if loaded else "Georgia"


def build(win, status: str, heading_font: str, *, detail: str = DETAIL, dot: str = GOOD, button=None, on_close=None) -> None:
    """Lay out a card inside ``win``. ``button`` is (label, command). Separate so tests can check it unseen."""
    import tkinter as tk

    scale = win.winfo_fpixels("1i") / 96

    def px(n: float) -> int:
        return round(n * scale)

    win.configure(bg=LINE)  # shows as a 1 px border around the card
    card = tk.Frame(win, bg=SURFACE)
    card.pack(padx=1, pady=1)
    tk.Frame(card, bg=GOLD, width=px(3)).pack(side="left", fill="y")
    body = tk.Frame(card, bg=SURFACE, padx=px(14), pady=px(12))
    body.pack(side="left")

    size = min(EMBLEM_SIZES, key=lambda n: abs(n - 40 * scale))
    emblem = tk.PhotoImage(file=str(ASSETS / f"emblem-{size}.png"), master=win)
    win.emblem = emblem  # Tk drops images that Python no longer references
    tk.Label(body, image=emblem, bg=SURFACE).grid(row=0, column=0, rowspan=4, sticky="n", padx=(0, px(12)))
    tk.Label(body, text=TITLE, font=(heading_font, 13), fg=GOLD, bg=SURFACE).grid(row=0, column=1, sticky="w")
    line = tk.Frame(body, bg=SURFACE)
    line.grid(row=1, column=1, sticky="w", pady=(px(2), 0))
    tk.Label(line, text="●", font=("Segoe UI", 8), fg=dot, bg=SURFACE).pack(side="left")
    tk.Label(line, text=status, font=("Segoe UI Semibold", 10), fg=TEXT, bg=SURFACE).pack(side="left", padx=(px(4), 0))
    tk.Label(
        body, text=detail, font=("Segoe UI", 9), fg=MUTED, bg=SURFACE, justify="left", wraplength=px(260)
    ).grid(row=2, column=1, sticky="w", pady=(px(4), 0))
    if button:
        label, command = button
        b = tk.Label(
            body, text=label, font=("Segoe UI Semibold", 9), fg=TEXT, bg=SURFACE_2, padx=px(12), pady=px(5),
            cursor="hand2", highlightthickness=1, highlightbackground=LINE_STRONG,
        )
        b.grid(row=3, column=1, sticky="w", pady=(px(12), 0))
        b.bind("<Enter>", lambda _e: b.configure(bg=SURFACE_3))
        b.bind("<Leave>", lambda _e: b.configure(bg=SURFACE_2))
        b.bind("<ButtonRelease-1>", lambda _e: command())
    close = tk.Label(body, text="✕", font=("Segoe UI", 9), fg=FAINT, bg=SURFACE, cursor="hand2")
    close.grid(row=0, column=2, sticky="ne", padx=(px(12), 0))
    close.bind("<Enter>", lambda _e: close.configure(fg=TEXT))
    close.bind("<Leave>", lambda _e: close.configure(fg=FAINT))
    if on_close:
        close.bind("<ButtonRelease-1>", lambda _e: on_close())


def card(root, status: str, heading_font: str, **kw):
    """Open a card in the bottom-right corner above the taskbar; it slides up and fades in."""
    import ctypes
    import tkinter as tk

    win = tk.Toplevel(root)
    win.withdraw()
    win.overrideredirect(True)  # no title bar or taskbar button
    win.attributes("-topmost", True)
    win.attributes("-alpha", 0.0)
    kw.setdefault("on_close", lambda: fade_out(win))
    build(win, status, heading_font, **kw)

    scale = win.winfo_fpixels("1i") / 96
    margin, rise = round(16 * scale), round(12 * scale)
    win.update_idletasks()
    _left, _top, right, bottom = _work_area(ctypes, win)
    x, y = right - win.winfo_reqwidth() - margin, bottom - win.winfo_reqheight() - margin
    win.geometry(f"+{x}+{y + rise}")
    win.deiconify()
    if _round_corners(ctypes, win):
        win.configure(bg=SURFACE)  # Windows 11 draws the border around the rounded shape instead

    def fade_in(step: int = 1, steps: int = 10) -> None:
        if not win.winfo_exists():
            return
        frac = step / steps
        win.attributes("-alpha", frac)
        win.geometry(f"+{x}+{y + round(rise * (1 - frac) ** 2)}")
        if step < steps:
            win.after(16, fade_in, step + 1)

    fade_in()
    return win


def fade_out(win, then=None) -> None:
    """Fade a card out and destroy it, then call ``then``. Safe to call more than once."""
    if getattr(win, "closing", False) or not win.winfo_exists():
        return
    win.closing = True

    def step(alpha: float) -> None:
        if alpha > 0:
            win.attributes("-alpha", alpha)
            win.after(20, step, round(alpha - 0.1, 2))
        else:
            win.destroy()
            if then:
                then()

    step(float(win.attributes("-alpha")))


def toast(root, status: str, heading_font: str, then=None):
    """A notice that closes itself after a few seconds (later while the mouse is over it) or on a click."""
    win = card(root, status, heading_font, on_close=lambda: fade_out(win, then))
    hover = {"on": False}
    win.bind("<Enter>", lambda _e: hover.update(on=True))
    win.bind("<Leave>", lambda _e: hover.update(on=False))
    for widget in _walk(win):
        widget.bind("<ButtonRelease-1>", lambda _e: fade_out(win, then), add="+")

    def close_unless_hovered() -> None:
        if win.winfo_exists():
            win.after(500, close_unless_hovered) if hover["on"] else fade_out(win, then)

    win.after(SHOW_MS, close_unless_hovered)
    return win


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _work_area(ctypes, win) -> tuple[int, int, int, int]:
    """The screen minus the taskbar, as (left, top, right, bottom)."""
    from ctypes import wintypes

    rect = wintypes.RECT()
    SPI_GETWORKAREA = 0x0030
    if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, win.winfo_screenwidth(), win.winfo_screenheight() - round(48 * win.winfo_fpixels("1i") / 96)


def _round_corners(ctypes, win) -> bool:
    """Windows 11: round the corners and draw the border in the site's line colour. False elsewhere."""
    GA_ROOT, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND, DWMWA_BORDER_COLOR = 2, 33, 2, 34
    hwnd = ctypes.windll.user32.GetAncestor(win.winfo_id(), GA_ROOT)
    try:
        dwm = ctypes.windll.dwmapi
        if dwm.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(ctypes.c_int(DWMWCP_ROUND)), 4):
            return False  # non-zero HRESULT: not supported on this Windows
        r, g, b = (int(LINE[i : i + 2], 16) for i in (1, 3, 5))
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR, ctypes.byref(ctypes.c_int(b << 16 | g << 8 | r)), 4)
        return True
    except (AttributeError, OSError):
        return False
