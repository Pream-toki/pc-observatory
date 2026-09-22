"""Font helpers — single place so typography stays consistent."""
from __future__ import annotations

from PySide6.QtGui import QFont


def card_value_font() -> QFont:
    f = QFont("Segoe UI")
    f.setPointSizeF(13.5)
    f.setWeight(QFont.Weight.DemiBold)
    return f


def page_title_font() -> QFont:
    f = QFont("Segoe UI")
    f.setPointSizeF(14.0)
    f.setWeight(QFont.Weight.DemiBold)
    return f
