"""Cards — the visual building blocks of the dashboard.

MetricCard: a live value with a thin progress bar (CPU %, RAM %, …).
StatCard:   a static-ish fact (hostname, OS version, uptime, …).
Both carry a 'How was this discovered?' button wired to provenance metadata.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from ..models.metrics import CollectorResult
from .how_discovered import HowDiscoveredDialog


class _CardBase(QFrame):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        self._layout.setSpacing(6)

        title_row = QHBoxLayout()
        self._title = QLabel(title.upper())
        self._title.setObjectName("CardTitle")
        title_row.addWidget(self._title)
        title_row.addStretch(1)
        self._how_btn = QPushButton("How?")
        self._how_btn.setToolTip("How was this discovered? — shows the exact data source")
        self._how_btn.setObjectName("HowButton")
        self._how_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._how_btn.hide()
        self._how_btn.clicked.connect(self._show_how)
        title_row.addWidget(self._how_btn)
        self._layout.addLayout(title_row)

        self._value = QLabel("—")
        self._value.setObjectName("CardValue")
        self._layout.addWidget(self._value)

        self._sub = QLabel("")
        self._sub.setObjectName("CardSub")
        self._sub.setWordWrap(True)
        self._sub.hide()
        self._layout.addWidget(self._sub)

        self._result: CollectorResult | None = None

    def set_value(self, text: str, sub: str = "") -> None:
        self._value.setText(text)
        if sub:
            self._sub.setText(sub)
            self._sub.show()
        else:
            self._sub.hide()

    def set_result(self, result: CollectorResult | None) -> None:
        """Attach provenance; a visible 'How' button appears only when known."""
        self._result = result
        self._how_btn.setVisible(result is not None)

    def _show_how(self) -> None:
        if self._result is not None:
            dlg = HowDiscoveredDialog.from_result(self._result, parent=self)
            dlg.exec()

    def mark_unavailable(self, reason: str = "Unavailable") -> None:
        self.set_value("Unavailable", reason)


class MetricCard(_CardBase):
    """Live value card with a 0-100 progress bar."""

    def __init__(self, title: str, unit_hint: str = "", parent=None) -> None:
        super().__init__(title, parent)
        self._unit_hint = unit_hint
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._layout.addWidget(self._bar)

    def set_percent(self, percent: float, text: str | None = None) -> None:
        clamped = max(0, min(100, int(round(percent))))
        self._bar.setValue(clamped)
        self._value.setText(text if text is not None else f"{clamped}%")

    def set_sub(self, sub: str) -> None:
        if sub:
            self._sub.setText(sub)
            self._sub.show()
        else:
            self._sub.hide()


class StatCard(_CardBase):
    """Plain fact card (no bar)."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(title, parent)
