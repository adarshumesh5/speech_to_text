"""Grogu's main window — a proper Windows application.

Native frame (resizable, snap, taskbar), dark title bar, a standard menu
bar, the deck strip on top, and two tabs: Transcriptions and Dictionary.
Ctrl+, opens Settings.
"""

from __future__ import annotations

import ctypes
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sotto import APP_NAME, APP_TAGLINE, __version__
from sotto.injector import get_foreground_hwnd
from sotto.ui.deck import DeckPanel
from sotto.ui.design_tokens import Color, Space
from sotto.ui.dictionary_tab import DictionaryTab
from sotto.ui.history_tab import HistoryTab
from sotto.ui.theme import QSS

DWMWA_USE_IMMERSIVE_DARK_MODE = 20


def apply_dark_title_bar(window) -> None:
    """Dark title bar via DWM (Windows 10 1809+). Best-effort; never fatal."""
    if os.name != "nt":
        return
    try:
        hwnd = int(window.winId())
        value = ctypes.c_int(1)
        ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value), ctypes.sizeof(value),
        )
    except Exception:  # noqa: BLE001
        pass


class MainWindow(QMainWindow):
    def __init__(self, service, history_store, dictionary, on_settings, parent=None):
        super().__init__(parent)
        self.service = service
        self.history = history_store
        self.on_settings = on_settings
        self.setWindowTitle(APP_NAME)
        self.resize(920, 640)
        self.setMinimumSize(720, 480)
        self.setStyleSheet(QSS)
        self._build_menu()
        self._build_central()
        self._build_shortcuts()
        # remember the last external window so dictation typed from Grogu's
        # own controls still lands where the cursor was
        QApplication.instance().applicationStateChanged.connect(
            self._on_app_state)
        apply_dark_title_bar(self)

    # -- construction -------------------------------------------------------
    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        act_dictate = QAction("&Start / Stop Dictation", self)
        act_dictate.setShortcut(QKeySequence("F7"))
        act_dictate.triggered.connect(self.service.toggle)
        file_menu.addAction(act_dictate)
        file_menu.addSeparator()
        act_settings = QAction("&Settings…", self)
        act_settings.setShortcut(QKeySequence("Ctrl+,"))
        act_settings.triggered.connect(self.on_settings)
        file_menu.addAction(act_settings)
        file_menu.addSeparator()
        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(act_quit)

        edit_menu = bar.addMenu("&Edit")
        act_copy = QAction("&Copy Selected", self)
        act_copy.setShortcut(QKeySequence("Ctrl+C"))
        act_copy.triggered.connect(self._copy_selected)
        edit_menu.addAction(act_copy)
        act_find = QAction("&Find in History", self)
        act_find.setShortcut(QKeySequence("Ctrl+F"))
        act_find.triggered.connect(self._focus_history_search)
        edit_menu.addAction(act_find)

        view_menu = bar.addMenu("&View")
        self.act_always_top = QAction("Always on &Top", self, checkable=True)
        self.act_always_top.toggled.connect(self._toggle_top)
        view_menu.addAction(self.act_always_top)

        help_menu = bar.addMenu("&Help")
        act_about = QAction("&About Grogu", self)
        act_about.triggered.connect(self._about)
        help_menu.addAction(act_about)

    def _build_central(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(Space.MD, Space.MD, Space.MD, Space.MD)
        layout.setSpacing(Space.MD)

        self.deck = DeckPanel(self.service)
        layout.addWidget(self.deck)
        self.deck.set_hotkey(self.service.config.hotkey)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.history_tab = HistoryTab(self.service, self.history)
        self.dictionary_tab = DictionaryTab(self.service.dictionary)
        self.tabs.addTab(self.history_tab, "TRANSCRIPTIONS")
        self.tabs.addTab(self.dictionary_tab, "DICTIONARY")
        layout.addWidget(self.tabs, stretch=1)

        self.setCentralWidget(central)

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.on_settings)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_history_search)

    # -- public -------------------------------------------------------------
    def add_history_entry(self, entry: dict) -> None:
        self.history.append(entry)
        self.history_tab.refresh()

    def on_service_error(self, message: str) -> None:
        from sotto.ui.tray import Tray

        tray = getattr(self, "_tray", None)
        if tray is not None:
            tray.notify("Grogu", message)

    def set_tray(self, tray) -> None:
        self._tray = tray

    # -- actions ------------------------------------------------------------
    def _copy_selected(self) -> None:
        if self.tabs.currentIndex() == 0:
            row = self.history_tab.list.currentRow()
            if row >= 0 and row < len(self.history_tab._entries):
                QApplication.clipboard().setText(
                    self.history_tab._entries[row].get("text", "")
                )

    def _focus_history_search(self) -> None:
        self.tabs.setCurrentIndex(0)
        self.history_tab.search.setFocus()
        self.history_tab.search.selectAll()

    def _toggle_top(self, on: bool) -> None:
        flag = Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlag(flag, on)
        self.show()

    def _on_app_state(self, state) -> None:
        if state == Qt.ApplicationState.ApplicationInactive:
            self.service.remember_foreign_hwnd(get_foreground_hwnd())

    def _about(self) -> None:
        QMessageBox.about(
            self, APP_NAME,
            f"<b>{APP_NAME}</b> {__version__}<br>{APP_TAGLINE}<br><br>"
            "Push-to-talk dictation. The Force transcribes on your own GPU, "
            "fully offline and private.<br><br>"
            "Hold Ctrl+Shift+Space (or the hotkey in Settings) in any app "
            "and speak — the saber ignites, and Grogu types the polished "
            "text where your cursor is.",
        )

    def closeEvent(self, event) -> None:
        # closing the window hides to tray; Quit (menu/tray) exits for real
        from sotto import APP_NAME as _  # noqa: F401

        self.hide()
        event.ignore()
