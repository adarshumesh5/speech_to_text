"""The lightsaber — Grogu's recording instrument.

A custom-painted hilt with a cyan blade that ignites when you speak, glows in
time with the microphone level, and retracts on the way out. The blade is
drawn as layered translucent rects (wide soft halo → mid glow → white-hot
core) so it reads as light, not as a colored line.

States: retracted (idle) → igniting → on (recording / working) → retracting.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from grogu.ui.design_tokens import Color, Motion

HILT_W = 96      # hilt footprint (px)
BLADE_MAX = 0.72  # blade reaches 72% of the widget width


class Lightsaber(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(96)
        self.setFixedHeight(110)
        self._length = 0.0        # 0..1 blade extension
        self._target = 0.0        # where the animation is heading
        self._level = 0.0         # mic level 0..1
        self._active = False      # saber lit (recording/working)
        self._t = 0.0             # clock for the idle hum pulse
        self._anim = QTimer(self)
        self._anim.setInterval(16)
        self._anim.timeout.connect(self._tick)
        self._anim.start()

    # -- public -------------------------------------------------------------
    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level))

    def ignite(self) -> None:
        """Start the blade (recording began)."""
        self._active = True
        self._target = 1.0

    def retract(self) -> None:
        """Sheathe the blade (recording/working ended)."""
        self._active = False
        self._target = 0.0

    @property
    def active(self) -> bool:
        return self._active

    # -- internals ----------------------------------------------------------
    def _tick(self) -> None:
        dt = 1.0 / 60.0
        speed = 1.0 / (Motion.SABER_IGNITE_MS / 1000.0) * dt
        if not self._active:
            speed = 1.0 / (Motion.SABER_RETRACT_MS / 1000.0) * dt
        if self._length < self._target:
            self._length = min(self._target, self._length + speed)
        elif self._length > self._target:
            self._length = max(self._target, self._length - speed)
        self._t += dt
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid_y = h / 2.0

        # --- hilt (angled metallic grip) -----------------------------------
        hilt_top = mid_y - 26.0
        hilt_bot = mid_y + 26.0
        hx0 = 12.0
        # slightly tapered trapezoid, emitter ring on the right
        taper = 4.0
        poly = [
            QPointF(hx0, hilt_top),
            QPointF(hx0 + HILT_W - taper, hilt_top + 2.0),
            QPointF(hx0 + HILT_W, mid_y),
            QPointF(hx0 + HILT_W - taper, hilt_bot - 2.0),
            QPointF(hx0, hilt_bot),
        ]
        p.setBrush(QColor(Color.PANEL_RAISED))
        p.setPen(QPen(QColor(Color.SEAM_LIGHT), 1.0))
        p.drawPolygon(poly)

        # grip bands
        p.setPen(QPen(QColor(Color.SEAM_DARK), 1.0))
        for i in range(4):
            bx = hx0 + 14.0 + i * 12.0
            p.drawLine(QPointF(bx, hilt_top + 3.0), QPointF(bx - 2.0, mid_y))
            p.drawLine(QPointF(bx - 2.0, mid_y), QPointF(bx, hilt_bot - 3.0))

        # emitter ring
        ex = hx0 + HILT_W
        ring = QRectF(ex - 5.0, hilt_top + 6.0, 6.0, (hilt_bot - hilt_top) - 12.0)
        p.setBrush(QColor(Color.SEAM_DARK))
        p.setPen(QPen(QColor(Color.SABER_DK), 1.0))
        p.drawRect(ring)

        # emitter slit glow (brightens as the blade grows)
        emitter_glow = int(60 + 160 * self._length)
        slit = QRectF(ex - 2.0, mid_y - 10.0, 3.0, 20.0)
        p.setBrush(QColor(*QColor(Color.SABER).getRgb()[:3], emitter_glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(slit)

        # --- blade ---------------------------------------------------------
        blade_len = (w - hx0 - HILT_W - 8.0) * BLADE_MAX * self._length
        if blade_len > 2.0:
            self._paint_blade(p, ex + 2.0, mid_y, blade_len)

    def _paint_blade(self, p: QPainter, x0: float, mid_y: float, length: float) -> None:
        """Draw the blade as three layered translucent rects."""
        # pulse: gentle hum at idle-level, stronger with mic level
        hum = 0.5 + 0.5 * math.sin(self._t * 3.2)
        pulse = 0.75 + 0.25 * hum
        if self._active:
            pulse = min(1.0, pulse + self._level * 0.6)

        core_w = 5.0
        mid_w = core_w * 2.6
        halo_w = core_w * 5.2

        end = x0 + length
        # blade tip: rounded (saber tips are rounded)
        tip_r = core_w / 2.0

        # halo (outer glow)
        hg = QLinearGradient(x0, 0, end, 0)
        hg.setColorAt(0, QColor(Color.SABER))
        hg.setColorAt(1, QColor(Color.SABER))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(hg)
        halo_alpha = int(42 * pulse)
        halo = QRectF(x0, mid_y - halo_w / 2.0, length, halo_w)
        p.fillRect(halo, QColor(*QColor(Color.SABER).getRgb()[:3], halo_alpha))

        # mid glow
        mid_alpha = int(130 * pulse)
        p.fillRect(QRectF(x0, mid_y - mid_w / 2.0, length, mid_w),
                   QColor(*QColor(Color.SABER).getRgb()[:3], mid_alpha))

        # white-hot core (thin)
        core_alpha = int(210 + 45 * pulse)
        p.fillRect(QRectF(x0, mid_y - core_w / 2.0, length, core_w),
                   QColor(*QColor(Color.SABER_LT).getRgb()[:3], core_alpha))

        # rounded tip on the core
        p.setBrush(QColor(*QColor(Color.SABER_LT).getRgb()[:3], core_alpha))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(end, mid_y), tip_r * 1.6, tip_r * 1.6)
