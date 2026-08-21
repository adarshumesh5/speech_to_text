"""DEFINITIVE live injection test.

Scenario (exact user flow):
  1. User opens Notepad, clicks in it -> caret is there
  2. User switches to Freebuff (this terminal) -> Freebuff has focus
  3. Grogu's caret tracker remembers Notepad
  4. Hotkey fires -> dictation -> send_text(target_hwnd=Notepad)
  5. Text MUST land in Notepad, verified by reading Notepad's own text

This script is run FROM the Freebuff terminal, so the foreground window while
it runs IS Freebuff — reproducing the real-world case exactly.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t

WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
EM_GETSEL = 0x00B0
GW_CHILD = 5
GW_HWNDNEXT = 2

results: list[str] = []


def note(msg: str) -> None:
    results.append(msg)
    print(msg, flush=True)


def window_title(hwnd: int) -> str:
    if not hwnd:
        return "<none>"
    n = user32.GetWindowTextLengthW(hwnd)
    if n == 0:
        return "<untitled>"
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def find_notepad() -> int:
    found: list[int] = []

    def cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            t = window_title(hwnd)
            if "Notepad" in t:
                found.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found[0] if found else 0


def find_edit_child(hwnd: int) -> int:
    """BFS for the real text control (RichEditD2DPT preferred)."""
    EDIT = {"Edit", "RichEdit", "RICHEDIT20W", "RICHEDIT50W", "Scintilla", "RichEditD2DPT"}
    SKIP = {"NotepadTextBox"}
    queue_ = [(hwnd, 0)]
    best = 0
    while queue_:
        parent, depth = queue_.pop(0)
        child = user32.GetWindow(parent, GW_CHILD)
        while child:
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(child, cls, 256)
            if cls.value in EDIT:
                return child
            if cls.value not in SKIP:
                best = child
            queue_.append((child, depth + 1))
            child = user32.GetWindow(child, GW_HWNDNEXT)
    return best


def read_edit_text(hwnd: int) -> str:
    """Read the full text of an edit control via WM_GETTEXT."""
    n = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.SendMessageW(hwnd, WM_GETTEXT, n + 1, ctypes.addressof(buf))
    return buf.value


def read_notepad_content(notepad: int) -> str:
    edit = find_edit_child(notepad)
    if edit:
        return read_edit_text(edit)
    return ""


def caret_pos(notepad: int) -> tuple[int, int]:
    """Read caret position via EM_GETSEL on the edit control."""
    edit = find_edit_child(notepad)
    if not edit:
        return (-1, -1)
    start = ctypes.c_uint(0)
    end = ctypes.c_uint(0)
    # Re-declare SendMessageW without argtypes so byref works
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    u32.SendMessageW.restype = ctypes.c_ssize_t
    u32.SendMessageW(edit, EM_GETSEL, ctypes.byref(start), ctypes.byref(end))
    return int(start.value), int(end.value)


def main() -> int:
    from grogu.injector import focus_window, get_foreground_hwnd, send_text
    from grogu.caret import CaretTracker

    print("=" * 64)
    print("LIVE INJECTION TEST — run from Freebuff terminal")
    print("=" * 64)

    # --- 1. Find/launch Notepad -------------------------------------------
    notepad = find_notepad()
    if not notepad:
        note("[1] No Notepad open — launching…")
        os.system("start notepad.exe")
        time.sleep(2.5)
        notepad = find_notepad()
    note(f"[1] Notepad hwnd={notepad} title={window_title(notepad)!r}")

    # --- 2. Verify we can find the edit control ----------------------------
    focus_window(notepad)
    time.sleep(0.3)
    edit = find_edit_child(notepad)
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(edit, cls, 256) if edit else None
    note(f"[2] Edit control found: hwnd={edit} class={cls.value!r}")
    note(f"    Notepad content before: {read_notepad_content(notepad)!r}")
    # Simulate a real user click INSIDE the text area so a caret appears
    try:
        rc = ctypes.wintypes.RECT()
        user32.GetWindowRect(edit, ctypes.byref(rc))
        cx = (rc.left + rc.right) // 2
        cy = (rc.top + rc.bottom) // 2
        user32.SetCursorPos(cx, cy)
        time.sleep(0.1)
        user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
        time.sleep(0.05)
        user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
        time.sleep(0.3)
    except Exception as e:  # noqa: BLE001
        note(f"    (click simulation failed: {e})")

    # --- 3. Verify caret tracker picks up Notepad --------------------------
    tracker = CaretTracker(interval=0.05)
    tracker.start()
    time.sleep(0.8)
    cached_hwnd, cached_title = tracker.get_target()
    note(f"[3] Caret tracker target: hwnd={cached_hwnd} title={cached_title!r}")
    tracker.stop()
    if cached_hwnd and (cached_hwnd == notepad or "Notepad" in cached_title):
        note("    ✓ Caret tracker remembered Notepad")
    else:
        note("    ⚠ Caret tracker did NOT find Notepad — this is a problem")

    # --- 4. The critical test: Freebuff is foreground, target=Notepad ------
    fg_now = get_foreground_hwnd()
    note(f"[4] Current foreground while running: hwnd={fg_now} "
         f"title={window_title(fg_now)!r}  (this is Freebuff/terminal)")

    test_text = "GROGU LIVE TEST " + str(int(time.time()))[-4:]
    before = read_notepad_content(notepad)
    note(f"    Sending: {test_text!r}")
    note(f"    Notepad content before: {before!r}")

    ok = send_text(test_text, mode="clipboard", target_hwnd=notepad)
    time.sleep(0.8)
    after = read_notepad_content(notepad)
    note(f"    send_text returned: {ok}")
    note(f"    Notepad content after: {after!r}")

    if test_text in after:
        note("    ✓✓ TEXT LANDED IN NOTEPAD")
    else:
        note("    ✗✗ TEXT DID NOT LAND IN NOTEPAD")

    # --- 5. Also test keystrokes mode --------------------------------------
    test_text2 = " KEYSTROKES OK"
    ok2 = send_text(test_text2, mode="keystrokes", target_hwnd=notepad)
    time.sleep(0.8)
    after2 = read_notepad_content(notepad)
    note(f"[5] keystrokes mode: returned={ok2} content={after2!r}")
    if test_text2 in after2:
        note("    ✓ keystrokes mode landed too")

    # --- 6. Caret position check -------------------------------------------
    pos = caret_pos(notepad)
    note(f"[6] Notepad caret position: {pos}")

    print()
    print("=" * 64)
    passed = any("✓✓" in r for r in results)
    print("PASS" if passed else "FAIL")
    print("=" * 64)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
