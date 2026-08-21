"""Transport controls: pill buttons, tape counter, status lamp.

Modern take: softly-rounded pills with a 1px press offset, a cyan face when
the control is active (REC armed / recording), and a monospaced counter.
No keycaps — the saber is the instrument now.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from sotto.ui.design_tokens import Color, Component, Motion, Radius, Type


class TransportButton(QWidget):
    clicked = Signal()

    def __init__(self, label: str, primary: bool = False, parent=None):
        super().__init__(parent)
        self._label = label
        self._primary = primary      # cyan face (REC)
        self._active = False
        self._pressed = False
        self._hover = False
        self._press_anim = 0.0
        self._anim = QTimer(self)
        self._anim.setInterval(Motion.PRESS_MS // 2)
        self._anim.timeout.connect(self._tick_anim)
        self.setFixedSize(96, 44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    # -- public -------------------------------------------------------------
    def set_active(self, on: bool) -> None:
        if self._active != on:
            self._active = on
            self.update()

    # -- events -------------------------------------------------------------
    def _tick_anim(self) -> None:
        step = 0.5
        if self._pressed:
            self._press_anim = min(1.0, self._press_anim + step)
            if self._press_anim >= 1.0:
                self._anim.stop()
        else:
            self._press_anim = max(0.0, self._press_anim - step)
            if self._press_anim <= 0.0:
                self._anim.stop()
        self.update()

    def enterEvent(self, _event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, _event) -> None:
        self._hover = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._anim.start()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            was_pressed = self._pressed
            self._pressed = False
            self._anim.start()
            if was_pressed and self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
            event.accept()

    # -- painting -----------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pressed = self._press_anim > 0.5
        dy = 1 if pressed else 0

        rect = QRectF(2.0, 2.0 + dy, w - 4.0, h - 6.0)

        if self._primary and self._active:
            face = QColor(Color.SABER).lighter(112 if self._hover else 100)
            text = Color.TEXT_ON_LIGHT
        elif self._primary:
            face = QColor(Color.SABER_DK)
            text = Component.REC_TEXT
        else:
            face = QColor(Color.PANEL_RAISED).lighter(110 if self._hover else 100)
            text = Color.TEXT

        p.setBrush(face)
        p.setPen(QPen(QColor(Color.SEAM_LIGHT), 1.0))
        p.drawRoundedRect(rect, Radius.MD, Radius.MD)

        if pressed:
            p.setPen(QPen(QColor(0, 0, 0, 120), 1.0))
            p.drawLine(QPointF(rect.left() + 4, rect.bottom()),
                       QPointF(rect.right() - 4, rect.bottom()))

        font = QFont(Type.FONT_UI, Type.LABEL + 1, Type.WEIGHT_BOLD)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,
                              Type.LABEL_TRACKING_PX)
        p.setFont(font)
        p.setPen(QColor(text))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._label)


class CounterLabel(QWidget):
    """Monospaced elapsed-time counter, cyan when recording."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seconds = 0.0
        self._active = False
        self.setFixedWidth(150)
        self.setFixedHeight(40)

    def set_time(self, seconds: float, active: bool) -> None:
        self._seconds = seconds
        self._active = active
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        rect = QRectF(1.0, 1.0, w - 2.0, h - 2.0)
        p.setBrush(QColor(Color.WELL))
        p.setPen(QPen(QColor(Color.SEAM_LIGHT), 1.0))
        p.drawRoundedRect(rect, Radius.MD, Radius.MD)

        total = int(self._seconds)
        mm, ss = total // 60, total % 60
        text = f"{mm:02d}:{ss:02d}"
        font = QFont(Type.FONT_MONO, Type.DISPLAY, Type.WEIGHT_MEDIUM)
        p.setFont(font)
        color = QColor(Color.SABER_LT) if self._active else QColor(Color.TEXT_FAINT)
        p.setPen(color)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


class StatusLamp(QWidget):
    """Small status dot + silk text (READY / REC / BUSY / ERR)."""

    COLORS = {
        "off": Color.TEXT_FAINT,
        "ready": Color.LEVEL_GREEN,
        "rec": Color.SABER,
        "busy": Color.LEVEL_AMBER,
        "err": Color.LEVEL_AMBER,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "off"
        self._text = "READY"
        self._blink = False
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(Motion.BLINK_MS)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self.setFixedHeight(24)

    def set_state(self, state: str, text: str) -> None:
        self._state = state
        self._text = text
        self._blink_timer.stop()
        self._blink = False
        if state == "busy":
            self._blink_timer.start()
        self.update()

    def _toggle_blink(self) -> None:
        self._blink = not self._blink
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self._blink if self._state == "busy" else True
        color = QColor(self.COLORS.get(self._state, Color.TEXT_FAINT))
        if not on:
            color = QColor(Color.TEXT_FAINT)

        p.setBrush(color)
        p.setPen(QPen(QColor(0, 0, 0, 140), 1.0))
        p.drawEllipse(QPointF(9, self.height() / 2), 4.5, 4.5)

        font = QFont(Type.FONT_UI, Type.MICRO, Type.LABEL_WEIGHT)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,
                              Type.LABEL_TRACKING_PX)
        p.setFont(font)
        p.setPen(QColor(Color.TEXT_DIM))
        p.drawText(QRectF(20, 0, self.width() - 20, self.height()),
                   Qt.AlignmentFlag.AlignVCenter, self._text)
