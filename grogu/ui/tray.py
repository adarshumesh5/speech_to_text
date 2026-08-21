"""System tray integration — secondary surface: status, hotkey, quick actions.

Icon swaps instantly when recording (red lamp lit) or muted (amber), so a
failing hotkey is visible even when the window is hidden. Also hosts the
recent-transcription quick-insert menu and the undo-last-correction action.
"""

from __future__ import annotations

import os
import threading

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from grogu import APP_NAME
from grogu.dictation import STATE_LISTENING, STATE_PAUSED
from grogu.injector import send_text
from grogu.ui.theme import QSS

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def asset_path(name: str) -> str:
    return os.path.join(ASSETS_DIR, name)


def _build_icon(base: str) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64):
        path = asset_path(f"icon-{size}.png")
        if os.path.exists(path):
            icon.addFile(path, QSize(size, size))
    if icon.isNull():
        icon = QIcon(asset_path(base))
    return icon


class Tray:
    def __init__(self, app, service, history, window, on_settings, on_undo):
        self.app = app
        self.service = service
        self.history = history
        self.window = window
        self._settings_cb = on_settings
        self._undo_cb = on_undo

        self._icon_idle = _build_icon("tray.png")
        self._icon_rec = _build_icon("tray-rec.png")
        self._icon_muted = _build_icon("tray-muted.png")
        self._current = "idle"

        self.menu = QMenu()
        self.menu.setStyleSheet(QSS)
        act_dictate = self.menu.addAction("Dictate")
        act_dictate.triggered.connect(self._toggle_dictate)
        self.menu.addSeparator()
        self.recent_menu = self.menu.addMenu("Recent…")
        act_undo = self.menu.addAction("Undo Last Correction")
        act_undo.triggered.connect(self._undo_cb)
        act_undo.setEnabled(False)
        self._act_undo = act_undo
        self.menu.addSeparator()
        act_settings = self.menu.addAction("Settings…")
        act_settings.triggered.connect(self._settings_cb)
        self.menu.addSeparator()
        act_quit = self.menu.addAction(f"Quit {APP_NAME}")
        act_quit.triggered.connect(app.quit)

        self.tray = QSystemTrayIcon(self._icon_idle, app)
        self.tray.setToolTip(f"{APP_NAME} — push-to-talk dictation")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)

        service.state_changed.connect(self._on_state)
        service.muted_changed.connect(self._on_muted)
        service.dictation_done.connect(self._on_dictation_done)
        service.error.connect(self._on_error)
        service.toast.connect(self.notify)

    # -- lifecycle ----------------------------------------------------------
    def show(self) -> None:
        self.tray.show()
        self._refresh_recent()

    def hide(self) -> None:
        self.tray.hide()

    def notify(self, title: str, message: str) -> None:
        self.tray.showMessage(title, message, self._current_icon(), 5000)

    # -- state-driven icons -------------------------------------------------
    def _current_icon(self) -> QIcon:
        return {"idle": self._icon_idle, "rec": self._icon_rec,
                "muted": self._icon_muted}.get(self._current, self._icon_idle)

    def _set_state_icon(self, state: str) -> None:
        if self._current == state:
            return
        self._current = state
        self.tray.setIcon(self._current_icon())

    def _on_state(self, state: str) -> None:
        if state in (STATE_LISTENING, STATE_PAUSED):
            self._set_state_icon("rec")
        elif self.service.muted:
            self._set_state_icon("muted")
        else:
            self._set_state_icon("idle")

    def _on_muted(self, muted: bool) -> None:
        self._set_state_icon("muted" if muted else "idle")
        self.tray.setToolTip(
            f"{APP_NAME} — muted (PTT disabled)" if muted
            else f"{APP_NAME} — push-to-talk dictation"
        )

    # -- actions ------------------------------------------------------------
    def _toggle_dictate(self) -> None:
        try:
            self.service.toggle()
        except Exception:
            pass

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_dictate()

    def _on_error(self, message: str) -> None:
        self.notify(APP_NAME, f"⚠ {message}")
        self._set_state_icon("muted")  # amber-ish: something needs attention

    def _on_dictation_done(self, entry: dict) -> None:
        self._refresh_recent()
        self._act_undo.setEnabled(bool(entry.get("corrections")))
        text = entry.get("text", "")
        corrections = entry.get("corrections", [])

        # Voice commands: confirm what ran instead of showing a text snippet.
        if entry.get("kind") == "command":
            if self.service.config.notify_on_dictation:
                self.notify(f"{APP_NAME} — command", f"✓ {text}")
            return

        # Build a clear notification message
        if self.service.config.insertion_mode == "clipboard":
            # Clipboard mode: text is on clipboard, tell user to paste
            snippet = text if len(text) <= 80 else text[:77] + "…"
            msg = f"📋 {snippet}\n\nCtrl+V to paste"
            if corrections:
                msg += f" ({len(corrections)} correction{'s' if len(corrections) > 1 else ''} applied)"
        else:
            # Keystrokes mode: text was typed
            snippet = text if len(text) <= 90 else text[:87] + "…"
            msg = snippet
            if corrections:
                msg += f"\n\n({len(corrections)} correction{'s' if len(corrections) > 1 else ''} applied)"

        # Show notification (when window is hidden or always)
        if self.service.config.notify_on_dictation:
            self.notify(f"{APP_NAME} — dictated", msg)

    # -- recent transcriptions ----------------------------------------------
    def _refresh_recent(self) -> None:
        self.recent_menu.clear()
        entries = self.history.load(newest_first=True)[:5]
        if not entries:
            item = self.recent_menu.addAction("(no transcriptions yet)")
            item.setEnabled(False)
            return
        for entry in entries:
            text = entry.get("text", "")
            snippet = text if len(text) <= 42 else text[:39] + "…"
            action = self.recent_menu.addAction(snippet)
            action.setToolTip(f"Insert into focused app ({entry.get('source', '')})")
            action.triggered.connect(
                lambda _=False, t=text: self._insert_text(t)
            )

    def _insert_text(self, text: str) -> None:
        def work() -> None:
            try:
                send_text(text)
            except Exception:
                pass
        threading.Thread(target=work, name="grogu-insert", daemon=True).start()
