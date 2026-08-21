"""Transcriptions tab — searchable history with copy per row and
correction-fired badges. Rows share a strict column grid so timestamps,
source tags and text all line up across entries. Supports exporting the
current (filtered) list to plain text, Markdown, or CSV.
"""

from __future__ import annotations

import datetime as _dt
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from grogu.ui.design_tokens import Color, Space, Type

# shared column geometry (px)
COL_TS = 66
COL_SRC = 60
COL_ACT = 64


def _fmt_ts(ts: float) -> str:
    try:
        return _dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    except (OSError, ValueError):
        return "--:--:--"


def _label(text: str, color: str, font) -> QLabel:
    lab = QLabel(text)
    lab.setFont(font)
    lab.setStyleSheet(f"color: {color}; background: transparent;")
    return lab


class HistoryRow(QWidget):
    """One dictation on a strict grid: TS | SRC | text…… | COPY."""

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.entry = entry
        self._hover = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        grid = QGridLayout(self)
        grid.setContentsMargins(Space.LG, Space.MD, Space.LG, Space.MD)
        grid.setHorizontalSpacing(Space.LG)
        grid.setVerticalSpacing(Space.XS)
        grid.setColumnStretch(2, 1)
        grid.setColumnMinimumWidth(0, COL_TS)
        grid.setColumnMinimumWidth(1, COL_SRC)
        grid.setColumnMinimumWidth(3, COL_ACT)

        mono = QFont(Type.FONT_MONO, Type.MICRO, Type.WEIGHT_MEDIUM)
        silk = QFont(Type.FONT_UI, Type.MICRO, Type.LABEL_WEIGHT)
        body = QFont(Type.FONT_UI, Type.BODY, Type.WEIGHT_REGULAR)

        ts = _label(_fmt_ts(entry.get("ts", 0)), Color.TEXT_FAINT, mono)
        grid.addWidget(ts, 0, 0, Qt.AlignmentFlag.AlignTop)

        src = _label(entry.get("source", "").upper() or "PTT",
                     Color.TEXT_DIM, silk)
        grid.addWidget(src, 0, 1, Qt.AlignmentFlag.AlignTop)

        text = QLabel(entry.get("text", ""))
        text.setWordWrap(True)
        text.setFont(body)
        text.setStyleSheet(f"color: {Color.TEXT}; background: transparent;")
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(text, 0, 2, Qt.AlignmentFlag.AlignTop)

        copy = QPushButton("COPY")
        copy.setObjectName("Key")
        copy.setFixedSize(COL_ACT, 22)
        copy.setCursor(Qt.CursorShape.PointingHandCursor)
        copy.setToolTip("Copy this transcription (Ctrl+click row also copies)")
        copy.clicked.connect(self._copy)
        grid.addWidget(copy, 0, 3, Qt.AlignmentFlag.AlignTop)

        row = 1
        fired = entry.get("corrections") or []
        if fired:
            parts = []
            for c in fired:
                label = f"{c.get('heard', '')} → {c.get('write', '')}"
                if c.get("count", 1) > 1:
                    label += f" ×{c['count']}"
                parts.append(label)
            corr = QLabel("CORR  " + "  |  ".join(parts))
            corr.setWordWrap(True)
            corr.setFont(silk)
            corr.setStyleSheet(f"color: {Color.LEVEL_AMBER}; background: transparent;")
            grid.addWidget(corr, row, 2, 1, 2, Qt.AlignmentFlag.AlignTop)
            row += 1

        if entry.get("inserted") is False:
            warn = QLabel("NOT INSERTED — text is on the clipboard (Ctrl+V)")
            warn.setFont(silk)
            warn.setStyleSheet(f"color: {Color.LEVEL_AMBER}; background: transparent;")
            grid.addWidget(warn, row, 2, 1, 2, Qt.AlignmentFlag.AlignTop)
            row += 1

        if entry.get("duration"):
            dur = _label(f"{entry['duration']:.1f}s", Color.TEXT_FAINT, mono)
            grid.addWidget(dur, row, 2, Qt.AlignmentFlag.AlignTop)

    # -- interaction --------------------------------------------------------
    def _copy(self) -> None:
        QApplication.clipboard().setText(self.entry.get("text", ""))

    def enterEvent(self, _event) -> None:
        self._hover = True
        self._apply_bg()

    def leaveEvent(self, _event) -> None:
        self._hover = False
        self._apply_bg()

    def _apply_bg(self) -> None:
        bg = Color.HOVER_BG if self._hover else "transparent"
        self.setStyleSheet(f"QWidget {{ background: {bg}; }}")
        self.update()


class HistoryTab(QWidget):
    def __init__(self, service, history_store, parent=None):
        super().__init__(parent)
        self.service = service
        self.history = history_store
        self._entries: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.LG, Space.LG, Space.LG, Space.LG)
        layout.setSpacing(Space.MD)

        top = QHBoxLayout()
        top.setSpacing(Space.MD)
        self.search = QLineEdit()
        self.search.setPlaceholderText("SEARCH HISTORY — TEXT OR RAW…")
        self.search.setFont(QFont(Type.FONT_MONO, Type.BODY, Type.WEIGHT_MEDIUM))
        self.search.textChanged.connect(self._apply_filter)
        top.addWidget(self.search, stretch=1)

        export = QPushButton("EXPORT")
        export.setCursor(Qt.CursorShape.PointingHandCursor)
        export.setToolTip("Export the current list to text, Markdown, or CSV")
        export.clicked.connect(self._export)
        top.addWidget(export)
        layout.addLayout(top)

        self.list = QListWidget()
        self.list.setSpacing(Space.XS)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list, stretch=1)

        self.hint = QLabel("Ctrl+click a row to copy · Ctrl+Z undoes what "
                           "Grogu typed · corrections fired show in amber.")
        self.hint.setStyleSheet(f"color: {Color.TEXT_FAINT}; background: transparent;")
        self.hint.setFont(QFont(Type.FONT_UI, Type.MICRO, Type.WEIGHT_REGULAR))
        layout.addWidget(self.hint)

        self.refresh()

    # -- public -------------------------------------------------------------
    def refresh(self) -> None:
        self._entries = self.history.search(self.search.text())
        self._rebuild()

    def _apply_filter(self, _text: str) -> None:
        self._entries = self.history.search(self.search.text())
        self._rebuild()

    def _rebuild(self) -> None:
        self.list.clear()
        for entry in self._entries:
            item = QListWidgetItem()
            row = HistoryRow(entry)
            item.setSizeHint(row.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, row)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
            row = self.list.row(item)
            if 0 <= row < len(self._entries):
                QApplication.clipboard().setText(
                    self._entries[row].get("text", "")
                )

    def _export(self) -> None:
        """Save the current (filtered) entries to a file chosen by the user."""
        fmt, path = self._ask_export_target()
        if not path:
            return
        try:
            self.history.export(self._entries, fmt=fmt, path=path)
            self._flash_exported(os.path.basename(path))
        except OSError as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Grogu", f"Could not export: {e}")

    def _ask_export_target(self) -> tuple[str, str]:
        """Show a save dialog; returns (fmt, path) or ("", "") if cancelled."""
        default = os.path.join(
            os.path.expanduser("~"), "Grogu-history.txt"
        )
        path, _sel = QFileDialog.getSaveFileName(
            self,
            "Export transcriptions",
            default,
            "Plain text (*.txt);;Markdown (*.md);;CSV (*.csv)",
        )
        if not path:
            return "", ""
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        fmt = ext if ext in ("txt", "md", "csv") else "txt"
        return fmt, path

    def _flash_exported(self, name: str) -> None:
        """Briefly swap the hint text to confirm the export landed."""
        from PySide6.QtCore import QTimer

        original = self.hint.text()
        self.hint.setText(f"Exported {len(self._entries)} entries → {name}")
        QTimer.singleShot(3000, lambda: self.hint.setText(original))
