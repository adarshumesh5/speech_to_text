"""Model manager dialog — see sizes, download with progress, cancel, delete.

A flat list of the models from Settings: each row shows the name, a
human-readable size, and a status chip (READY / NOT DOWNLOADED /
DOWNLOADING n% / CANCELLING). Buttons per row: DOWNLOAD (or CONTINUE),
DELETE (when installed). A shared progress bar + cancel sits at the bottom
while a download is active. Downloading runs on a worker thread; progress
crosses back to the GUI thread via signals so the UI never blocks.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from grogu import APP_NAME
from grogu.config import MODELS
from grogu.model_manager import (
    delete_model,
    download_model,
    model_downloaded,
    model_size_bytes,
)
from grogu.ui.design_tokens import Color, Space, Type


def _fmt_mb(size_bytes: int) -> str:
    mb = size_bytes / (1024 * 1024)
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb:.0f} MB"


def _silk(text: str, color: str = Color.TEXT_DIM) -> QLabel:
    lab = QLabel(text)
    font = lab.font()
    font.setPointSize(Type.MICRO)
    font.setWeight(QFont.Weight(Type.LABEL_WEIGHT))
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
    lab.setFont(font)
    lab.setStyleSheet(f"color: {color};")
    return lab


class _Worker(QObject):
    """Runs one download off the GUI thread; reports via signals."""

    progressed = Signal(int, int)   # done, total
    finished = Signal(str, bool)    # model, ok
    failed = Signal(str, str)       # model, error

    def __init__(self, model: str, cancel_event: threading.Event):
        super().__init__()
        self._model = model
        self._cancel = cancel_event

    def run(self) -> None:
        try:
            ok = download_model(
                self._model,
                progress=lambda done, total: self.progressed.emit(done, total),
                cancel_event=self._cancel,
            )
            if self._cancel.is_set():
                self.finished.emit(self._model, False)  # cancelled
            else:
                self.finished.emit(self._model, ok)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(self._model, str(e))


class ModelManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Model Manager")
        self.setMinimumWidth(560)
        self._worker: _Worker | None = None
        self._worker_thread: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._active_model: str | None = None
        self._rows: dict[str, "ModelRow"] = {}
        self._build()
        self.refresh()

    # -- ui -----------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.XL, Space.XL, Space.XL, Space.XL)
        layout.setSpacing(Space.MD)

        title = QLabel(APP_NAME)
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {Color.TEXT};"
        )
        layout.addWidget(title)
        layout.addWidget(_silk("MODELS · SIZE · STATUS"))

        self.list = QVBoxLayout()
        self.list.setSpacing(Space.SM)
        layout.addLayout(self.list)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 1000)
        layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        self.status_label.setStyleSheet(
            f"color: {Color.LEVEL_AMBER}; background: transparent;"
        )
        layout.addWidget(self.status_label)

        hint = QLabel(
            "Models download from Hugging Face on first use and are cached "
            "locally. Download ahead of time here so dictation is instant."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Color.TEXT_FAINT}; font-size: 10px;")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton("Cancel download")
        self.cancel_btn.setObjectName("Keycap")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_download)
        buttons.addWidget(self.cancel_btn)
        close = QPushButton("Close")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    # -- rows ---------------------------------------------------------------
    def refresh(self) -> None:
        # clear existing rows
        while self.list.count():
            item = self.list.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._rows.clear()
        for model in MODELS:
            row = ModelRow(model, on_download=self._start_download,
                           on_delete=self._delete_model)
            self.list.addWidget(row)
            self._rows[model] = row

    def _update_row(self, model: str) -> None:
        row = self._rows.get(model)
        if row is not None:
            row.refresh_status()

    # -- actions ------------------------------------------------------------
    def _start_download(self, model: str) -> None:
        if self._worker is not None:
            return  # one download at a time
        self._cancel_event.clear()
        self._active_model = model
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.cancel_btn.setVisible(True)
        row = self._rows.get(model)
        if row is not None:
            row.set_downloading(0)

        self._worker = _Worker(model, self._cancel_event)
        self._worker.progressed.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker_thread = threading.Thread(
            target=self._worker.run, name="grogu-model-dl", daemon=True
        )
        self._worker_thread.start()

    def _cancel_download(self) -> None:
        if self._worker is not None:
            self._cancel_event.set()
            row = self._rows.get(self._active_model or "")
            if row is not None:
                row.set_downloading(None, cancelled=True)
            self.cancel_btn.setEnabled(False)

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setValue(int(1000 * done / total))
        row = self._rows.get(self._active_model or "")
        if row is not None:
            row.set_downloading(done / total if total else 0)

    def _on_finished(self, model: str, ok: bool) -> None:
        self._cleanup_worker()
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self._update_row(model)
        if ok:
            self._notify(f"{model} is ready to use.")
        else:
            self._notify(f"{model} download cancelled — cached files kept.")

    def _on_failed(self, model: str, error: str) -> None:
        self._cleanup_worker()
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self._update_row(model)
        self._notify(f"Could not download {model}: {error}")

    def _cleanup_worker(self) -> None:
        self._worker = None
        self._worker_thread = None
        self._active_model = None
        self.cancel_btn.setEnabled(True)

    def _delete_model(self, model: str) -> None:
        ret = QMessageBox.question(
            self, APP_NAME,
            f"Delete the cached {model} model? It will need to be "
            "re-downloaded before it can be used again.",
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_model(model)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"Could not delete: {e}")
        self._update_row(model)

    def _notify(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setVisible(True)

    def closeEvent(self, event) -> None:
        # don't leave a download thread dangling
        if self._worker is not None:
            self._cancel_event.set()
        super().closeEvent(event)


class ModelRow(QWidget):
    """One model: name · size · status chip · DOWNLOAD/CONTINUE · DELETE."""

    def __init__(self, model: str, on_download, on_delete, parent=None):
        super().__init__(parent)
        self.model = model
        self._on_download = on_download
        self._on_delete = on_delete
        self._downloading: float | None = None  # 0..1, or None
        self._cancelled = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(Space.LG, Space.SM, Space.LG, Space.SM)

        name = QLabel(model)
        name.setStyleSheet(f"color: {Color.TEXT}; background: transparent;")
        name.setFont(QFont(Type.FONT_MONO, Type.BODY, Type.WEIGHT_MEDIUM))
        lay.addWidget(name)

        size = _silk(_fmt_mb(model_size_bytes(model)), Color.TEXT_FAINT)
        lay.addWidget(size)
        lay.addStretch(1)

        self.status = QLabel("…")
        self.status.setFont(QFont(Type.FONT_UI, Type.MICRO, Type.LABEL_WEIGHT))
        self.status.setStyleSheet(
            f"color: {Color.TEXT_FAINT}; background: transparent;"
        )
        lay.addWidget(self.status)

        self.dl_btn = QPushButton("DOWNLOAD")
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(lambda: self._on_download(self.model))
        lay.addWidget(self.dl_btn)

        self.del_btn = QPushButton("DELETE")
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.clicked.connect(lambda: self._on_delete(self.model))
        lay.addWidget(self.del_btn)

        self.refresh_status()

    def refresh_status(self) -> None:
        if model_downloaded(self.model):
            self.status.setText("READY")
            self.status.setStyleSheet(
                f"color: {Color.LEVEL_GREEN}; background: transparent;"
            )
            self.dl_btn.setText("CONTINUE")
            self.del_btn.setEnabled(True)
        else:
            self.status.setText("NOT DOWNLOADED")
            self.status.setStyleSheet(
                f"color: {Color.TEXT_FAINT}; background: transparent;"
            )
            self.dl_btn.setText("DOWNLOAD")
            self.del_btn.setEnabled(False)
        self.dl_btn.setEnabled(True)

    def set_downloading(self, frac: float | None, cancelled: bool = False) -> None:
        if cancelled:
            self._cancelled = True
            self.status.setText("CANCELLING…")
            self.status.setStyleSheet(
                f"color: {Color.LEVEL_AMBER}; background: transparent;"
            )
            self.dl_btn.setEnabled(False)
            return
        self._cancelled = False
        if frac is None:
            self._downloading = None
            self.status.setText("QUEUED…")
        else:
            self._downloading = frac
            self.status.setText(f"DOWNLOADING {int(frac * 100)}%")
            self.status.setStyleSheet(
                f"color: {Color.LEVEL_AMBER}; background: transparent;"
            )
        self.dl_btn.setEnabled(False)
        self.del_btn.setEnabled(False)
