"""Global push-to-talk hotkey via Win32 RegisterHotKey.

A hidden message-only window is created on a dedicated thread; WM_HOTKEY
messages drive a down/up callback pair. RegisterHotKey only reports key-downs,
so for hold-to-talk we poll GetAsyncKeyState until the key is released.

Usage::

    listener = HotkeyListener("Ctrl+Shift+Space", on_down=..., on_up=...)
    listener.start()
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes

log = logging.getLogger(__name__)

# --- Win32 constants -------------------------------------------------------
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HWND_MESSAGE = wintypes.HWND(-3)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_KEYS = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09,
    "esc": 0x1B, "escape": 0x1B, "backspace": 0x08, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdn": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "insert": 0x2D, "capslock": 0x14, "printscreen": 0x2C, "scrolllock": 0x91,
    "pause": 0x13, "numlock": 0x90, "apps": 0x5D, "win": 0x5B,
    "*": 0x6A, "+": 0x6B, "-": 0x6D, ".": 0x6E, "/": 0x6F,
}

ERROR_HOTKEY_ALREADY_REGISTERED = 1409
ERROR_CLASS_ALREADY_EXISTS = 1410

# Window classes are process-wide and never unregistered within a process, so
# each listener instance must register a *unique* class name — otherwise a
# second listener (mute hotkey, or a post-restart listener) would inherit the
# first one's wndproc and its hotkey would silently never fire.
_class_counter = 0
_class_counter_lock = threading.Lock()


def _unique_class_name(prefix: str) -> str:
    global _class_counter
    with _class_counter_lock:
        _class_counter += 1
        return f"{prefix}{_class_counter}"


def hotkey_error_text(err: int) -> str:
    """Human explanation for common RegisterHotKey failures."""
    if err == ERROR_HOTKEY_ALREADY_REGISTERED:
        return "already in use by another app — pick a different combination"
    return f"Windows error {err}"

MODIFIER_FLAGS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL,
                  "shift": MOD_SHIFT, "alt": MOD_ALT, "win": MOD_WIN,
                  "windows": MOD_WIN, "meta": MOD_WIN}

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = ctypes.c_ssize_t
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DefWindowProcW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def is_key_down(vk: int) -> bool:
    """True while the given virtual key is physically held."""
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Parse a hotkey spec like "Ctrl+Shift+Space" into (modifiers, vk).

    Raises ValueError on anything unrecognized so callers can surface it.
    """
    parts = [p.strip() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError("Empty hotkey")
    modifiers = 0
    key_part = parts[-1]
    for part in parts[:-1]:
        flag = MODIFIER_FLAGS.get(part.lower())
        if flag is None:
            raise ValueError(f"Unknown modifier: {part!r}")
        modifiers |= flag

    low = key_part.lower()
    if low in VK_KEYS:
        vk = VK_KEYS[low]
    elif len(key_part) == 1:
        ch = key_part.upper()
        if ch.isalnum() or ch in "`-=[]\\;',./":
            vk = ord(ch)
        else:
            raise ValueError(f"Unsupported key: {key_part!r}")
    elif low.startswith("f") and 1 <= int(low[1:]) <= 24:
        vk = 0x70 + int(low[1:]) - 1
    else:
        raise ValueError(f"Unsupported key: {key_part!r}")
    return modifiers, vk


class HotkeyListener:
    """Registers a global hotkey and reports down/up via callbacks.

    Callbacks fire from a dedicated background thread; keep them cheap (e.g.
    push to a queue). ``start()``/``stop()`` are safe to call repeatedly.
    """

    def __init__(self, spec: str, on_down=None, on_up=None, on_error=None,
                 on_registered=None, hotkey_id: int = 1):
        self.spec = spec
        self.on_down = on_down
        self.on_up = on_up
        self.on_error = on_error
        self.on_registered = on_registered
        self._id = hotkey_id
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._pressed = False
        self._modifiers = 0
        self._vk = 0
        self._wndproc = WNDPROC(self._wndproc_impl)

    # -- public API ---------------------------------------------------------
    @property
    def key(self) -> str:
        return self.spec

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._modifiers, self._vk = parse_hotkey(self.spec)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="grogu-hotkey",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(timeout=2.0)
        self._thread = None

    # -- internals ----------------------------------------------------------
    def _wndproc_impl(self, hwnd, msg, wparam, lparam):
        if msg == WM_HOTKEY and wparam == self._id:
            self._on_hotkey()
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on_hotkey(self):
        if self._pressed:
            return
        self._pressed = True
        # Capture the foreground window NOW — at the exact moment the hotkey fires.
        # This is critical because by the time the GUI thread processes the event,
        # the foreground window may have changed.
        user32_local = ctypes.WinDLL("user32", use_last_error=True)
        user32_local.GetForegroundWindow.restype = wintypes.HWND
        fg_hwnd = int(user32_local.GetForegroundWindow() or 0)
        log.debug("hotkey fired: fg_hwnd=%s", fg_hwnd)
        if self.on_down:
            try:
                self.on_down(fg_hwnd=fg_hwnd)
            except TypeError:
                # Backward compat: old callback without fg_hwnd arg
                self.on_down()
            except Exception:
                log.exception("on_down callback failed")
        # Block until the key is released so we can report key-up.
        while not self._stop.is_set() and (user32.GetAsyncKeyState(self._vk) & 0x8000):
            time.sleep(0.01)
        self._pressed = False
        if not self._stop.is_set() and self.on_up:
            try:
                self.on_up()
            except Exception:
                log.exception("on_up callback failed")

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.lpszClassName = _unique_class_name("GroguHotkeyWindow")
        wc.hInstance = hinst
        if not user32.RegisterClassW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != ERROR_CLASS_ALREADY_EXISTS:
                log.error("RegisterClassW failed: %s", err)
                if self.on_error:
                    self.on_error(f"Could not set up the hotkey (error {err}).")
                return
        hwnd = user32.CreateWindowExW(
            0, wc.lpszClassName, "Grogu", 0,
            0, 0, 0, 0, HWND_MESSAGE, None, hinst, None,
        )
        if not hwnd:
            log.error("CreateWindowExW failed")
            if self.on_error:
                self.on_error("Could not create the hotkey window.")
            return
        try:
            ok = user32.RegisterHotKey(hwnd, self._id, self._modifiers | MOD_NOREPEAT,
                                       self._vk)
            if not ok:
                err = ctypes.get_last_error()
                msg = (f"Hotkey {self.spec} {hotkey_error_text(err)}. "
                       "Pick a different one in Settings.")
                log.error(msg)
                if self.on_error:
                    self.on_error(msg)
                return
            log.info("Hotkey registered: %s", self.spec)
            if self.on_registered:
                self.on_registered(self.spec)
            msg = MSG()
            while not self._stop.is_set():
                res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if res == 0:  # WM_QUIT
                    break
                if res == -1:
                    log.error("GetMessageW failed")
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnregisterHotKey(hwnd, self._id)
            user32.DestroyWindow(hwnd)


def test_register(spec: str, hotkey_id: int = 5001) -> tuple[bool, str]:
    """Check whether ``spec`` can be registered as a global hotkey right now.

    Returns (ok, message). Used by the Settings "Test hotkey" button.
    """
    try:
        modifiers, vk = parse_hotkey(spec)
    except ValueError as e:
        return False, f"Invalid hotkey: {e}"

    result: dict = {}

    def probe():
        user32_local = ctypes.WinDLL("user32", use_last_error=True)
        user32_local.DefWindowProcW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        user32_local.DefWindowProcW.restype = ctypes.c_ssize_t
        kernel32_local = ctypes.WinDLL("kernel32", use_last_error=True)
        hinst = kernel32_local.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = WNDPROC(lambda h, m, wp, lp: user32_local.DefWindowProcW(h, m, wp, lp))
        wc.lpszClassName = _unique_class_name("GroguHotkeyProbe")
        wc.hInstance = hinst
        if not user32_local.RegisterClassW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != ERROR_CLASS_ALREADY_EXISTS:
                result["err"] = err
                result["msg"] = f"Could not set up test window (error {err})."
                return
        hwnd = user32_local.CreateWindowExW(
            0, wc.lpszClassName, "Grogu", 0,
            0, 0, 0, 0, HWND_MESSAGE, None, hinst, None,
        )
        if not hwnd:
            result["err"] = -1
            result["msg"] = "Could not create test window."
            return
        ok = user32_local.RegisterHotKey(hwnd, hotkey_id, modifiers | MOD_NOREPEAT, vk)
        if not ok:
            err = ctypes.get_last_error()
            result["err"] = err
            if err == ERROR_HOTKEY_ALREADY_REGISTERED:
                result["msg"] = (
                    f"{spec} is {hotkey_error_text(err)}."
                )
            else:
                result["msg"] = f"Could not register {spec}: {hotkey_error_text(err)}."
        else:
            result["err"] = 0
            result["msg"] = f"{spec} is free to register."
        if ok:
            user32_local.UnregisterHotKey(hwnd, hotkey_id)
        user32_local.DestroyWindow(hwnd)

    thread = threading.Thread(target=probe, daemon=True)
    thread.start()
    thread.join(timeout=5.0)
    if not result:
        return False, "Test timed out."
    return (result["err"] == 0), result.get("msg", "")
