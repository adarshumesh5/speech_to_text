"""QSS for standard Qt widgets — built exclusively from design tokens.

Custom-painted widgets (lightsaber, level meter, transport, history rows)
draw their own surfaces from the same tokens; this file only skins the
standard widget chrome (menus, fields, tabs, dialogs, scrollbars). No one-off
values.
"""

import ctypes
import os

from sotto.ui.design_tokens import Border, Color, Radius, Type


def is_high_contrast() -> bool:
    """True when Windows high-contrast / increased-contrast is active."""
    if os.name != "nt":
        return False
    try:
        class _HIGHCONTRASTW(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwFlags", ctypes.c_uint),
                        ("lpszDefaultScheme", ctypes.c_wchar_p)]
        SPI_GETHIGHCONTRAST = 0x0042
        hc = _HIGHCONTRASTW()
        hc.cbSize = ctypes.sizeof(_HIGHCONTRASTW)
        ok = ctypes.WinDLL("user32", use_last_error=True).SystemParametersInfoW(
            SPI_GETHIGHCONTRAST, ctypes.sizeof(hc), ctypes.byref(hc), 0)
        if not ok:
            return False
        HCF_HIGHCONTRASTON = 0x00000001
        return bool(hc.dwFlags & HCF_HIGHCONTRASTON)
    except Exception:  # noqa: BLE001
        return False


def apply_system_accessibility() -> bool:
    """Apply high-contrast overrides if the OS requests them.

    Returns True when overrides were applied (QSS must be rebuilt).
    """
    if is_high_contrast():
        Color.apply_high_contrast()
        return True
    return False

QSS = f"""
* {{
    font-family: {Type.FONT_UI};
    font-size: {Type.BODY}px;
    color: {Color.TEXT};
}}

QMainWindow, QDialog {{
    background-color: {Color.INK};
}}

QLabel {{
    background: transparent;
    color: {Color.TEXT};
}}

/* --- menu bar + menus (industrial, flat) --- */
QMenuBar {{
    background-color: {Color.PANEL};
    color: {Color.TEXT_DIM};
    border-bottom: {Border.THIN}px solid {Color.SEAM_DARK};
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 12px;
}}
QMenuBar::item:selected {{
    background: {Color.PANEL_RAISED};
    color: {Color.TEXT};
}}
QMenu {{
    background-color: {Color.PANEL};
    color: {Color.TEXT};
    border: {Border.THIN}px solid {Color.SEAM_DARK};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 28px 6px 12px;
    border-radius: {Radius.SM}px;
}}
QMenu::item:selected {{
    background-color: {Color.ALUMINUM};
    color: {Color.TEXT_ON_LIGHT};
}}
QMenu::item:disabled {{ color: {Color.DISABLED}; }}
QMenu::separator {{
    height: {Border.THIN}px;
    background: {Color.SEAM_LIGHT};
    margin: 4px 8px;
}}

/* --- tabs (hard-edged, silk labels, clear active state) --- */
QTabWidget::pane {{
    border: {Border.THIN}px solid {Color.SEAM_DARK};
    border-top: {Border.THIN}px solid {Color.SEAM_LIGHT};
    background: {Color.INK};
}}
QTabBar {{
    background: {Color.PANEL};
}}
QTabBar::tab {{
    background: {Color.PANEL};
    color: {Color.TEXT_FAINT};
    font-size: {Type.MICRO}px;
    font-weight: {Type.LABEL_WEIGHT};
    letter-spacing: {Type.LABEL_TRACKING_PX}px;
    padding: 8px 22px;
    border: none;
    border-right: {Border.THIN}px solid {Color.SEAM_DARK};
}}
QTabBar::tab:selected {{
    background: {Color.INK};
    color: {Color.SABER_LT};
    border-top: 2px solid {Color.SABER};
}}
QTabBar::tab:hover:!selected {{
    background: {Color.PANEL_RAISED};
    color: {Color.TEXT_DIM};
}}

/* --- wells: text input, search --- */
QLineEdit, QPlainTextEdit, QTextEdit, QKeySequenceEdit {{
    background-color: {Color.WELL};
    color: {Color.TEXT};
    border: {Border.THIN}px solid {Color.SEAM_LIGHT};
    border-radius: {Radius.SM}px;
    padding: 6px 8px;
    selection-background-color: {Color.ALUMINUM};
    selection-color: {Color.TEXT_ON_LIGHT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QKeySequenceEdit:focus {{
    border: {Border.THIN}px solid {Color.FOCUS};
}}
QLineEdit:disabled {{ color: {Color.DISABLED}; }}

/* --- group boxes (settings) --- */
QGroupBox {{
    background-color: {Color.PANEL};
    border: {Border.THIN}px solid {Color.SEAM_DARK};
    border-top: {Border.THIN}px solid {Color.SEAM_LIGHT};
    border-radius: {Radius.SM}px;
    margin-top: 12px;
    padding: 10px 12px 12px 12px;
    font-size: {Type.MICRO}px;
    font-weight: {Type.LABEL_WEIGHT};
    letter-spacing: {Type.LABEL_TRACKING_PX}px;
    color: {Color.TEXT_DIM};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {Color.TEXT};
}}

/* --- buttons (silver keycap look for dialogs) --- */
QPushButton {{
    background-color: {Color.PANEL_RAISED};
    color: {Color.TEXT};
    border: {Border.THIN}px solid {Color.SEAM_DARK};
    border-top: {Border.THIN}px solid {Color.SEAM_LIGHT};
    border-radius: {Radius.SM}px;
    padding: 6px 16px;
    font-weight: {Type.WEIGHT_MEDIUM};
}}
QPushButton:hover {{
    background-color: {Color.HOVER_BG};
}}
QPushButton:pressed {{
    background-color: {Color.ALUMINUM};
    color: {Color.TEXT_ON_LIGHT};
    border-top: {Border.THIN}px solid {Color.SEAM_DARK};
    padding-top: 7px;
}}
QPushButton:disabled {{
    color: {Color.DISABLED};
    background-color: {Color.PANEL};
}}
QPushButton#Primary {{
    background-color: {Color.ALUMINUM};
    color: {Color.TEXT_ON_LIGHT};
    border: {Border.THIN}px solid {Color.ALUMINUM_DK};
}}
QPushButton#Primary:pressed {{
    background-color: {Color.ALUMINUM_DK};
    padding-top: 7px;
}}

/* small keycap buttons (COPY, row actions) */
QPushButton#Key {{
    background-color: {Color.PANEL_RAISED};
    color: {Color.TEXT_DIM};
    border: {Border.THIN}px solid {Color.SEAM_DARK};
    border-top: {Border.THIN}px solid {Color.SEAM_LIGHT};
    border-radius: {Radius.SM}px;
    padding: 4px 10px;
    font-size: {Type.MICRO}px;
    font-weight: {Type.LABEL_WEIGHT};
    letter-spacing: {Type.LABEL_TRACKING_PX}px;
}}
QPushButton#Key:hover {{
    background-color: {Color.HOVER_BG};
    color: {Color.TEXT};
}}
QPushButton#Key:pressed {{
    background-color: {Color.ALUMINUM};
    color: {Color.TEXT_ON_LIGHT};
    border-top: {Border.THIN}px solid {Color.SEAM_DARK};
    padding-top: 5px;
}}

/* --- combo / spin --- */
QComboBox, QSpinBox {{
    background-color: {Color.WELL};
    color: {Color.TEXT};
    border: {Border.THIN}px solid {Color.SEAM_LIGHT};
    border-radius: {Radius.SM}px;
    padding: 5px 10px;
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {Color.PANEL};
    color: {Color.TEXT};
    border: {Border.THIN}px solid {Color.SEAM_DARK};
    selection-background-color: {Color.ALUMINUM};
    selection-color: {Color.TEXT_ON_LIGHT};
    outline: 0;
}}

/* --- check box: hard square --- */
QCheckBox {{ spacing: 8px; color: {Color.TEXT}; }}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: {Border.THIN}px solid {Color.SEAM_LIGHT};
    background: {Color.WELL};
}}
QCheckBox::indicator:checked {{
    background: {Color.ALUMINUM};
    border-color: {Color.ALUMINUM_DK};
}}

/* --- scrollbars: thin, hard --- */
QScrollBar:vertical {{
    background: {Color.PANEL};
    width: 10px;
    border-left: {Border.THIN}px solid {Color.SEAM_DARK};
}}
QScrollBar::handle:vertical {{
    background: {Color.ALUMINUM_DK};
    min-height: 24px;
    border-radius: 0;
}}
QScrollBar::handle:vertical:hover {{ background: {Color.ALUMINUM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{
    background: {Color.PANEL};
    height: 10px;
    border-top: {Border.THIN}px solid {Color.SEAM_DARK};
}}
QScrollBar::handle:horizontal {{
    background: {Color.ALUMINUM_DK};
    min-width: 24px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* --- misc --- */
QToolTip {{
    background-color: {Color.PANEL};
    color: {Color.TEXT};
    border: {Border.THIN}px solid {Color.SEAM_LIGHT};
    border-radius: {Radius.SM}px;
    padding: 4px 8px;
}}
QStatusBar {{ color: {Color.TEXT_DIM}; }}
QHeaderView::section {{
    background: {Color.PANEL};
    color: {Color.TEXT_DIM};
    border: none;
    border-right: {Border.THIN}px solid {Color.SEAM_DARK};
    padding: 4px 8px;
}}
QListWidget {{
    background: {Color.INK};
    border: none;
    outline: 0;
}}
QListWidget::item {{ border: none; }}
QListWidget::item:selected {{ background: transparent; }}
"""
