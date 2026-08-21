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
import os
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
VK_A = 0x41
VK_Z = 0x5A
VK_BACK = 0x08
VK_DELETE = 0x2E
VK_CAPITAL = 0x14

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_NAME_WIN32 = 0


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
user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = wintypes.SHORT
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, ctypes.c_wchar_p, ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
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
user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.CloseClipboard.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HANDLE
kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
kernel32.GlobalUnlock.restype = wintypes.BOOL

# AllowSetForegroundWindow — tells Windows the next SetForegroundWindow call is OK
user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
user32.AllowSetForegroundWindow.restype = wintypes.BOOL

# ForegroundLockTimeout — we temporarily set this to 0 so focus isn't blocked
user32.SystemParametersInfoW.argtypes = [
    wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT
]
user32.SystemParametersInfoW.restype = wintypes.BOOL

SPI_GETFOREGROUNDLOCKTIMEOUT = 0x1000
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x1001
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

# Window text retrieval
user32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, wintypes.INT]
user32.GetWindowTextW.restype = wintypes.INT
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = wintypes.INT

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


def get_window_title(hwnd: int) -> str:
    """Get the title text of a window for debugging."""
    if not hwnd:
        return "<none>"
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return "<untitled>"
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


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


def _fake_input_unlock() -> None:
    """Simulate a brief Alt press+release to satisfy the Windows foreground
    lock.  ``SetForegroundWindow`` only succeeds when the calling process
    "received the last input event"; a synthetic Alt keystroke tricks the
    OS into granting that permission.
    """
    try:
        down = INPUT()
        down.type = INPUT_KEYBOARD
        down.u.ki.wVk = 0x12  # VK_MENU (Alt)
        up = INPUT()
        up.type = INPUT_KEYBOARD
        up.u.ki.wVk = 0x12
        up.u.ki.dwFlags = KEYEVENTF_KEYUP
        arr = (INPUT * 2)(down, up)
        user32.SendInput(2, arr, _INPUT_SIZE)
    except Exception:  # noqa: BLE001
        pass


def focus_window(hwnd: int) -> bool:
    """Best-effort: bring ``hwnd`` to the foreground so typing lands there.

    Uses the Alt-key input unlock + AttachThreadInput + AllowSetForegroundWindow
    + the ForegroundLockTimeout hack.  Returns True when the window is (very
    likely) focused.
    """
    if not hwnd:
        return False
    try:
        cur_tid = kernel32.GetCurrentThreadId()
        target_tid = user32.GetWindowThreadProcessId(hwnd, None)

        log.debug("focus_window: hwnd=%s title=%r target_tid=%d cur_tid=%d",
                  hwnd, get_window_title(hwnd), target_tid, cur_tid)

        # AllowSetForegroundWindow — tell the OS our next SetForegroundWindow is legit
        user32.AllowSetForegroundWindow(target_tid if target_tid else -1)

        # Temporarily disable the foreground-lock timeout so Windows doesn't
        # block us from stealing focus.
        old_timeout = wintypes.UINT(0)
        user32.SystemParametersInfoW(
            SPI_GETFOREGROUNDLOCKTIMEOUT, 0,
            ctypes.byref(old_timeout), 0
        )
        user32.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT, 0,
            ctypes.byref(wintypes.UINT(0)),
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
        )

        # Alt-key trick: make Windows think we received input so the
        # foreground lock doesn't block SetForegroundWindow.
        _fake_input_unlock()

        attached = False
        if target_tid and target_tid != cur_tid:
            attached = bool(user32.AttachThreadInput(cur_tid, target_tid, True))

        ok = bool(user32.SetForegroundWindow(hwnd))

        if attached:
            user32.AttachThreadInput(cur_tid, target_tid, False)

        # Restore the original foreground-lock timeout
        user32.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT, 0,
            ctypes.byref(old_timeout),
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
        )

        if not ok:
            log.warning("SetForegroundWindow(%s) failed (title=%r)", hwnd, get_window_title(hwnd))
        return ok
    except Exception:  # noqa: BLE001
        log.warning("focus_window failed", exc_info=True)
        return False


def _verify_foreground(hwnd: int) -> bool:
    """Check that the window is actually the foreground window now."""
    current = int(user32.GetForegroundWindow() or 0)
    return current == hwnd


def focus_window_with_retry(hwnd: int, retries: int = 3, delay: float = 0.08) -> bool:
    """Try to focus the window with retries. Returns True on success."""
    for attempt in range(retries):
        if focus_window(hwnd):
            time.sleep(delay)
            if _verify_foreground(hwnd):
                log.debug("focus_window succeeded on attempt %d for hwnd=%s title=%r",
                          attempt + 1, hwnd, get_window_title(hwnd))
                return True
            log.debug("focus_window: SetForegroundWindow returned True but "
                      "hwnd not yet foreground (attempt %d, current fg=%s)",
                      attempt + 1, get_foreground_hwnd())
        else:
            log.debug("focus_window: SetForegroundWindow returned False (attempt %d)", attempt + 1)
        # exponential backoff: 0.08, 0.16, 0.32
        time.sleep(delay * (2 ** attempt))
    log.warning("focus_window: failed to focus hwnd=%s title=%r after %d attempts",
                hwnd, get_window_title(hwnd), retries)
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
        log.warning("clipboard write failed", exc_info=True)
        return False


def set_clipboard_text(text: str) -> bool:
    """Public wrapper: put ``text`` on the clipboard as Unicode text."""
    return _set_clipboard(text)


def _paste_from_clipboard() -> None:
    _send_one(_vk_input(VK_CONTROL, False))
    _send_pair(_vk_input(VK_V, False), _vk_input(VK_V, True))
    _send_one(_vk_input(VK_CONTROL, True))


# Win32 paste constants
WM_PASTE = 0x0302
WM_CHAR = 0x0102
EM_SETSEL = 0x00B1
GW_CHILD = 5

user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND


def _find_edit_child(hwnd: int) -> int:
    """Walk the child window tree to find a text-edit control.

    Returns the first child with a recognized edit class, or the deepest
    leaf window (best-effort for custom controls like Notepad's
    ``RichEditD2DPT``).  Works for standard Edit, RichEdit, Scintilla,
    and modern Notepad/Windows apps.
    """
    _EDIT_CLASSES = {
        "Edit", "RichEdit", "RICHEDIT20W", "RICHEDIT50W",
        "Scintilla",
        "RichEditD2DPT",        # Windows 11 Notepad text control
        "NotepadMainWindow",    # Win10 Notepad
    }
    # Classes that are edit CONTAINERS (not the actual text control) —
    # we skip these in favor of their children.
    _CONTAINER_CLASSES = {"NotepadTextBox"}
    best = 0  # deepest leaf if no known class matches
    # BFS through the child tree
    queue_ = [(hwnd, 0)]
    while queue_:
        parent, depth = queue_.pop(0)
        child = user32.GetWindow(parent, GW_CHILD)
        while child:
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(child, cls, 256)
            if cls.value in _EDIT_CLASSES:
                log.debug("_find_edit_child: found %s at hwnd=%s depth=%d",
                          cls.value, child, depth)
                return child
            if cls.value not in _CONTAINER_CLASSES:
                best = child  # track deepest non-container leaf
            queue_.append((child, depth + 1))
            child = user32.GetWindow(child, 2)  # GW_HWNDNEXT
    return best


def _get_text_length(hwnd: int) -> int:
    """Return the character count of an edit control (EM_GETTEXTLENGTH)."""
    try:
        return int(user32.SendMessageW(hwnd, 0x000E, 0, 0))
    except Exception:  # noqa: BLE001
        return -1


def _direct_paste(hwnd: int) -> bool:
    """Paste clipboard content directly into *hwnd* via WM_PASTE.

    This works WITHOUT focusing the window — ``SendMessage`` delivers the
    message straight to the target's message queue.  It inserts at the
    control's current caret, exactly where the user's cursor was.

    Tries the edit child first (RichEditD2DPT / Edit / Scintilla …), then
    the main window as a fallback.  Returns True only when the paste was
    accepted *and* the text length actually grew, so callers never report
    success for a silent no-op.
    """
    # The control we paste into must have a caret position. If the edit
    # child is not focused, WM_PASTE still uses its last selection/caret.
    edit = _find_edit_child(hwnd)
    targets = [edit] if edit else []
    # Also try the main window itself (some apps handle WM_PASTE at the top)
    targets.append(hwnd)

    # Verify against the edit control's own length (EM_GETTEXTLENGTH on the
    # top-level window is unreliable).
    measure = edit if edit else hwnd
    before_len = _get_text_length(measure)

    for target in targets:
        try:
            result = user32.SendMessageW(target, WM_PASTE, 0, 0)
            log.info("_direct_paste: target=%s result=%s", target, result)
            time.sleep(0.05)
            after_len = _get_text_length(measure)
            if after_len > before_len:
                log.info("_direct_paste: verified — length %d -> %d",
                         before_len, after_len)
                return True
            log.debug("_direct_paste: target %s did not grow length "
                      "(%d -> %d), trying next", target, before_len, after_len)
        except Exception:  # noqa: BLE001
            log.debug("_direct_paste: target %s failed", target, exc_info=True)
    log.warning("_direct_paste: all attempts failed for hwnd=%s", hwnd)
    return False


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


def press_combo(modifiers: list[int] | None, key: int) -> None:
    """Press a key chord: optional modifiers down, tap ``key``, release mods.

    E.g. ``press_combo([VK_CONTROL], VK_Z)`` sends Ctrl+Z.
    """
    mods = list(modifiers or [])
    for m in mods:
        _send_one(_vk_input(m, False))
    _send_pair(_vk_input(key, False), _vk_input(key, True))
    for m in reversed(mods):
        _send_one(_vk_input(m, True))


def get_caps_lock() -> bool:
    """True when Caps Lock is currently toggled on."""
    return bool(user32.GetKeyState(VK_CAPITAL) & 1)


def set_caps_lock(on: bool) -> None:
    """Toggle Caps Lock so its state matches ``on`` (no-op when it already does)."""
    if get_caps_lock() == on:
        return
    _send_pair(_vk_input(VK_CAPITAL, False), _vk_input(VK_CAPITAL, True))


def hwnd_exe_name(hwnd: int) -> str | None:
    """Lowercase executable filename owning ``hwnd`` (e.g. "notepad.exe").

    Returns None when the process can't be inspected (elevated apps,
    vanished windows). Used for per-app insertion-mode profiles.
    """
    if not hwnd:
        return None
    pid = hwnd_pid(hwnd)
    if not pid:
        return None
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, PROCESS_NAME_WIN32,
                                               buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(handle)
    return None


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
    # Diagnostic: log what we're about to do
    cur_fg = get_foreground_hwnd()
    cur_fg_title = get_window_title(cur_fg)
    target_title = get_window_title(target_hwnd) if target_hwnd else "<none>"
    own = is_own_window(target_hwnd) if target_hwnd else False

    log.info("send_text START: target_hwnd=%s title=%r own=%s | current_fg=%s fg_title=%r | mode=%s",
             target_hwnd, target_title, own, cur_fg, cur_fg_title, mode)
    log.info("send_text: text=%r (len=%d)", text[:100], len(text))

    # ---- Focus the target window ----
    _focused_ok = False
    if target_hwnd and not own:
        if cur_fg != target_hwnd:
            log.info("send_text: focusing target (current fg=%s, target=%s)", cur_fg, target_hwnd)
            _focused_ok = focus_window_with_retry(target_hwnd, retries=3, delay=0.1)
            new_fg = get_foreground_hwnd()
            log.info("send_text: focus result=%s, new_fg=%s match=%s",
                     _focused_ok, new_fg, new_fg == target_hwnd)
            if not _focused_ok or new_fg != target_hwnd:
                log.warning("send_text: focus did NOT land on target — "
                            "new_fg=%s title=%r (target was %s)",
                            new_fg, get_window_title(new_fg), target_hwnd)
        else:
            log.info("send_text: target already in foreground")
            _focused_ok = True
        # Additional settle time after focus (some apps need it)
        time.sleep(0.05)
    elif own:
        log.info("send_text: target is our own window — typing directly (foreign_hwnd may be needed)")
    else:
        log.info("send_text: no target_hwnd — typing to current foreground")

    # ---- Clipboard mode ----
    if mode == "clipboard" or (mode == "smart" and target_hwnd and not own):
        log.info("send_text: using clipboard mode (mode=%s, focused=%s)",
                 mode, _focused_ok)
        if not text:
            return True
        if not _set_clipboard(text):
            return False
        # Strategy 1: WM_PASTE straight into the target's edit control.
        #             Most reliable: no focus needed, inserts at the caret.
        if target_hwnd and not own:
            if _direct_paste(target_hwnd):
                log.info("send_text: direct WM_PASTE into target succeeded")
                return True
            log.warning("send_text: direct WM_PASTE did not land — "
                        "falling back to focus + Ctrl+V")
        # Strategy 2: If we have focus, Ctrl+V works everywhere
        if _focused_ok or (not target_hwnd) or own:
            log.info("send_text: pasting via Ctrl+V (focused=%s)", _focused_ok)
            _paste_from_clipboard()
            return True
        # Strategy 3: Focus failed — retry WM_PASTE, then Ctrl+V as a last
        #             resort (might land if focus snuck back)
        log.info("send_text: focus failed, retrying _direct_paste into hwnd=%s",
                 target_hwnd)
        if _direct_paste(target_hwnd):
            log.info("send_text: _direct_paste retry succeeded")
            return True
        log.info("send_text: _direct_paste failed, falling back to Ctrl+V")
        _paste_from_clipboard()
        return True

    if mode == "smart":
        # Smart mode: try keystrokes, fallback to clipboard if focus fails
        if target_hwnd and not own:
            focused = focus_window_with_retry(target_hwnd, retries=2, delay=0.05)
            if not focused:
                log.info("send_text: smart mode — focus failed, falling back to clipboard")
                if not text:
                    return True
                if not _set_clipboard(text):
                    return False
                _paste_from_clipboard()
                return True
            time.sleep(0.03)

    log.info("send_text: typing %d chars via keystrokes", len(text))
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

    # Final diagnostic
    final_fg = get_foreground_hwnd()
    log.info("send_text DONE: typed %d chars | final_fg=%s fg_title=%r",
             len(text), final_fg, get_window_title(final_fg))
    return True
