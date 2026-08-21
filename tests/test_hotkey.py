"""Tests for grogu.hotkey.parse_hotkey (pure parsing, no window)."""

import pytest

from grogu.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    parse_hotkey,
)


def test_ctrl_shift_space():
    mod, vk = parse_hotkey("Ctrl+Shift+Space")
    assert mod == (MOD_CONTROL | MOD_SHIFT)
    assert vk == 0x20


def test_alt_f4():
    mod, vk = parse_hotkey("Alt+F4")
    assert mod == MOD_ALT
    assert vk == 0x73


def test_plain_f9():
    mod, vk = parse_hotkey("F9")
    assert mod == 0
    assert vk == 0x78


def test_single_letter():
    mod, vk = parse_hotkey("Ctrl+Shift+A")
    assert mod == (MOD_CONTROL | MOD_SHIFT)
    assert vk == ord("A")


def test_digit():
    mod, vk = parse_hotkey("Ctrl+1")
    assert vk == ord("1")


def test_meta_windows_key():
    mod, vk = parse_hotkey("Meta+Space")
    assert mod == MOD_WIN


def test_case_insensitive():
    mod, vk = parse_hotkey("ctrl+shift+space")
    assert mod == (MOD_CONTROL | MOD_SHIFT)
    assert vk == 0x20


def test_invalid_modifier():
    with pytest.raises(ValueError):
        parse_hotkey("Super+F1")


def test_empty():
    with pytest.raises(ValueError):
        parse_hotkey("")


def test_bad_key():
    with pytest.raises(ValueError):
        parse_hotkey("Ctrl+F99")


# --- real registration (Windows session only) ------------------------------

import ctypes
import sys
import threading
import time
from ctypes import wintypes

from grogu.hotkey import HotkeyListener

KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_SHIFT = 0x10


def _user32():
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD,
                              ctypes.c_ulong]
    return u


def _press_combo(user32, spec: str) -> None:
    """Hold the modifiers and tap the key via keybd_event (system-wide)."""
    mods, vk = parse_hotkey(spec)
    held: list[int] = []
    if mods & 0x0002:
        held.append(VK_CONTROL)
    if mods & 0x0004:
        held.append(VK_SHIFT)
    if mods & 0x0001:
        held.append(0x12)  # VK_MENU
    for k in held:
        user32.keybd_event(k, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    for k in reversed(held):
        user32.keybd_event(k, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.15)


def _start_listener(spec: str, events: list, hotkey_id: int):
    registered = threading.Event()
    errors: list[str] = []

    def on_registered(_s):
        registered.set()

    def on_error(msg):
        errors.append(msg)
        registered.set()

    listener = HotkeyListener(
        spec, on_down=lambda: events.append("down"),
        on_up=lambda: events.append("up"),
        on_error=on_error, on_registered=on_registered,
        hotkey_id=hotkey_id,
    )
    listener.start()
    return listener, registered, errors


def test_two_listeners_both_fire():
    """The mute-hotkey/restart scenario: a second listener in the same
    process must get its own wndproc and actually fire. Regression for the
    fixed-class-name bug (1410 reuse inherited the first wndproc)."""
    if sys.platform != "win32":
        pytest.skip("requires a Windows desktop session")
    user32 = _user32()
    events_a: list = []
    events_b: list = []
    a, reg_a, errs_a = _start_listener("Ctrl+Shift+F13", events_a, hotkey_id=11)
    b, reg_b, errs_b = _start_listener("Ctrl+Shift+F14", events_b, hotkey_id=12)
    try:
        assert reg_a.wait(3.0), f"listener A did not register: {errs_a}"
        assert reg_b.wait(3.0), f"listener B did not register: {errs_b}"
        if errs_a or errs_b:
            pytest.skip(f"hotkey conflicted in this session: {errs_a + errs_b}")
        # both are registered — now prove B's callback fires (not A's)
        _press_combo(user32, "Ctrl+Shift+F14")
        assert "down" in events_b, f"listener B never fired: {events_b}"
        assert "down" not in events_a, f"listener A wrongly received B's key: {events_a}"
    finally:
        a.stop()
        b.stop()


def test_restart_re_registers_and_fires():
    """stop() then start() again must keep working (hotkey changes in
    Settings, or tray re-registration, must not silently kill the key)."""
    if sys.platform != "win32":
        pytest.skip("requires a Windows desktop session")
    user32 = _user32()
    events: list = []
    listener, registered, errors = _start_listener(
        "Ctrl+Shift+F15", events, hotkey_id=13)
    try:
        assert registered.wait(3.0), f"first registration failed: {errors}"
        if errors:
            pytest.skip(f"hotkey conflicted in this session: {errors}")
        listener.stop()
        time.sleep(0.3)
        # same listener object, started again (the class survives; a fresh
        # unique class name must be used so the wndproc matches)
        events.clear()
        registered.clear()
        errors.clear()
        listener._on_error = lambda m: errors.append(m)
        listener._on_registered = lambda s: registered.set()
        listener.start()
        assert registered.wait(3.0), f"re-registration failed: {errors}"
        if errors:
            pytest.skip(f"hotkey conflicted in this session: {errors}")
        _press_combo(user32, "Ctrl+Shift+F15")
        assert "down" in events, f"re-registered listener never fired: {events}"
    finally:
        listener.stop()
