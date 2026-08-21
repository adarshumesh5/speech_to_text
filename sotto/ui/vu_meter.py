"""LevelMeter — the recording level indicator.

A modern horizontal bar in a recessed well: green through amber, with a slow
attack/decay, a bright peak-hold marker, and a silk label. The saber carries
the drama; this is the plain instrumentation. Level input is 0..1 (from the
mic); it is mapped logarithmically to a -20..+3 dB scale like a VU.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from sotto.ui.design_tokens import Color, Motion, Radius, Type

DB_MIN, DB_MAX = -20.0, 3.0
DB_GREEN_SPLIT = -3.0


def _db_from_level(level: float) -> float:
    if level <= 1e-4:
        return DB_MIN
    return max(DB_MIN, min(DB_MAX, 20.0 * math.log10(level)))


class LevelMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 40)
        self.setFixedHeight(40)
        self._target = 0.0
        self._level = 0.0
        self._peak = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # -- public -------------------------------------------------------------
    def set_level(self, level: float) -> None:
        self._target = max(0.0, min(1.0, level))

    def idle(self) -> None:
        self._target = 0.0

    # -- internals ----------------------------------------------------------
    def _tick(self) -> None:
        dt = 0.033
        if self._target > self._level:
            k = 1.0 - math.exp(-dt / Motion.VU_ATTACK_S)
        else:
            k = 1.0 - math.exp(-dt / Motion.VU_DECAY_S)
        self._level += (self._target - self._level) * k
        if self._level > self._peak:
            self._peak = self._level
        else:
            self._peak = max(self._level, self._peak - dt * 0.4)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # well
        rect = QRectF(1.0, 1.0, w - 2.0, h - 2.0)
        p.setBrush(QColor(Color.WELL))
        p.setPen(QPen(QColor(Color.SEAM_LIGHT), 1.0))
        p.drawRoundedRect(rect, Radius.MD, Radius.MD)

        # fill
        db = _db_from_level(self._level)
        frac = (db - DB_MIN) / (DB_MAX - DB_MIN)
        fill_w = (w - 16.0) * max(0.0, min(1.0, frac))
        if fill_w > 1.0:
            grad = QLinearGradient(0, 0, w, 0)
            grad.setColorAt(0.0, QColor(Color.LEVEL_GREEN))
            grad.setColorAt(0.75, QColor(Color.LEVEL_GREEN))
            grad.setColorAt(1.0, QColor(Color.LEVEL_AMBER))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawRoundedRect(QRectF(8.0, 8.0, fill_w, h - 16.0),
                              Radius.SM, Radius.SM)

        # peak hold marker
        peak_frac = (max(self._peak, self._level) - DB_MIN) / (DB_MAX - DB_MIN)
        px = 8.0 + (w - 16.0) * max(0.0, min(1.0, peak_frac))
        if px > 8.0:
            p.setBrush(QColor(Color.SABER_LT))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(px - 1.0, 6.0, 2.0, h - 12.0))

        # silk label
        font = QFont(Type.FONT_UI, Type.MICRO, Type.LABEL_WEIGHT)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        p.setFont(font)
        p.setPen(QColor(Color.TEXT_FAINT))
        p.drawText(QRectF(8, 0, 40, 12), Qt.AlignmentFlag.AlignLeft, "LEVEL")
