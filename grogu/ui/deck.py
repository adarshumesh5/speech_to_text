"""The deck — Grogu's top panel.

The lightsaber is the recording instrument: it ignites and glows while you
speak. Below it sit the transport (REC / STOP pills), the level meter, the
elapsed counter, the status line, and the hotkey silkscreen. The tabs below
are the content.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from grogu.dictation import (
    STATE_CLEANING,
    STATE_IDLE,
    STATE_LISTENING,
    STATE_PAUSED,
    STATE_PREPARING,
    STATE_TRANSCRIBING,
    STATE_TYPING,
)
from grogu.ui.design_tokens import Color, Space, Type
from grogu.ui.lightsaber import Lightsaber
from grogu.ui.transport import CounterLabel, StatusLamp, TransportButton
from grogu.ui.vu_meter import LevelMeter

LAMP_TEXT = {
    STATE_IDLE: "MAY THE FORCE BE WITH YOU",
    STATE_PREPARING: "CALIBRATING…",
    STATE_LISTENING: "THE FORCE IS WITH YOU",
    STATE_PAUSED: "PAUSED — PRESS REC TO RESUME",
    STATE_TRANSCRIBING: "DECIPHERING…",
    STATE_CLEANING: "POLISHING…",
    STATE_TYPING: "TRANSMITTING…",
}

LAMP_COLOR = {
    STATE_IDLE: "ready",
    STATE_PREPARING: "busy",
    STATE_LISTENING: "rec",
    STATE_PAUSED: "busy",
    STATE_TRANSCRIBING: "busy",
    STATE_CLEANING: "busy",
    STATE_TYPING: "rec",
}


class _SilkLabel(QLabel):
    """Uppercase tracked label in the silkscreen face."""

    def __init__(self, text: str, parent=None, color: str = Color.TEXT_DIM):
        super().__init__(text.upper(), parent)
        font = QFont(Type.FONT_UI, Type.MICRO, Type.LABEL_WEIGHT)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,
                              Type.LABEL_TRACKING_PX)
        self.setFont(font)
        self._color = color
        self._apply()

    def set_color(self, color: str) -> None:
        self._color = color
        self._apply()

    def _apply(self) -> None:
        self.setStyleSheet(f"color: {self._color}; background: transparent;")


class _StatusSilk(_SilkLabel):
    """Silk label that turns amber for anything worth noticing."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._warn = False
        self.setWordWrap(True)

    def set_status(self, text: str, warn: bool = False) -> None:
        self.setText(text.upper() if text else "")
        self.set_color(Color.LEVEL_AMBER if warn else Color.TEXT_DIM)
        self.setVisible(bool(text))


class DeckPanel(QFrame):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self._listen_started = 0.0
        self._last_duration = 0.0
        self.setObjectName("DeckPanel")
        self.setStyleSheet(
            f"#DeckPanel {{ background: {Color.PANEL}; "
            f"border: 1px solid {Color.SEAM_DARK}; "
            f"border-top: 1px solid {Color.SEAM_LIGHT}; }}"
        )
        self._build()

        # --- wiring ---
        self.rec_button.clicked.connect(service.record)
        self.pause_button.clicked.connect(service.toggle_pause)
        self.stop_button.clicked.connect(service.stop)
        service.state_changed.connect(self._on_state)
        service.mic_level.connect(self._on_level)
        service.muted_changed.connect(self._on_muted)
        service.error.connect(self._on_service_error)

        self._poll = QTimer(self)
        self._poll.setInterval(33)
        self._poll.timeout.connect(self._poll_sensors)
        self._poll.start()

        self._on_state(service.state)

    # -- construction -------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(Space.XL, Space.XL, Space.XL, Space.LG)
        outer.setSpacing(Space.MD)

        # hero: the saber
        self.saber = Lightsaber()
        outer.addWidget(self.saber)

        # controls row
        row = QHBoxLayout()
        row.setSpacing(Space.LG)

        self.rec_button = TransportButton("REC", primary=True)
        self.pause_button = TransportButton("PAUSE", width=72)
        self.stop_button = TransportButton("STOP")
        row.addWidget(self.rec_button)
        row.addWidget(self.pause_button)
        row.addWidget(self.stop_button)

        self.level = LevelMeter()
        row.addWidget(self.level, stretch=1)

        self.counter = CounterLabel()
        row.addWidget(self.counter)

        right = QVBoxLayout()
        right.setSpacing(Space.XS)
        self.status_lamp = StatusLamp()
        right.addWidget(self.status_lamp)
        self.hotkey_label = _SilkLabel("PTT", color=Color.TEXT_FAINT)
        right.addWidget(self.hotkey_label)
        self.status_text = _StatusSilk()
        right.addWidget(self.status_text)
        row.addLayout(right)

        outer.addLayout(row)

    # -- slots --------------------------------------------------------------
    def set_hotkey(self, spec: str) -> None:
        self.hotkey_label.setText(f"PTT  {spec.upper()}")

    def _on_level(self, level: float) -> None:
        self.saber.set_level(level)
        self.level.set_level(level)

    def _on_state(self, state: str) -> None:
        if self.service.muted and state == STATE_IDLE:
            self.status_lamp.set_state("ready", "MUTED")
            self.status_text.set_status("SABER SHEATHED — PTT DISABLED", warn=True)
        else:
            lamp = LAMP_COLOR.get(state, "off")
            text = LAMP_TEXT.get(state, state.upper())
            self.status_lamp.set_state(lamp, text)
            err = self.service.last_error
            if state == STATE_IDLE and err:
                self.status_text.set_status(f"⚠ {err}", warn=True)
            elif state == STATE_IDLE:
                self.status_text.set_status("")
        self.rec_button.set_active(state in (STATE_LISTENING, STATE_PAUSED))
        self.pause_button.set_active(state == STATE_PAUSED)
        if state == STATE_LISTENING:
            self._listen_started = time.time()
            self.saber.ignite()
        elif state == STATE_PAUSED:
            # keep the saber lit but freeze the meters
            self.level.idle()
        elif state == STATE_IDLE:
            self.saber.retract()
            self.level.idle()
        if state in (STATE_TRANSCRIBING, STATE_CLEANING, STATE_TYPING):
            self._last_duration = time.time() - self._listen_started
            self.counter.set_time(self._last_duration, False)

    def _on_muted(self, muted: bool) -> None:
        if muted:
            self.status_lamp.set_state("ready", "MUTED")
            self.status_text.set_status("SABER SHEATHED — PTT DISABLED", warn=True)
            self.saber.retract()
        elif self.service.state == STATE_IDLE:
            err = self.service.last_error
            self.status_lamp.set_state("ready", "READY")
            self.status_text.set_status(f"⚠ {err}" if err else "", warn=bool(err))

    def _on_service_error(self, message: str) -> None:
        self.status_lamp.set_state("busy", "ERR")
        self.status_text.set_status(f"⚠ {message}", warn=True)
        self.saber.retract()

    def _poll_sensors(self) -> None:
        if self.service.state == STATE_LISTENING:
            elapsed = time.time() - self._listen_started
            self.counter.set_time(elapsed, True)
        elif self.service.state == STATE_IDLE:
            self.counter.set_time(self._last_duration, False)
