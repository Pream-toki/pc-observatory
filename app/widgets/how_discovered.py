"""'How was this discovered?' — the app's signature learning feature.

Every card, table row, or detail view can open this dialog. It shows exactly
what data source was used, how it works, when it ran, and its status —
turning every number in the UI into a small IT lesson.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models.metrics import CollectorMeta, CollectorResult, CollectorStatus
from ..utils.format import fmt_datetime

_STATUS_LABEL = {
    CollectorStatus.SUCCESS: "OK",
    CollectorStatus.PARTIAL: "Partial",
    CollectorStatus.PERMISSION_DENIED: "Permission required",
    CollectorStatus.UNSUPPORTED: "Unavailable",
    CollectorStatus.ERROR: "Error",
}


def _row(title: str) -> tuple[QLabel, QLabel]:
    """A 'Title: value' pair; the value label wraps long text."""
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet("font-weight:600;")
    value_lbl = QLabel("")
    value_lbl.setWordWrap(True)
    value_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return title_lbl, value_lbl


class HowDiscoveredDialog(QDialog):
    """Shows collector, source, method, collection time, and status."""

    def __init__(self, meta: CollectorMeta | None, detail: str = "",
                 status: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("How was this discovered?")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            "This is the real source of the information you just looked at. "
            "Nothing is estimated and nothing is invented."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        grid = QVBoxLayout()
        grid.setSpacing(8)

        rows: list[tuple[str, str]] = [
            ("Collector", meta.collector if meta else "—"),
            ("Data source", meta.source if meta else "—"),
            ("How it works", meta.method if meta else "—"),
            ("Collected at", fmt_datetime(meta.collected_at) if meta else "—"),
            ("Status", status or "OK"),
        ]
        if detail:
            rows.append(("Details", detail))

        self._value_labels: list[QLabel] = []
        for title, value in rows:
            row_h = QHBoxLayout()
            title_lbl, value_lbl = _row(title)
            value_lbl.setText(value)
            self._value_labels.append(value_lbl)
            row_h.addWidget(title_lbl)
            row_h.addStretch(1)
            grid.addLayout(row_h)
            grid.addWidget(value_lbl)
        layout.addLayout(grid)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addSpacing(4)
        layout.addLayout(buttons)

    @classmethod
    def from_result(cls, result: CollectorResult,
                    parent: QWidget | None = None) -> "HowDiscoveredDialog":
        status = _STATUS_LABEL.get(result.status, result.status.value)
        return cls(result.meta, detail=result.detail, status=status, parent=parent)
