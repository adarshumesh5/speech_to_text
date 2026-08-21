"""Settings window — edits the shared Config and applies it live."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from grogu import APP_NAME
from grogu.audio import list_input_devices
from grogu.config import (
    CLEANERS,
    INSERTION_MODES,
    LANGUAGES,
    MODELS,
    Config,
)
from grogu.hotkey import hotkey_error_text, parse_hotkey, test_register
from grogu.startup import is_enabled, set_enabled
from grogu.ui.design_tokens import Color, Space, Type
from grogu.ui.main_window import apply_dark_title_bar
from grogu.ui.theme import QSS

MODE_LABELS = {
    "hold": "Hold to talk (press & hold while speaking)",
    "toggle": "Toggle (press once to start, again to stop)",
}

MUTE_HOTKEY_HINT = (
    "Optional global kill-switch: cancels any dictation in flight and "
    "disables the push-to-talk key. Press again to re-enable."
)


def _silk_label(text: str, color: str = Color.TEXT_DIM) -> QLabel:
    label = QLabel(text.upper())
    font = label.font()
    font.setPointSize(Type.MICRO)
    font.setWeight(QFont.Weight(Type.LABEL_WEIGHT))
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
    label.setFont(font)
    label.setStyleSheet(f"color: {color};")
    return label


class SettingsWindow(QDialog):
    def __init__(self, config: Config, service, parent=None):
        super().__init__(parent)
        self.config = config
        self.service = service
        self.setObjectName("SettingsWindow")
        self.setWindowTitle(f"{APP_NAME} — Settings")
        self.setMinimumWidth(520)
        self.setStyleSheet(QSS)
        self._build()
        apply_dark_title_bar(self)

    # -- ui -----------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.LG, Space.LG, Space.LG, Space.LG)
        layout.setSpacing(Space.MD)

        title = QLabel(APP_NAME)
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {Color.TEXT};"
        )
        tagline = _silk_label("CONTROLS · ENGINE · AUDIO · SYSTEM",
                              color=Color.SABER)
        layout.addWidget(title)
        layout.addWidget(tagline)

        # --- hotkeys + behaviour ---
        group = QGroupBox("Dictation")
        form = QFormLayout(group)
        form.setSpacing(Space.SM)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # primary hotkey row: editor + Test button
        hotkey_row = QHBoxLayout()
        hotkey_row.setSpacing(Space.SM)
        self.hotkey_edit = QKeySequenceEdit()
        try:
            self.hotkey_edit.setKeySequence(self.config.hotkey)
        except Exception:  # noqa: BLE001
            pass
        hotkey_row.addWidget(self.hotkey_edit, stretch=1)
        btn_test = QPushButton("Test Hotkey")
        btn_test.setObjectName("Keycap")
        btn_test.clicked.connect(self._test_hotkey)
        hotkey_row.addWidget(btn_test)
        form.addRow("PTT hotkey", hotkey_row)
        self.hotkey_result = _silk_label("", color=Color.LEVEL_AMBER)
        self.hotkey_result.setWordWrap(True)
        form.addRow("", self.hotkey_result)

        # optional mute hotkey
        self.mute_hotkey_edit = QKeySequenceEdit()
        if self.config.mute_hotkey:
            try:
                self.mute_hotkey_edit.setKeySequence(self.config.mute_hotkey)
            except Exception:  # noqa: BLE001
                pass
        self.mute_hotkey_edit.setMaximumSequenceLength(1)
        form.addRow("Mute hotkey", self.mute_hotkey_edit)
        hint = QLabel(MUTE_HOTKEY_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Color.TEXT_FAINT}; font-size: 10px;")
        form.addRow("", hint)

        self.insert_mode_combo = QComboBox()
        for key, label in INSERTION_MODES.items():
            self.insert_mode_combo.addItem(label, key)
        idx = self.insert_mode_combo.findData(self.config.insertion_mode)
        self.insert_mode_combo.setCurrentIndex(max(0, idx))
        form.addRow("Insert text", self.insert_mode_combo)

        self.mode_combo = QComboBox()
        for key, label in MODE_LABELS.items():
            self.mode_combo.addItem(label, key)
        idx = self.mode_combo.findData(self.config.mode)
        self.mode_combo.setCurrentIndex(max(0, idx))
        form.addRow("Mode", self.mode_combo)

        self.mic_combo = QComboBox()
        self.mic_combo.addItem("(Default microphone)", None)
        devices = list_input_devices()
        for name in devices:
            self.mic_combo.addItem(name, name)
        idx = self.mic_combo.findData(self.config.mic_device)
        if idx >= 0:
            self.mic_combo.setCurrentIndex(idx)
        form.addRow("Microphone", self.mic_combo)

        self.vad_check = QCheckBox("Stop transcribing on silence (VAD)")
        self.vad_check.setChecked(self.config.vad_filter)
        form.addRow("", self.vad_check)

        self.cues_check = QCheckBox(
            "Lightsaber sound on record start / stop")
        self.cues_check.setChecked(self.config.sound_cues)
        form.addRow("", self.cues_check)

        self.learn_check = QCheckBox(
            "Learn from corrections — auto-add every fired correction to "
            "the dictionary so Grogu keeps catching it"
        )
        self.learn_check.setChecked(self.config.learn_from_corrections)
        form.addRow("", self.learn_check)
        layout.addWidget(group)

        # --- engine ---
        group = QGroupBox("Speech engine")
        form = QFormLayout(group)
        form.setSpacing(Space.SM)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.model_combo = QComboBox()
        for m in MODELS:
            self.model_combo.addItem(m, m)
        idx = self.model_combo.findData(self.config.model)
        self.model_combo.setCurrentIndex(max(0, idx))
        form.addRow("Model", self.model_combo)

        self.lang_combo = QComboBox()
        for code, label in LANGUAGES.items():
            self.lang_combo.addItem(label, code)
        idx = self.lang_combo.findData(self.config.language)
        self.lang_combo.setCurrentIndex(max(0, idx))
        form.addRow("Language", self.lang_combo)

        self.cleaner_combo = QComboBox()
        for key, label in CLEANERS.items():
            self.cleaner_combo.addItem(label, key)
        idx = self.cleaner_combo.findData(self.config.cleaner)
        self.cleaner_combo.setCurrentIndex(max(0, idx))
        form.addRow("Cleanup", self.cleaner_combo)

        note = QLabel(
            "The model downloads on first use (cached locally). "
            "CUDA (GPU) is used automatically when available."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {Color.TEXT_FAINT}; font-size: 11px;")
        form.addRow("", note)

        manage_row = QHBoxLayout()
        btn_models = QPushButton("Manage Models…")
        btn_models.setObjectName("Keycap")
        btn_models.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_models.setToolTip("Pre-download models, see sizes, delete cached models")
        btn_models.clicked.connect(self._open_model_manager)
        manage_row.addWidget(btn_models)
        manage_row.addStretch(1)
        form.addRow("", manage_row)
        layout.addWidget(group)

        # --- system ---
        group = QGroupBox("System")
        form = QFormLayout(group)
        form.setSpacing(Space.SM)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.startup_check = QCheckBox(
            "Start with Windows (opens minimized to the tray)")
        self.startup_check.setChecked(self.config.start_with_windows)
        form.addRow("", self.startup_check)

        self.notify_check = QCheckBox(
            "Show a notification when a dictation lands "
            "(while the window is hidden)")
        self.notify_check.setChecked(self.config.notify_on_dictation)
        form.addRow("", self.notify_check)
        layout.addWidget(group)

        # --- actions ---
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save & Apply")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    # -- actions ------------------------------------------------------------
    def _open_model_manager(self) -> None:
        from grogu.ui.model_manager import ModelManagerDialog

        dlg = ModelManagerDialog(self)
        dlg.exec()

    def _test_hotkey(self) -> None:
        """Probe the OS right now and report the specific outcome."""
        spec = self.hotkey_edit.keySequence().toString()
        try:
            parse_hotkey(spec)
        except ValueError as e:
            self.hotkey_result.setText(f"INVALID — {e}")
            self.hotkey_result.setVisible(True)
            return
        ok, message = test_register(spec)
        if ok:
            self.hotkey_result.setText(f"✓ {message}")
            self.hotkey_result.set_color(Color.LEVEL_GREEN)
        else:
            self.hotkey_result.setText(f"✗ {message}")
            self.hotkey_result.set_color(Color.LEVEL_AMBER)
        self.hotkey_result.setVisible(True)

    def _save(self) -> None:
        spec = self.hotkey_edit.keySequence().toString()
        if spec:
            try:
                parse_hotkey(spec)
            except ValueError as e:
                QMessageBox.warning(self, APP_NAME, f"Invalid hotkey: {e}")
                return
        else:
            QMessageBox.warning(self, APP_NAME,
                                "Pick a push-to-talk hotkey first.")
            return

        # optional mute hotkey — empty means disabled
        mute_spec = self.mute_hotkey_edit.keySequence().toString() or None
        if mute_spec:
            try:
                parse_hotkey(mute_spec)
            except ValueError as e:
                QMessageBox.warning(self, APP_NAME,
                                    f"Invalid mute hotkey: {e}")
                return

        # hotkey change: verify the new combo is free before committing
        ok, message = test_register(spec)
        if not ok:
            ret = QMessageBox.question(
                self, APP_NAME,
                f"Hotkey {spec} {hotkey_error_text(1409) if 'already' in message else message}.\n"
                "Apply anyway?",
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        self.config.hotkey = spec
        self.config.mute_hotkey = mute_spec
        self.config.mode = self.mode_combo.currentData()
        self.config.insertion_mode = self.insert_mode_combo.currentData()
        self.config.mic_device = self.mic_combo.currentData()
        self.config.vad_filter = self.vad_check.isChecked()
        self.config.sound_cues = self.cues_check.isChecked()
        self.config.learn_from_corrections = self.learn_check.isChecked()
        self.config.model = self.model_combo.currentData()
        self.config.language = self.lang_combo.currentData()
        self.config.cleaner = self.cleaner_combo.currentData()
        self.config.notify_on_dictation = self.notify_check.isChecked()

        # start-with-windows: apply to the registry and mirror in config
        want_startup = self.startup_check.isChecked()
        if want_startup != self.config.start_with_windows:
            if set_enabled(want_startup):
                self.config.start_with_windows = want_startup
            else:
                QMessageBox.warning(
                    self, APP_NAME,
                    "Could not update the Start-with-Windows registry entry.\n"
                    "You can add Grogu to startup manually via Task Manager → "
                    "Startup apps.",
                )
        self.config.save()

        self.service.restart_hotkey(spec)
        self.service.restart_mute_hotkey(mute_spec)
        self.service.set_cleaner(self.config.cleaner)
        self.accept()
