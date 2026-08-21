"""Application entry point: wires config, service, dictionary, history,
main window (primary) and tray (secondary).

Also owns Windows integration: AppUserModelID, the taskbar jump list, the
single-instance mutex + command pipe (``Grogu.exe --dictate`` etc. reach the
running instance), and the start-minimized behaviour.
"""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from sotto import APP_ID, APP_NAME, APP_TAGLINE, __version__
from sotto.config import APP_DATA_DIR, Config, migrate_from_sotto
from sotto.dictation import DictationService
from sotto.dictionary import Dictionary
from sotto.history import HistoryStore
from sotto.ipc import CommandServer, send_command
from sotto.jumplist import install_jump_list, set_app_user_model_id
from sotto.ui.main_window import MainWindow
from sotto.ui.settings_window import SettingsWindow
from sotto.ui.theme import QSS
from sotto.ui.tray import Tray, asset_path

log = logging.getLogger(__name__)

COMMANDS: queue.Queue[dict] = queue.Queue()


def _setup_logging(level: str) -> str:
    log_path = os.path.join(APP_DATA_DIR, "sotto.log")
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    logging.basicConfig(
        filename=log_path,
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    return log_path


def _acquire_single_instance(name: str) -> bool:
    """True if we are the only instance; False if another is already running."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, f"Local\\{name}")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def _parse_args(argv: list[str]) -> dict[str, bool]:
    """Map ``--minimized`` / ``--dictate`` / ``--dictionary`` / ``--settings``."""
    wanted: dict[str, bool] = {
        "minimized": False, "dictate": False,
        "dictionary": False, "settings": False,
    }
    for arg in argv:
        if arg in ("--minimized", "-m"):
            wanted["minimized"] = True
        elif arg in ("--dictate", "-d"):
            wanted["dictate"] = True
        elif arg in ("--dictionary",):
            wanted["dictionary"] = True
        elif arg in ("--settings",):
            wanted["settings"] = True
    return wanted


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    wanted = _parse_args(argv)

    if not _acquire_single_instance(APP_ID):
        # Another instance is running: forward the requested action to it via
        # the command pipe and exit quietly. No action = just focus the window.
        if wanted["dictate"]:
            send_command("dictate")
        elif wanted["dictionary"]:
            send_command("dictionary")
        elif wanted["settings"]:
            send_command("settings")
        else:
            send_command("show")
        return 0

    migrate_from_sotto()  # first run after the rename: copy old Sotto data
    config = Config.load()
    log_path = _setup_logging(config.log_level)

    # Windows integration: group the taskbar icon, enable the jump list.
    set_app_user_model_id(APP_ID)
    exe_path = (sys.executable if getattr(sys, "frozen", False) else "")
    install_jump_list(exe_path=exe_path)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(QSS)

    icon = QIcon(asset_path("app.ico"))
    if not icon.isNull():
        app.setWindowIcon(icon)

    dictionary = Dictionary()
    history = HistoryStore()
    service = DictationService(config, dictionary=dictionary)
    window = MainWindow(service, history, dictionary, on_settings=lambda: None)
    settings = SettingsWindow(config, service)

    def show_settings() -> None:
        settings.show()
        settings.raise_()
        settings.activateWindow()

    window.on_settings = show_settings
    app._sotto_window = window
    service.dictation_done.connect(_on_dictation_done)
    service.error.connect(window.on_service_error)

    tray = Tray(app, service, history, window,
                on_settings=show_settings,
                on_undo=service.undo_last_correction)
    window.set_tray(tray)

    # IPC: commands arrive on a background thread, executed here on the GUI
    # thread via a 200ms poll, so all Qt access stays on one thread.
    def _enqueue(payload: dict) -> None:
        COMMANDS.put(payload)

    server = CommandServer(_enqueue)
    server.start()

    poll = QTimer()
    poll.setInterval(200)
    poll.timeout.connect(_dispatch_commands)
    poll.start()

    service.start()
    tray.show()

    # Always start hidden to avoid stealing focus from the user's app.
    # The window shows only when the user explicitly opens it.
    window.hide()
    if wanted["dictate"]:
        service.record("jump")
    elif wanted["dictionary"]:
        window.tabs.setCurrentIndex(1)
    elif wanted["settings"]:
        show_settings()
    elif wanted["minimized"]:
        pass  # already handled above

    if not config._extra.get("first_run_done"):
        tray.notify(
            f"{APP_NAME} is ready",
            f"Hold {config.hotkey} and speak. Release to type.\n\n{APP_TAGLINE}",
        )
        config._extra["first_run_done"] = True
        config.save()

    log.info("%s %s started (log: %s)", APP_NAME, __version__, log_path)
    return app.exec()


def _dispatch_commands() -> None:
    """Run queued IPC commands (GUI thread)."""
    app = QApplication.instance()
    if app is None:
        return
    window = getattr(app, "_sotto_window", None)
    if window is None:
        return
    tray = getattr(window, "_tray", None)
    while True:
        try:
            payload = COMMANDS.get_nowait()
        except queue.Empty:
            return
        command = payload.get("command", "")
        if command == "dictate":
            window.service.record("jump")
        elif command == "dictionary":
            window.show()
            window.raise_()
            window.activateWindow()
            window.tabs.setCurrentIndex(1)
        elif command == "settings":
            window.show()
            window.raise_()
            window.activateWindow()
            window.on_settings()
        elif command == "show":
            window.show()
            window.raise_()
            window.activateWindow()
        elif command == "quit":
            app.quit()


def _on_dictation_done(entry: dict) -> None:
    """Called via signal in the GUI thread; persist + refresh the history tab."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    window = getattr(app, "_sotto_window", None)
    if window is None:
        return
    window.add_history_entry(entry)


if __name__ == "__main__":
    sys.exit(main())
