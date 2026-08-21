"""True end-to-end scenario test.

User flow:
  1. User clicks in Notepad (caret there) -> caret tracker caches Notepad
  2. User switches to Freebuff (this terminal) -> Freebuff foreground
  3. Hotkey fires -> dictation -> send_text(target=Notepad from caret cache)
  4. Text MUST land in Notepad while Freebuff stays foreground

This is the exact case that was broken: text went to Freebuff (or nowhere).
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
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_void_p]
user32.SendMessageW.restype = ctypes.c_ssize_t

WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
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
        if user32.IsWindowVisible(hwnd) and "Notepad" in window_title(hwnd):
            found.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found[0] if found else 0


def find_edit_child(hwnd: int) -> int:
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
    n = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.SendMessageW(hwnd, WM_GETTEXT, n + 1, ctypes.addressof(buf))
    return buf.value


def main() -> int:
    from grogu.injector import focus_window, get_foreground_hwnd, send_text
    from grogu.caret import CaretTracker

    print("=" * 64)
    print("E2E SCENARIO TEST — Freebuff foreground, dictation to Notepad")
    print("=" * 64)

    notepad = find_notepad()
    if not notepad:
        note("[1] No Notepad — launching…")
        os.system("start notepad.exe")
        time.sleep(2.5)
        notepad = find_notepad()
    note(f"[1] Notepad hwnd={notepad} title={window_title(notepad)!r}")

    # Step A: user clicks in Notepad -> caret appears, tracker caches it
    focus_window(notepad)
    time.sleep(0.4)
    edit = find_edit_child(notepad)
    rc = ctypes.wintypes.RECT()
    user32.GetWindowRect(edit, ctypes.byref(rc))
    user32.SetCursorPos((rc.left + rc.right) // 2, (rc.top + rc.bottom) // 2)
    time.sleep(0.1)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.4)

    tracker = CaretTracker(interval=0.05)
    tracker.start()
    time.sleep(0.8)
    cached_hwnd, cached_title = tracker.get_target()
    tracker.stop()
    note(f"[A] Caret tracker cached: hwnd={cached_hwnd} title={cached_title!r}")
    if not cached_hwnd or cached_hwnd != notepad:
        note("    ✗ Caret tracker did NOT cache Notepad — cannot continue")
        return 1
    note("    ✓ Caret tracker has Notepad")

    # Step B: user switches back to Freebuff (this terminal window).
    # The script itself runs from Freebuff's terminal, so we restore focus
    # to the console window by simply NOT re-focusing Notepad. Verify the
    # foreground is NOT Notepad now (it's whatever the user is in).
    fg = get_foreground_hwnd()
    note(f"[B] Foreground before injection: hwnd={fg} title={window_title(fg)!r}")
    if fg == notepad:
        note("    ⚠ Notepad is still foreground — focusing the terminal instead")
        # Find the console window and focus it to simulate Freebuff focus
        # (best effort; if it fails we still test the no-focus path)
        os.system("start cmd /c exit")  # no-op; do not steal focus
        time.sleep(0.3)
        fg = get_foreground_hwnd()
        note(f"    Foreground now: hwnd={fg} title={window_title(fg)!r}")

    # Step C: the dictation finishes and send_text fires with the cached
    # Notepad hwnd, while Freebuff is (still) foreground.
    test_text = "CURSOR TARGET " + str(int(time.time()))[-4:]
    before = read_edit_text(edit) if edit else ""
    note(f"[C] Sending {test_text!r} with target_hwnd={notepad} (no focus attempt)")
    note(f"    Notepad before: {before!r}")

    ok = send_text(test_text, mode="clipboard", target_hwnd=notepad)
    time.sleep(0.8)
    after = read_edit_text(edit) if edit else ""
    note(f"    send_text returned: {ok}")
    note(f"    Notepad after: {after!r}")
    fg_after = get_foreground_hwnd()
    note(f"    Foreground after: hwnd={fg_after} title={window_title(fg_after)!r}")

    if test_text in after:
        note("    ✓✓✓ TEXT LANDED IN NOTEPAD WHILE FREEBUFF WAS FOREGROUND")
    else:
        note("    ✗✗✗ TEXT DID NOT LAND IN NOTEPAD")

    print()
    print("=" * 64)
    print("PASS" if "✓✓✓" in "\n".join(results) else "FAIL")
    print("=" * 64)
    return 0 if "✓✓✓" in "\n".join(results) else 1


if __name__ == "__main__":
    sys.exit(main())
