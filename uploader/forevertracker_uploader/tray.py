"""The tray icon: shows that ForeverTracker is running, and lets the player stop it (Windows only).

The icon belongs to a hidden window created on the same thread as Tk, so Tk's event loop delivers
its messages and there is no second UI thread. Clicking the icon opens a status card (notice.py)
with a Quit button. Quit stops the upload loop; the app starts again at the next sign-in when
start-with-Windows is on, or from the Start menu.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes
from pathlib import Path

from forevertracker_uploader import notice
from forevertracker_uploader.config import Config, State

log = logging.getLogger("forevertracker.uploader.tray")

WM_APP_TRAY = 0x8000 + 1  # WM_APP + 1: the icon's click messages
POLL_MS = 100
WM_LBUTTONUP, WM_RBUTTONUP = 0x0202, 0x0205
NIM_ADD, NIM_DELETE = 0, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
IMAGE_ICON, LR_LOADFROMFILE, SM_CXSMICON = 1, 0x10, 49
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON),
    ]


user32, shell32, kernel32 = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def run(home: Path, stop: threading.Event, worker: threading.Thread, greeting: str | None = None) -> None:
    """Show the tray icon until the player quits or ``worker`` (the upload loop) ends. Main thread only."""
    import tkinter as tk

    heading = notice.prepare()
    root = tk.Tk()
    root.withdraw()
    app = _Tray(root, home, stop, worker, heading)
    try:
        app.add_icon()
        if greeting:
            app.greeting = notice.toast(root, greeting, heading)
        app.poll()
        root.mainloop()
    finally:
        app.remove_icon()


class _Tray:
    def __init__(self, root, home: Path, stop: threading.Event, worker: threading.Thread, heading: str):
        self.root, self.home, self.stop, self.worker, self.heading = root, home, stop, worker, heading
        self.card = None
        self.greeting = None  # the "running" notice, closed when the card opens in the same spot
        self.clicked = False
        self.closed_at = 0.0
        self.hwnd = None
        self.icon = None
        self.nid = None
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self._wndproc = WNDPROC(self._on_message)  # kept referenced: Windows calls it later

    def add_icon(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW(lpfnWndProc=self._wndproc, hInstance=hinst, lpszClassName="ForeverTrackerTray")
        user32.RegisterClassW(ctypes.byref(wc))
        # A hidden top-level window (not message-only) so it also hears "TaskbarCreated" after Explorer restarts.
        self.hwnd = user32.CreateWindowExW(0, "ForeverTrackerTray", notice.TITLE, 0, 0, 0, 0, 0, None, None, hinst, None)
        size = user32.GetSystemMetrics(SM_CXSMICON)
        self.icon = user32.LoadImageW(None, str(notice.ICON), IMAGE_ICON, size, size, LR_LOADFROMFILE)
        self.nid = NOTIFYICONDATAW(
            cbSize=ctypes.sizeof(NOTIFYICONDATAW), hWnd=self.hwnd, uID=1, uFlags=NIF_MESSAGE | NIF_ICON | NIF_TIP,
            uCallbackMessage=WM_APP_TRAY, hIcon=self.icon, szTip="ForeverTracker is running",
        )
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid)):
            log.warning("could not add the tray icon")

    def remove_icon(self) -> None:
        if self.nid is not None:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            self.nid = None
        if self.icon:
            user32.DestroyIcon(self.icon)
            self.icon = None
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None

    def _on_message(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_APP_TRAY and lparam in (WM_LBUTTONUP, WM_RBUTTONUP):
                # Windows calls this from inside Tk's event loop, where calling Tk crashes Python;
                # poll() opens the card instead.
                self.clicked = True
                return 0
            if msg == self.taskbar_created and self.nid is not None:  # Explorer restarted: add the icon again
                shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))
                return 0
        except Exception:  # noqa: BLE001 - an exception must not escape into Windows
            log.exception("tray message failed")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def toggle_card(self) -> None:
        if self.card is not None and self.card.winfo_exists():
            notice.fade_out(self.card)
            return
        if time.monotonic() - self.closed_at < 0.3:
            return  # this click is what just took focus away from the card and closed it
        if self.greeting is not None and self.greeting.winfo_exists():
            self.greeting.destroy()
        paused = Config.load(self.home).paused
        self.card = notice.card(
            self.root,
            "Paused" if paused else "Running",
            self.heading,
            detail="Uploads are paused." if paused else notice.last_synced(State.load(self.home)),
            dot=notice.WARN if paused else notice.GOOD,
            button=("Quit ForeverTracker", self.quit),
        )
        card = self.card
        card.bind("<Escape>", lambda _e: notice.fade_out(card))
        card.bind("<FocusOut>", lambda _e: card.after(150, self._close_if_unfocused, card))
        card.focus_force()
        user32.SetForegroundWindow(user32.GetAncestor(card.winfo_id(), 2))

    def _close_if_unfocused(self, card) -> None:
        try:
            focused = card.focus_get()
        except KeyError:  # Tk cannot name a focus window outside the app
            focused = None
        if focused is None and card.winfo_exists():
            self.closed_at = time.monotonic()
            notice.fade_out(card)

    def poll(self) -> None:
        """Open or close the card after a click, and quit when the upload loop ends by itself (an
        update is being installed). Runs every POLL_MS: cheap, and quick enough to feel instant."""
        if not self.worker.is_alive():
            self.root.destroy()
            return
        if self.clicked:
            self.clicked = False
            self.toggle_card()
        self.root.after(POLL_MS, self.poll)

    def quit(self) -> None:
        log.info("quit from the tray icon")
        self.stop.set()
        self.root.destroy()
