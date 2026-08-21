"""Taskbar jump list — right-click the taskbar icon for quick actions.

Implemented via the managed WPF ``System.Windows.Shell.JumpList`` API through
a small PowerShell helper (``scripts/jumplist.ps1``). Raw ctypes
``ICustomDestinationList`` calls crash inside ``windows.storage.dll`` on some
Windows builds when made from Python processes (observed deterministically on
this machine), while the WPF path is reliable — so we use the helper.    Each task launches ``Grogu.exe --<command>``; the running instance receives
    it through the command pipe (see ``grogu.ipc``). Best effort: failures are
    logged and ignored — the tray menu covers the same actions.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys

log = logging.getLogger(__name__)

AUMID = "Grogu"


def set_app_user_model_id(aumid: str = AUMID) -> None:
    """Group the taskbar button under our AppUserModelID."""
    try:
        import ctypes

        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(aumid))
    except Exception:  # noqa: BLE001
        log.debug("could not set AppUserModelID", exc_info=True)


def _helper_path() -> str | None:
    """Locate jumplist.ps1: bundled copy when frozen, scripts/ in the repo."""
    candidates: list[str] = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(sys._MEIPASS, "jumplist.ps1"))
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates.append(os.path.join(root, "scripts", "jumplist.ps1"))
        candidates.append(os.path.join(root, "jumplist.ps1"))
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def install_jump_list(exe_path: str | None = None) -> bool:
    """Write the Tasks jump list (New recording / Dictionary / Settings).

    Returns True when the helper reported success. Never raises; the tray
    menu covers the same actions when this is unavailable.
    """
    if os.name != "nt":
        return False
    helper = _helper_path()
    if helper is None:
        log.warning("jumplist.ps1 not found")
        return False
    exe_path = exe_path or (sys.executable if getattr(sys, "frozen", False) else "")
    if not exe_path or not os.path.exists(exe_path):
        log.warning("jump list: no executable path to attach tasks to")
        return False
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
             "-File", helper, "-ExePath", exe_path],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("jump list helper failed to start: %s", e)
        return False
    out = (proc.stdout or "") + (proc.stderr or "")
    if "JUMPLIST_OK" in out:
        log.info("jump list installed")
        return True
    log.warning("jump list helper reported failure: %s", out.strip()[:400])
    return False
