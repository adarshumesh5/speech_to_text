"""Start-with-Windows: manages the HKCU Run entry for Grogu.

The entry launches Grogu with ``--minimized`` so an auto-start lands quietly
in the tray instead of popping a window over whatever you're doing.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Grogu"
LEGACY_VALUE_NAME = "Sotto"  # stale entry from before the rename — removed on enable


def launch_command() -> str:
    """The command line used for the Run entry."""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        return f'"{exe}" --minimized'
    # dev mode: pythonw so no console window appears
    python = sys.executable
    if python.lower().endswith("python.exe"):
        python = python[:-4] + "w.exe"
    if not os.path.exists(python):
        python = sys.executable
    return f'"{python}" -m grogu --minimized'


def is_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """Enable/disable auto-start. Returns True on success."""
    try:
        import winreg

        if enabled:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ,
                                  launch_command())
            try:  # drop the pre-rename entry so it can't launch a dead exe
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                    winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, LEGACY_VALUE_NAME)
            except OSError:
                pass
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        log.info("auto-start %s", "enabled" if enabled else "disabled")
        return True
    except OSError as e:
        log.warning("could not update auto-start: %s", e)
        return False


def restart_if_installed() -> None:
    """Re-apply the Run entry after an install moves the exe (best effort)."""
    if is_enabled():
        set_enabled(True)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "status":
        print("enabled" if is_enabled() else "disabled")
        if is_enabled():
            print(launch_command())
    elif action == "on":
        print("ok" if set_enabled(True) else "failed")
    elif action == "off":
        print("ok" if set_enabled(False) else "failed")
