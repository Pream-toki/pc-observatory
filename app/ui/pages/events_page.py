"""Events page — recent Windows event log entries (spec §23-24)."""
from __future__ import annotations

import time

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services.service import SystemService
from ...utils.format import fmt_datetime
from ...widgets.how_discovered import HowDiscoveredDialog

_LEVEL_HINTS = {
    "Error": "Something failed. One error is normal on any Windows PC — patterns matter.",
    "Warning": "A component reports an issue worth noting, not necessarily a problem.",
    "Critical": "A serious failure was recorded. Read the message before concluding anything.",
    "Information": "Normal operational records — most events are these.",
}


class EventsPage(QWidget):
    def __init__(self, service: SystemService, config) -> None:
        super().__init__()
        self._service = service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        controls = QHBoxLayout()
        label = QLabel("Level")
        label.setObjectName("PageSubtitle")
        self._level = QComboBox()
        self._level.addItem("All levels", userData=None)
        for lv in ("Critical", "Error", "Warning", "Information"):
            self._level.addItem(lv, userData=lv)
        self._level.currentIndexChanged.connect(lambda _i: self._load())
        self._count_label = QLabel("")
        self._count_label.setObjectName("PageSubtitle")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._load)
        how = QPushButton("How was this discovered?")
        how.setObjectName("HowButton")
        how.clicked.connect(self._show_how)
        controls.addWidget(label)
        controls.addWidget(self._level)
        controls.addWidget(self._count_label)
        controls.addStretch(1)
        controls.addWidget(refresh)
        controls.addWidget(how)
        layout.addLayout(controls)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["When", "Level", "Source", "Event ID", "Message"])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for col in range(4):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        self._hint = QLabel("")
        self._hint.setObjectName("PageSubtitle")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        self._load()

    def _load(self) -> None:
        level = self._level.currentData()
        events = self._service.recent_events(limit=400, level=level,
                                             since_ts=time.time() - 86400)
        self._table.setRowCount(len(events))
        counts: dict[str, int] = {}
        for r, ev in enumerate(events):
            counts[ev.level] = counts.get(ev.level, 0) + 1
            values = [fmt_datetime(ev.ts), ev.level, ev.provider or "Unavailable",
                      str(ev.event_id), ev.message or "Unavailable"]
            for c, text in enumerate(values):
                self._table.setItem(r, c, QTableWidgetItem(text))
        self._count_label.setText(
            f"{len(events)} events in the last 24 h · "
            + " · ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        )
        hints = [f"{k}: {_LEVEL_HINTS.get(k, '')}" for k in ("Critical", "Error", "Warning")
                 if counts.get(k)]
        self._hint.setText(" ".join(hints) if hints else
                           "Only informational events in the last 24 hours — quiet is good.")

    def _show_how(self) -> None:
        result = self._service.last_result("EventLogCollector")
        if result is not None:
            HowDiscoveredDialog.from_result(result, parent=self).exec()
