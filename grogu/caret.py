"""Win32 caret and focus tracking — find where the blinking cursor actually is.

Uses GetGUIThreadInfo to detect which window owns the caret, and tracks
the last known caret window across focus changes. This lets Grogu type
where the cursor was, even if Freebuff/Desktop has focus when the hotkey fires.
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
from ctypes import wintypes

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.GetGUIThreadInfo.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = wintypes.INT
user32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL

GA_ROOTOWNER = 3
OWN_PID = os.getpid()


def get_window_title(hwnd: int) -> str:
    if not hwnd:
        return "<none>"
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return "<untitled>"
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def hwnd_pid(hwnd: int) -> int:
    if not hwnd:
        return 0
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _get_caret_info_for_tid(tid: int) -> tuple[int, wintypes.RECT]:
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
        return 0, wintypes.RECT(0, 0, 0, 0)
    hwnd = int(info.hwndCaret or 0)
    return hwnd, info.rcCaret


def _has_visible_caret(hwnd: int, rect: wintypes.RECT) -> bool:
    if not hwnd:
        return False
    return rect.left != rect.right or rect.top != rect.bottom


def find_caret_window() -> tuple[int, str]:
    """Find a window with a visible caret by checking all top-level windows.

    Returns (hwnd, title). hwnd=0 means no caret found.
    """
    # 1. Quick check: foreground window
    fg = int(user32.GetForegroundWindow() or 0)
    if fg and hwnd_pid(fg) != OWN_PID:
        tid = user32.GetWindowThreadProcessId(fg, None)
        caret, rect = _get_caret_info_for_tid(tid)
        if _has_visible_caret(caret, rect):
            root = int(user32.GetAncestor(caret, GA_ROOTOWNER) or 0)
            target = root if root else caret
            return target, get_window_title(target)

    # 2. Enumerate all visible top-level windows
    results: list[tuple[int, str]] = []

    def enum_cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if hwnd_pid(hwnd) == OWN_PID:
            return True
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        caret, rect = _get_caret_info_for_tid(tid)
        if _has_visible_caret(caret, rect):
            results.append((hwnd, get_window_title(hwnd)))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

    if results:
        return results[0]
    return 0, "<none>"


class CaretTracker:
    """Tracks the last window with a visible caret.

    Polls periodically and remembers the last known caret window.
    When the hotkey fires, use ``get_target()`` to get the window
    to type into.
    """

    def __init__(self, interval: float = 0.3):
        self.interval = interval
        self._last_hwnd: int = 0
        self._last_title: str = ""
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="grogu-caret", daemon=True
        )
        self._thread.start()
        # Do an immediate scan so we have a target right away
        self._scan()
        log.info("CaretTracker started (interval=%.2fs)", self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None

    def get_target(self) -> tuple[int, str]:
        """Return the last known caret window (hwnd, title).

        Returns (0, '') if no caret has been found or the cached window
        was closed.
        """
        with self._lock:
            hwnd = self._last_hwnd
            title = self._last_title
        if hwnd and user32.IsWindow(hwnd):
            return hwnd, title
        if hwnd:
            log.debug("CaretTracker: cached hwnd %s no longer valid", hwnd)
            with self._lock:
                self._last_hwnd = 0
                self._last_title = ""
        # Try an immediate scan
        hwnd, title = find_caret_window()
        if hwnd:
            with self._lock:
                self._last_hwnd = hwnd
                self._last_title = title
            return hwnd, title
        return 0, ""

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._scan()
            except Exception:  # noqa: BLE001
                log.debug("CaretTracker poll error", exc_info=True)
            self._stop.wait(self.interval)

    def _scan(self) -> None:
        hwnd, title = find_caret_window()
        if hwnd:
            with self._lock:
                if hwnd != self._last_hwnd:
                    log.info("CaretTracker: caret found hwnd=%s title=%r", hwnd, title)
                self._last_hwnd = hwnd
                self._last_title = title
        else:
            # No caret found — keep the last known one if it's still valid
            with self._lock:
                if self._last_hwnd and not user32.IsWindow(self._last_hwnd):
                    log.debug("CaretTracker: clearing stale hwnd=%s", self._last_hwnd)
                    self._last_hwnd = 0
                    self._last_title = ""
