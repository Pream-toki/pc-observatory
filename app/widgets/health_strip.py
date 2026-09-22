"""CollectorHealthStrip — the '4 of 5 collectors completed' bar (spec §47).

One pill per collector, colored by its most recent run status, with the real
error detail available via tooltip or the 'How was this discovered?' dialog.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from ..models.metrics import CollectorStatus
from .how_discovered import HowDiscoveredDialog

_LABELS = {
    CollectorStatus.SUCCESS.value: ("OK", "#4cc38a"),
    CollectorStatus.PARTIAL.value: ("Partial", "#e5b567"),
    CollectorStatus.PERMISSION_DENIED.value: ("Permission required", "#e5b567"),
    CollectorStatus.UNSUPPORTED.value: ("Unavailable", "#8b95a3"),
    CollectorStatus.ERROR.value: ("Error", "#e5484d"),
}


def _short_status(status: str) -> tuple[str, str]:
    return _LABELS.get(status, (status, "#8b95a3"))


class _Pill(QFrame):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setToolTip("")
        self.setFixedHeight(30)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 2, 10, 2)
        self._name = QLabel(title)
        self._name.setStyleSheet("font-size:11px; color:#8b95a3;")
        self._state = QLabel("—")
        self._state.setStyleSheet("font-size:11px; font-weight:600;")
        row.addWidget(self._name)
        row.addStretch(1)
        row.addWidget(self._state)

    def set_status(self, status: str, detail: str) -> None:
        text, color = _short_status(status)
        self._state.setText(text)
        self._state.setStyleSheet(f"font-size:11px; font-weight:600; color:{color};")
        self.setToolTip(detail or text)


class CollectorHealthStrip(QFrame):
    """Horizontal strip summarizing every registered collector's latest status."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(6)

        header = QHBoxLayout()
        self._summary = QLabel("Collectors")
        self._summary.setObjectName("CardTitle")
        header.addWidget(self._summary)
        header.addStretch(1)
        self._how_btn = QPushButton("How is this collected?")
        self._how_btn.setObjectName("HowButton")
        self._how_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(self._how_btn)
        outer.addLayout(header)

        self._pill_row = QHBoxLayout()
        self._pill_row.setSpacing(8)
        outer.addLayout(self._pill_row)
        self._pills: dict[str, _Pill] = {}

    def sync(self, health: dict[str, tuple[str, str, float]]) -> None:
        """health: collector name -> (status, detail, started_at)."""
        for name, (status, detail, _ts) in health.items():
            pill = self._pills.get(name)
            if pill is None:
                pill = _Pill(name)
                self._pill_row.addWidget(pill)
                self._pills[name] = pill
            pill.set_status(status, detail)
        self._update_summary(health)

    def _update_summary(self, health: dict[str, tuple[str, str, float]]) -> None:
        total = len(health)
        ok = sum(
            1 for status, _d, _t in health.values()
            if status in (CollectorStatus.SUCCESS.value, CollectorStatus.PARTIAL.value)
        )
        if total == 0:
            self._summary.setText("Collectors starting…")
        elif ok == total:
            self._summary.setText(f"All {total} collectors completed")
        else:
            self._summary.setText(f"{ok} of {total} collectors completed")
