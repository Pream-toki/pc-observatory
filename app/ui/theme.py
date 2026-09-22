"""Theme engine — design tokens + Qt stylesheet.

All colors are defined once as tokens, then rendered into a QSS string.
Every widget reads the same vocabulary, which is what keeps the UI looking
like one professional product instead of a pile of default Qt widgets.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    # Base surfaces
    window: str
    surface: str            # cards
    surface_alt: str        # table rows / inputs
    border: str
    # Text
    text: str
    text_dim: str
    text_bright: str
    # Accents
    accent: str
    accent_soft: str
    ok: str
    warn: str
    error: str
    chart_grid: str
    chart_curve: str


DARK = Palette(
    window="#1b1e24",
    surface="#23272f",
    surface_alt="#2a2f38",
    border="#343a45",
    text="#c9d1dc",
    text_dim="#8b95a3",
    text_bright="#e8edf4",
    accent="#4f8cff",
    accent_soft="#2c3e5f",
    ok="#4cc38a",
    warn="#e5b567",
    error="#e5484d",
    chart_grid="#2d323b",
    chart_curve="#4f8cff",
)

LIGHT = Palette(
    window="#f2f4f7",
    surface="#ffffff",
    surface_alt="#eef1f5",
    border="#d7dce3",
    text="#2b3440",
    text_dim="#66717f",
    text_bright="#141a21",
    accent="#2563eb",
    accent_soft="#dce7fd",
    ok="#177245",
    warn="#9a6b0f",
    error="#c0343a",
    chart_grid="#e4e8ee",
    chart_curve="#2563eb",
)


def build_qss(p: Palette) -> str:
    """Render the full application stylesheet from a palette."""
    return f"""
* {{
    font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
    font-size: 13px;
    color: {p.text};
    selection-background-color: {p.accent};
    selection-color: #ffffff;
}}
QMainWindow, QWidget#Root {{ background-color: {p.window}; }}
QToolTip {{
    background-color: {p.surface_alt}; color: {p.text_bright};
    border: 1px solid {p.border}; padding: 6px 8px; border-radius: 4px;
}}

/* ---------- sidebar ---------- */
QWidget#Sidebar {{ background-color: {p.surface}; border-right: 1px solid {p.border}; }}
QLabel#AppTitle {{ font-size: 16px; font-weight: 600; color: {p.text_bright}; padding: 2px 0; }}
QLabel#AppTagline {{ font-size: 11px; color: {p.text_dim}; padding: 0 0 10px 0; }}
QLabel#NavSection {{
    color: {p.text_dim}; font-size: 11px; font-weight: 600;
    letter-spacing: 1px; padding: 14px 8px 4px 8px;
}}
QPushButton#NavButton {{
    text-align: left; padding: 8px 12px; border: none; border-radius: 6px;
    color: {p.text}; background-color: transparent;
}}
QPushButton#NavButton:hover {{ background-color: {p.surface_alt}; }}
QPushButton#NavButton:checked {{
    background-color: {p.accent_soft}; color: {p.text_bright}; font-weight: 600;
}}

/* ---------- header ---------- */
QWidget#Header {{ background-color: {p.window}; border-bottom: 1px solid {p.border}; }}
QLabel#PageTitle {{ font-size: 19px; font-weight: 600; color: {p.text_bright}; }}
QLabel#PageSubtitle {{ color: {p.text_dim}; }}

/* ---------- cards ---------- */
QFrame#Card {{ background-color: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; }}
QLabel#CardTitle {{
    color: {p.text_dim}; font-size: 11px; font-weight: 600; letter-spacing: 1px;
}}
QLabel#CardValue {{ font-size: 21px; font-weight: 600; color: {p.text_bright}; }}
QLabel#CardSub {{ color: {p.text_dim}; font-size: 12px; }}
QPushButton#HowButton {{
    border: none; color: {p.accent}; font-size: 11px; padding: 2px 4px;
    background: transparent; text-align: left;
}}
QPushButton#HowButton:hover {{ text-decoration: underline; }}

/* ---------- tables ---------- */
QTableWidget {{
    background-color: {p.surface}; border: 1px solid {p.border}; border-radius: 8px;
    gridline-color: {p.border}; alternate-background-color: {p.surface_alt};
}}
QTableWidget::item {{ padding: 4px 8px; }}
QTableWidget::item:selected {{ background-color: {p.accent}; color: #ffffff; }}
QHeaderView::section {{
    background-color: {p.surface_alt}; color: {p.text_dim}; font-weight: 600;
    border: none; border-bottom: 1px solid {p.border}; padding: 6px 8px;
}}

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {p.surface_alt}; border: 1px solid {p.border};
    border-radius: 6px; padding: 6px 8px;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {p.accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {p.surface}; border: 1px solid {p.border};
    selection-background-color: {p.accent};
}}

/* ---------- buttons ---------- */
QPushButton {{
    background-color: {p.surface_alt}; border: 1px solid {p.border};
    border-radius: 6px; padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {p.accent}; }}
QPushButton:pressed {{ background-color: {p.accent_soft}; }}
QPushButton:disabled {{ color: {p.text_dim}; }}

/* ---------- tabs / dialogs / scrollbars ---------- */
QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: 8px; }}
QTabBar::tab {{
    background: transparent; padding: 8px 14px; color: {p.text_dim};
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {p.text_bright}; border-bottom: 2px solid {p.accent}; }}
QDialog {{ background-color: {p.window}; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.text_dim}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 5px; min-width: 30px; }}

QProgressBar {{
    background-color: {p.surface_alt}; border: none; border-radius: 3px;
    max-height: 6px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background-color: {p.accent}; border-radius: 3px; }}
"""


def apply_theme(widget, name: str) -> None:
    """Render the chosen palette and apply it to the whole application.

    Applying to the QApplication (not just one widget) means dialogs — like
    'How was this discovered?' — are themed too. Falls back to the widget
    when no application instance exists (unit tests).
    """
    palette = LIGHT if name == "light" else DARK
    app = QApplication.instance()
    target = app if app is not None else widget
    target.setStyleSheet(build_qss(palette))
