"""Dictionary tab — teach the engine words and correct what it hears.

Two sections: WORDS (sent to the engine as context, capped) and CORRECTIONS
(guaranteed rewrite pass after transcription, tolerant of glued words). Both
are editable in the UI and as a plain JSON file. Supports exporting the
dictionary to JSON and merging another dictionary JSON back in.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from grogu.dictionary import Dictionary
from grogu.ui.design_tokens import Color, Space, Type


class EntryDialog(QDialog):
    """Add/edit a word or a correction, with a live common-word warning."""

    def __init__(self, dictionary: Dictionary, mode: str,
                 existing: dict | None = None, parent=None):
        super().__init__(parent)
        self.dictionary = dictionary
        self.mode = mode  # "word" | "correction"
        self.setWindowTitle(
            "Edit word" if mode == "word" else "Edit correction"
        )
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.XL, Space.XL, Space.XL, Space.XL)
        layout.setSpacing(Space.MD)

        form = QFormLayout()
        form.setSpacing(Space.MD)
        if mode == "word":
            self.heard_edit = QLineEdit()
            form.addRow("WORD", self.heard_edit)
            self.write_edit = None
            if existing:
                self.heard_edit.setText(existing.get("text", ""))
        else:
            self.heard_edit = QLineEdit()
            self.heard_edit.setPlaceholderText("what the model says…")
            self.write_edit = QLineEdit()
            self.write_edit.setPlaceholderText("what to type instead…")
            form.addRow("HEAR", self.heard_edit)
            form.addRow("WRITE", self.write_edit)
            if existing:
                self.heard_edit.setText(existing.get("heard", ""))
                self.write_edit.setText(existing.get("write", ""))
        layout.addLayout(form)

        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet(
            f"color: {Color.LEVEL_AMBER}; background: transparent;"
        )
        layout.addWidget(self.warning)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("CANCEL")
        cancel.clicked.connect(self.reject)
        save = QPushButton("SAVE")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        self.heard_edit.textChanged.connect(self._update_warning)
        self._update_warning()
        self.heard_edit.setFocus()

    def _update_warning(self) -> None:
        heard = self.heard_edit.text().strip()
        if not heard or self.mode == "word":
            self.warning.setText("")
            return
        warnings = self.dictionary.check_warning(heard)
        self.warning.setText("\n".join(warnings))

    def _save(self) -> None:
        heard = self.heard_edit.text().strip()
        if self.mode == "word":
            if not heard:
                QMessageBox.warning(self, "Grogu", "Enter a word or phrase.")
                return
        else:
            write = self.write_edit.text().strip()
            if not heard or not write:
                QMessageBox.warning(
                    self, "Grogu", "Both 'hear' and 'write' are required."
                )
                return
        self.accept()


class _Section(QWidget):
    """One dictionary section: list + ADD/EDIT/DELETE."""

    def __init__(self, title: str, note: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.MD)

        head = QHBoxLayout()
        t = QLabel(title)
        t.setStyleSheet(f"color: {Color.TEXT}; background: transparent;")
        t.setFont(QFont(Type.FONT_UI, Type.SUB, Type.LABEL_WEIGHT))
        head.addWidget(t)
        head.addStretch(1)
        layout.addLayout(head)

        n = QLabel(note)
        n.setWordWrap(True)
        n.setStyleSheet(f"color: {Color.TEXT_FAINT}; background: transparent;")
        n.setFont(QFont(Type.FONT_UI, Type.MICRO, Type.WEIGHT_REGULAR))
        layout.addWidget(n)

        self.list = QListWidget()
        self.list.setSpacing(Space.XS)
        layout.addWidget(self.list, stretch=1)

        btns = QHBoxLayout()
        self.add_btn = QPushButton("ADD")
        self.edit_btn = QPushButton("EDIT")
        self.del_btn = QPushButton("DELETE")
        for b in (self.add_btn, self.edit_btn, self.del_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            btns.addWidget(b)
        btns.addStretch(1)
        layout.addLayout(btns)


class WordRow(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(Space.LG, Space.SM, Space.LG, Space.SM)
        lab = QLabel(text)
        lab.setStyleSheet(f"color: {Color.TEXT}; background: transparent;")
        lay.addWidget(lab)
        lay.addStretch(1)
        tag = QLabel("WORD")
        tag.setStyleSheet(f"color: {Color.TEXT_FAINT}; background: transparent;")
        tag.setFont(QFont(Type.FONT_UI, Type.MICRO, Type.LABEL_WEIGHT))
        lay.addWidget(tag)


class CorrectionRow(QWidget):
    def __init__(self, heard: str, write: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(Space.LG, Space.SM, Space.LG, Space.SM)
        heard_lab = QLabel(heard)
        heard_lab.setStyleSheet(f"color: {Color.TEXT}; background: transparent;")
        arrow = QLabel("→")
        arrow.setStyleSheet(f"color: {Color.LEVEL_AMBER}; background: transparent;")
        write_lab = QLabel(write)
        write_lab.setStyleSheet(f"color: {Color.TEXT}; background: transparent;")
        for w in (heard_lab, arrow, write_lab):
            lay.addWidget(w)
        lay.addStretch(1)


class DictionaryTab(QWidget):
    def __init__(self, dictionary: Dictionary, parent=None):
        super().__init__(parent)
        self.dictionary = dictionary

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.LG, Space.LG, Space.LG, Space.LG)
        layout.setSpacing(Space.MD)

        self.search = QLineEdit()
        self.search.setPlaceholderText("SEARCH DICTIONARY…")
        self.search.setFont(QFont(Type.FONT_MONO, Type.BODY, Type.WEIGHT_MEDIUM))
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)

        cols = QHBoxLayout()
        cols.setSpacing(Space.XL)

        self.words_section = _Section(
            "WORDS",
            "Names and jargon the engine should know. Sent as context "
            "(capped at 10) — a nudge, not a promise.",
        )
        self.corr_section = _Section(
            "CORRECTIONS",
            "Hear X → write Y, applied after transcription. Tolerant of "
            "glued forms: 'CloudCode' and 'Cloud-Code' both catch "
            "'Claude Code'.",
        )
        cols.addWidget(self.words_section, stretch=1)
        cols.addWidget(self.corr_section, stretch=1)
        layout.addLayout(cols, stretch=1)

        hint = QLabel(
            f"Plain-file editable: {self.dictionary.path}"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Color.TEXT_FAINT}; background: transparent;")
        hint.setFont(QFont(Type.FONT_UI, Type.MICRO, Type.WEIGHT_REGULAR))
        layout.addWidget(hint)

        io_row = QHBoxLayout()
        io_row.setSpacing(Space.SM)
        btn_export = QPushButton("EXPORT JSON")
        btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_export.setToolTip("Save the dictionary as a JSON backup")
        btn_export.clicked.connect(self._export_json)
        btn_import = QPushButton("IMPORT JSON")
        btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_import.setToolTip("Merge a dictionary JSON file into this one (no overwrites)")
        btn_import.clicked.connect(self._import_json)
        io_row.addWidget(btn_export)
        io_row.addWidget(btn_import)
        io_row.addStretch(1)
        layout.addLayout(io_row)

        # wiring
        self.words_section.add_btn.clicked.connect(lambda: self._add_word())
        self.words_section.edit_btn.clicked.connect(lambda: self._edit_word())
        self.words_section.del_btn.clicked.connect(lambda: self._del_word())
        self.corr_section.add_btn.clicked.connect(lambda: self._add_corr())
        self.corr_section.edit_btn.clicked.connect(lambda: self._edit_corr())
        self.corr_section.del_btn.clicked.connect(lambda: self._del_corr())

        self.refresh()

    # -- public -------------------------------------------------------------
    def refresh(self, _text: str = "") -> None:
        q = self.search.text()
        self._fill_words(self.dictionary.search_words(q))
        self._fill_corrections(self.dictionary.search_corrections(q))

    # -- word CRUD ----------------------------------------------------------
    def _add_word(self) -> None:
        dlg = EntryDialog(self.dictionary, "word", self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                self.dictionary.add_word(dlg.heard_edit.text())
            except ValueError as e:
                QMessageBox.warning(self, "Grogu", str(e))
            self.refresh()

    def _edit_word(self) -> None:
        row = self.words_section.list.currentRow()
        if row < 0:
            return
        entry = self.dictionary.search_words(self.search.text())[row]
        dlg = EntryDialog(self.dictionary, "word",
                          {"text": entry.text}, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            index = self.dictionary.words.index(entry)
            try:
                self.dictionary.update_word(index, dlg.heard_edit.text())
            except ValueError as e:
                QMessageBox.warning(self, "Grogu", str(e))
            self.refresh()

    def _del_word(self) -> None:
        row = self.words_section.list.currentRow()
        if row < 0:
            return
        entry = self.dictionary.search_words(self.search.text())[row]
        index = self.dictionary.words.index(entry)
        self.dictionary.delete_word(index)
        self.refresh()

    # -- correction CRUD ----------------------------------------------------
    def _add_corr(self) -> None:
        dlg = EntryDialog(self.dictionary, "correction", self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                self.dictionary.add_correction(
                    dlg.heard_edit.text(), dlg.write_edit.text()
                )
            except ValueError as e:
                QMessageBox.warning(self, "Grogu", str(e))
            self.refresh()

    def _edit_corr(self) -> None:
        row = self.corr_section.list.currentRow()
        if row < 0:
            return
        entry = self.dictionary.search_corrections(self.search.text())[row]
        dlg = EntryDialog(self.dictionary, "correction",
                          {"heard": entry.heard, "write": entry.write}, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            index = self.dictionary.corrections.index(entry)
            try:
                self.dictionary.update_correction(
                    index, dlg.heard_edit.text(), dlg.write_edit.text()
                )
            except ValueError as e:
                QMessageBox.warning(self, "Grogu", str(e))
            self.refresh()

    def _del_corr(self) -> None:
        row = self.corr_section.list.currentRow()
        if row < 0:
            return
        entry = self.dictionary.search_corrections(self.search.text())[row]
        index = self.dictionary.corrections.index(entry)
        self.dictionary.delete_correction(index)
        self.refresh()

    # -- fillers ------------------------------------------------------------
    def _fill_words(self, words) -> None:
        self.words_section.list.clear()
        for w in words:
            item = QListWidgetItem()
            item.setSizeHint(WordRow(w.text).sizeHint())
            self.words_section.list.addItem(item)
            self.words_section.list.setItemWidget(item, WordRow(w.text))

    def _fill_corrections(self, corrections) -> None:
        self.corr_section.list.clear()
        for c in corrections:
            item = QListWidgetItem()
            item.setSizeHint(CorrectionRow(c.heard, c.write).sizeHint())
            self.corr_section.list.addItem(item)
            self.corr_section.list.setItemWidget(
                item, CorrectionRow(c.heard, c.write)
            )

    # -- import / export ----------------------------------------------------
    def _export_json(self) -> None:
        default = os.path.join(
            os.path.expanduser("~"), "grogu-dictionary.json"
        )
        path, _sel = QFileDialog.getSaveFileName(
            self, "Export dictionary", default, "JSON (*.json)"
        )
        if not path:
            return
        try:
            self.dictionary.export_to(path)
            QMessageBox.information(
                self, "Grogu",
                f"Exported {len(self.dictionary.words)} words and "
                f"{len(self.dictionary.corrections)} corrections to\n{path}",
            )
        except OSError as e:
            QMessageBox.warning(self, "Grogu", f"Could not export: {e}")

    def _import_json(self) -> None:
        path, _sel = QFileDialog.getOpenFileName(
            self, "Import dictionary", os.path.expanduser("~"),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            counts = self.dictionary.import_from(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(
                self, "Grogu", f"Could not import {path}:\n{e}"
            )
            return
        self.refresh()
        total = counts["words"] + counts["corrections"]
        if total == 0:
            QMessageBox.information(
                self, "Grogu",
                "Nothing new to import — every entry in that file is "
                "already in your dictionary.",
            )
        else:
            QMessageBox.information(
                self, "Grogu",
                f"Imported {counts['words']} word(s) and "
                f"{counts['corrections']} correction(s).",
            )
