"""First-run onboarding wizard — 3 steps, shown once.

1. **Hotkey** — see/change the push-to-talk hotkey and test it.
2. **Microphone** — pick an input device and watch the live level meter.
3. **Sample dictation** — record a short clip, see it transcribed.

Each step saves its result into the shared ``Config`` as the user clicks
Next, so a closed wizard never loses the settings that were already made.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from grogu import APP_NAME
from grogu.audio import MicRecorder, list_input_devices
from grogu.hotkey import parse_hotkey, test_register
from grogu.ui.design_tokens import Color, Space, Type
from grogu.ui.main_window import apply_dark_title_bar
from grogu.ui.model_manager import _silk
from grogu.ui.vu_meter import LevelMeter


def _body_font() -> QFont:
    return QFont(Type.FONT_UI, Type.BODY, Type.WEIGHT_REGULAR)


def _hint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet(f"color: {Color.TEXT_FAINT}; background: transparent;")
    lab.setFont(QFont(Type.FONT_UI, Type.MICRO, Type.WEIGHT_REGULAR))
    return lab


class _StepPage(QWidget):
    """Base page: title + silk subtitle + content + optional result label."""

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.XL, Space.XL, Space.XL, Space.XL)
        layout.setSpacing(Space.MD)
        t = QLabel(title)
        t.setStyleSheet(
            f"font-size: 17px; font-weight: 600; color: {Color.TEXT};"
        )
        layout.addWidget(t)
        layout.addWidget(_silk(subtitle))
        self.body = QVBoxLayout()
        self.body.setSpacing(Space.MD)
        layout.addLayout(self.body)
        layout.addStretch(1)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        self.result.setStyleSheet(
            f"color: {Color.LEVEL_AMBER}; background: transparent;"
        )
        layout.addWidget(self.result)

    def set_result(self, text: str, color: str = Color.LEVEL_AMBER) -> None:
        self.result.setText(text)
        self.result.setStyleSheet(
            f"color: {color}; background: transparent;"
        )


class OnboardingWizard(QDialog):
    """3-step wizard. ``finished_ok`` is True when the user completed it."""

    def __init__(self, config, service, parent=None):
        super().__init__(parent)
        self.config = config
        self.service = service
        self.finished_ok = False
        self._recorder: MicRecorder | None = None
        self._level_timer: QTimer | None = None
        self._page = 0
        self._pages: list[_StepPage] = []

        self.setObjectName("OnboardingWizard")
        self.setWindowTitle(f"Welcome to {APP_NAME}")
        self.setMinimumWidth(540)
        self.setMinimumHeight(430)
        self._build()
        apply_dark_title_bar(self)

    # -- ui -----------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QWidget()
        self.stack_layout = QVBoxLayout(self.stack)
        self.stack_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack, stretch=1)

        bar = QHBoxLayout()
        bar.setContentsMargins(Space.XL, Space.MD, Space.XL, Space.MD)
        bar.setSpacing(Space.MD)
        bar.addStretch(1)
        self.back_btn = QPushButton("Back")
        self.back_btn.setObjectName("Keycap")
        self.back_btn.clicked.connect(self._go_back)
        bar.addWidget(self.back_btn)
        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("Primary")
        self.next_btn.clicked.connect(self._go_next)
        bar.addWidget(self.next_btn)
        layout.addLayout(bar)

        self._build_hotkey_page()
        self._build_mic_page()
        self._build_sample_page()
        self._show_page(0)

    def _build_hotkey_page(self) -> None:
        page = _StepPage(
            "Your push-to-talk hotkey",
            "HOLD THIS KEY TO DICTATE · RELEASE TO TYPE",
        )
        self.hotkey_edit = QKeySequenceEdit()
        try:
            self.hotkey_edit.setKeySequence(self.config.hotkey)
        except Exception:  # noqa: BLE001
            pass
        page.body.addWidget(self.hotkey_edit)

        test_row = QHBoxLayout()
        btn_test = QPushButton("Test hotkey")
        btn_test.setObjectName("Keycap")
        btn_test.clicked.connect(self._test_hotkey)
        test_row.addWidget(btn_test)
        test_row.addStretch(1)
        page.body.addLayout(test_row)
        page.body.addWidget(_hint(
            "Works in every app — even when Grogu's window is hidden. "
            "You can change it any time in Settings (Ctrl+,)."
        ))
        self._pages.append(page)

    def _build_mic_page(self) -> None:
        page = _StepPage(
            "Your microphone",
            "SPEAK — THE LEVEL METER SHOULD MOVE",
        )
        self.mic_combo = QComboBox()
        self.mic_combo.addItem("(Default microphone)", None)
        for name in list_input_devices():
            self.mic_combo.addItem(name, name)
        idx = self.mic_combo.findData(self.config.mic_device)
        if idx >= 0:
            self.mic_combo.setCurrentIndex(idx)
        page.body.addWidget(self.mic_combo)

        self.meter = LevelMeter()
        self.meter.setMinimumWidth(300)
        page.body.addWidget(self.meter)

        self.listen_btn = QPushButton("Start listening")
        self.listen_btn.setObjectName("Primary")
        self.listen_btn.clicked.connect(self._toggle_mic_test)
        page.body.addWidget(self.listen_btn)
        page.body.addWidget(_hint(
            "Click Start listening, then speak. The bar should jump toward "
            "the amber zone. Click Stop when you're happy."
        ))
        self._pages.append(page)

    def _build_sample_page(self) -> None:
        page = _StepPage(
            "Try it out",
            "HOLD TO RECORD · RELEASE TO TRANSCRIBE",
        )
        self.sample_btn = QPushButton("Hold to speak")
        self.sample_btn.setObjectName("Primary")
        self.sample_btn.pressed.connect(self._start_sample)
        self.sample_btn.released.connect(self._stop_sample)
        page.body.addWidget(self.sample_btn)
        self.sample_out = QLabel("")
        self.sample_out.setWordWrap(True)
        self.sample_out.setStyleSheet(
            f"color: {Color.TEXT}; background: transparent;"
        )
        self.sample_out.setFont(_body_font())
        page.body.addWidget(self.sample_out)
        page.body.addWidget(_hint(
            "Hold the button, say something like “the force is strong with "
            "this one”, then release. Grogu will transcribe it on your GPU."
        ))
        self._pages.append(page)

    # -- navigation ---------------------------------------------------------
    def _show_page(self, index: int) -> None:
        self._page = index
        # swap the visible page
        for i, w in enumerate(self._pages):
            w.setParent(None)
        self.stack_layout.addWidget(self._pages[index])
        self._pages[index].show()
        self.back_btn.setEnabled(index > 0)
        if index == len(self._pages) - 1:
            self.next_btn.setText("Finish")
        else:
            self.next_btn.setText("Next")
        # stop any live mic test when leaving
        if index != 1:
            self._stop_mic_test()

    def _go_back(self) -> None:
        if self._page > 0:
            self._show_page(self._page - 1)

    def _go_next(self) -> None:
        if self._page == 0:
            if not self._save_hotkey():
                return
        elif self._page == 1:
            self._save_mic()
        else:
            self._stop_sample()
            self.finished_ok = True
            self.accept()
            return
        if self._page < len(self._pages) - 1:
            self._show_page(self._page + 1)

    # -- step 1: hotkey -----------------------------------------------------
    def _test_hotkey(self) -> None:
        spec = self.hotkey_edit.keySequence().toString()
        try:
            parse_hotkey(spec)
        except ValueError as e:
            self._pages[0].set_result(f"INVALID — {e}")
            return
        ok, message = test_register(spec)
        if ok:
            self._pages[0].set_result(f"✓ {message}", Color.LEVEL_GREEN)
        else:
            self._pages[0].set_result(f"✗ {message}")

    def _save_hotkey(self) -> bool:
        spec = self.hotkey_edit.keySequence().toString()
        try:
            parse_hotkey(spec)
        except ValueError as e:
            self._pages[0].set_result(f"INVALID — {e}")
            return False
        # If the user kept the current hotkey, the service already registered
        # it at startup — no need to probe (it would report "in use" by us).
        if spec != self.config.hotkey:
            ok, message = test_register(spec)
            if not ok:
                ret = QMessageBox.question(
                    self, APP_NAME, f"Hotkey {spec} {message}.\nApply anyway?"
                )
                if ret != QMessageBox.StandardButton.Yes:
                    return False
        self.config.hotkey = spec
        self.config.save()
        return True

    # -- step 2: mic --------------------------------------------------------
    def _toggle_mic_test(self) -> None:
        if self._recorder is not None:
            self._stop_mic_test()
            return
        self._stop_mic_test()
        try:
            self._recorder = MicRecorder(self.mic_combo.currentData())
            self._recorder.start()
        except Exception as e:  # noqa: BLE001
            self._pages[1].set_result(f"Could not open the mic: {e}")
            return
        self.meter.idle()
        self.listen_btn.setText("Stop listening")
        self._level_timer = QTimer(self)
        self._level_timer.setInterval(60)
        self._level_timer.timeout.connect(self._poll_level)
        self._level_timer.start()

    def _poll_level(self) -> None:
        if self._recorder is not None:
            self.meter.set_level(self._recorder.level())

    def _stop_mic_test(self) -> None:
        if self._level_timer is not None:
            self._level_timer.stop()
            self._level_timer = None
        rec = self._recorder
        self._recorder = None
        if rec is not None:
            try:
                rec.cancel()
            except Exception:  # noqa: BLE001
                pass
        self.listen_btn.setText("Start listening")
        self.meter.idle()

    def _save_mic(self) -> None:
        self._stop_mic_test()
        self.config.mic_device = self.mic_combo.currentData()
        self.config.save()

    # -- step 3: sample dictation -------------------------------------------
    def _start_sample(self) -> None:
        self._stop_mic_test()
        self.sample_out.setText("Recording… speak now.")
        try:
            self._recorder = MicRecorder(self.config.mic_device)
            self._recorder.start()
        except Exception as e:  # noqa: BLE001
            self.sample_out.setText(f"Mic error: {e}")

    def _stop_sample(self) -> None:
        rec = self._recorder
        self._recorder = None
        if rec is None:
            return
        try:
            audio = rec.stop()
        except Exception as e:  # noqa: BLE001
            self.sample_out.setText(f"Mic error: {e}")
            return
        self.sample_out.setText("Transcribing…")
        threading.Thread(
            target=self._transcribe_sample,
            args=(audio,),
            name="grogu-onboarding-sample",
            daemon=True,
        ).start()

    def _transcribe_sample(self, audio) -> None:
        try:
            engine = self.service._ensure_engine()
            text = engine.transcribe(
                audio,
                language=self.config.language,
                vad=self.config.vad_filter,
            )
            cleaned = text.strip()
            if not cleaned:
                cleaned = "(no speech detected — try again?)"
        except Exception as e:  # noqa: BLE001
            cleaned = f"(transcription failed: {e})"
        self.sample_out.setText(cleaned)

    def closeEvent(self, event) -> None:
        self._stop_mic_test()
        self._stop_sample()
        super().closeEvent(event)
