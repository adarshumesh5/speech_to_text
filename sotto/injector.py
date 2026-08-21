"""Text injection into the focused window via Win32 SendInput.

Uses KEYEVENTF_UNICODE so it works in every app that accepts keyboard input —
terminals, editors, browsers, chat apps — without touching the clipboard.
Ctrl+Z undo works naturally afterwards because we type real keystrokes.

Focus handling: ``send_text`` can restore a remembered target window before
typing, so dictation lands where the cursor was even when Grogu itself had
focus at record time. ``mode="clipboard"`` uses Ctrl+V instead of keystrokes
for apps that eat synthetic input (opt-in; it touches the clipboard).

Cancellation: pass a ``threading.Event`` (set to abort) and/or let the user
press Escape mid-type; ``send_text`` returns False if cancelled.
"""

from __future__ import annotations

import ctypes
import logging
import struct
import threading
import time
from ctypes import wintypes

log = logging.getLogger(__name__)

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

VK_RETURN = 0x0D
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_SHIFT = 0x10
VK_LEFT = 0x25
VK_CONTROL = 0x11
VK_V = 0x56


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", wintypes.DWORD * 5),
        ("hi", wintypes.DWORD * 3),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.CloseClipboard.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HANDLE
kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
kernel32.GlobalUnlock.restype = wintypes.BOOL

_INPUT_SIZE = ctypes.sizeof(INPUT)


def _make_inputs(keydown: INPUT, keyup: INPUT) -> list[INPUT]:
    return [keydown, keyup]


def _unicode_input(unit: int, keyup: bool) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = 0
    inp.u.ki.wScan = unit
    inp.u.ki.dwFlags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if keyup else 0)
    return inp


def _vk_input(vk: int, keyup: bool) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    inp.u.ki.dwFlags = KEYEVENTF_KEYUP if keyup else 0
    return inp


def _send_pair(down: INPUT, up: INPUT) -> None:
    arr = (INPUT * 2)(down, up)
    user32.SendInput(2, arr, _INPUT_SIZE)


def _send_one(inp: INPUT) -> None:
    user32.SendInput(1, ctypes.byref(inp), _INPUT_SIZE)


def _utf16_units(text: str):
    data = text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        yield struct.unpack("<H", data[i : i + 2])[0]


def is_escape_pressed() -> bool:
    return bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)


def _cancelled(cancel_event: threading.Event | None) -> bool:
    if cancel_event is not None and cancel_event.is_set():
        return True
    return is_escape_pressed()


def get_foreground_hwnd() -> int:
    """HWND of the currently focused top-level window (0 if none)."""
    hwnd = user32.GetForegroundWindow()
    return int(hwnd or 0)


def hwnd_pid(hwnd: int) -> int:
    """PID owning ``hwnd`` (0 when invalid)."""
    if not hwnd:
        return 0
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def is_own_window(hwnd: int) -> bool:
    """True when ``hwnd`` belongs to our own process."""
    import os

    return bool(hwnd) and hwnd_pid(hwnd) == os.getpid()


def focus_window(hwnd: int) -> bool:
    """Best-effort: bring ``hwnd`` to the foreground so typing lands there.

    Uses the AttachThreadInput trick, which lets us steal focus from our own
    window even though SetForegroundWindow normally refuses. Returns True when
    the window is (very likely) focused.
    """
    if not hwnd:
        return False
    try:
        cur_tid = kernel32.GetCurrentThreadId()
        target_tid = user32.GetWindowThreadProcessId(hwnd, None)
        attached = False
        if target_tid and target_tid != cur_tid:
            attached = bool(user32.AttachThreadInput(cur_tid, target_tid, True))
        ok = bool(user32.SetForegroundWindow(hwnd))
        if attached:
            user32.AttachThreadInput(cur_tid, target_tid, False)
        if not ok:
            log.debug("SetForegroundWindow(%s) failed", hwnd)
        return ok
    except Exception:  # noqa: BLE001
        log.debug("focus_window failed", exc_info=True)
        return False


def _set_clipboard(text: str) -> bool:
    """Put ``text`` on the clipboard as Unicode text."""
    try:
        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h:
                return False
            ptr = kernel32.GlobalLock(h)
            if ptr:
                ctypes.memmove(ptr, data, len(data))
                kernel32.GlobalUnlock(h)
            return bool(user32.SetClipboardData(CF_UNICODETEXT, h))
        finally:
            user32.CloseClipboard()
    except Exception:  # noqa: BLE001
        log.debug("clipboard write failed", exc_info=True)
        return False


def _paste_from_clipboard() -> None:
    _send_one(_vk_input(VK_CONTROL, False))
    _send_pair(_vk_input(VK_V, False), _vk_input(VK_V, True))
    _send_one(_vk_input(VK_CONTROL, True))


def select_back(count: int, cancel_event: threading.Event | None = None) -> bool:
    """Select ``count`` characters to the left of the cursor (Shift+Left).

    Returns True when the full selection completed.
    """
    for _ in range(count):
        if _cancelled(cancel_event):
            return False
        _send_one(_vk_input(VK_SHIFT, False))
        _send_one(_vk_input(VK_LEFT, False))
        _send_one(_vk_input(VK_LEFT, True))
        _send_one(_vk_input(VK_SHIFT, True))
    return True


def send_text(
    text: str,
    per_char_delay: float = 0.0,
    cancel_event: threading.Event | None = None,
    on_char=None,
    mode: str = "keystrokes",
    target_hwnd: int = 0,
) -> bool:
    """Insert ``text`` into the focused window. Returns True if completed.

    ``target_hwnd`` (when given and not ours) is brought to the foreground
    first so the text lands where the cursor was. ``mode="clipboard"`` copies
    to the clipboard and pastes with Ctrl+V instead of typing keystrokes.
    Escape (or ``cancel_event``) aborts mid-way; whatever was typed stays.
    """
    if target_hwnd and not is_own_window(target_hwnd):
        if user32.GetForegroundWindow() != target_hwnd:
            focus_window(target_hwnd)
            time.sleep(0.05)

    if mode == "clipboard":
        if not text:
            return True
        if not _set_clipboard(text):
            return False
        _paste_from_clipboard()
        return True

    for ch in text:
        if _cancelled(cancel_event):
            return False
        if ch == "\r":
            continue
        if ch == "\n":
            _send_pair(_vk_input(VK_RETURN, False), _vk_input(VK_RETURN, True))
        elif ch == "\t":
            _send_pair(_vk_input(VK_TAB, False), _vk_input(VK_TAB, True))
        else:
            for unit in _utf16_units(ch):
                _send_pair(_unicode_input(unit, False), _unicode_input(unit, True))
        if on_char:
            on_char()
        if per_char_delay:
            time.sleep(per_char_delay)
    return True
