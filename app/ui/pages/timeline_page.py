"""Timeline page — 'what happened on my PC', newest first.

Events come from the database via SystemService: Windows boots, processes
first observed running after the app started, and (in later phases) much
more. A kind filter keeps the view readable.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QComboBox,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...database.history_repositories import TimelineEvent
from ...services.service import SystemService
from ...utils.format import fmt_datetime

_KIND_LABELS = {
    "boot": "Boot",
    "process_first_seen": "Process",
    "collector": "Collector",
    "manual": "Note",
}


class TimelinePage(QWidget):
    def __init__(self, service: SystemService, config) -> None:
        super().__init__()
        self._service = service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        controls = QHBoxLayout()
        label = QLabel("Show")
        label.setObjectName("PageSubtitle")
        self._kind_combo = QComboBox()
        self._kind_combo.addItem("All events", userData=None)
        for kind, text in (("boot", "Boots"), ("process_first_seen", "Processes"),
                           ("manual", "My notes")):
            self._kind_combo.addItem(text, userData=kind)
        self._kind_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        controls.addWidget(label)
        controls.addWidget(self._kind_combo)
        controls.addStretch(1)
        count_label = QLabel("")
        count_label.setObjectName("PageSubtitle")
        self._count_label = count_label
        controls.addWidget(count_label)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        controls.addWidget(refresh_btn)
        layout.addLayout(controls)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["When", "Type", "Event"])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setWordWrap(True)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        hint = QLabel(
            "Events are recorded from the moment PC Observatory runs. "
            "Every entry shows exactly when it was observed — nothing is guessed."
        )
        hint.setObjectName("PageSubtitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._service.timelineChanged.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        kind = self._kind_combo.currentData()
        events: list[TimelineEvent] = self._service.timeline_events(limit=400, kind=kind)
        self._table.setRowCount(len(events))
        for r, ev in enumerate(events):
            when = QTableWidgetItem(fmt_datetime(ev.ts))
            kind_item = QTableWidgetItem(_KIND_LABELS.get(ev.kind, ev.kind))
            title = QTableWidgetItem(ev.title)
            title.setToolTip(ev.details)
            for c, item in ((0, when), (1, kind_item), (2, title)):
                item.setData(Qt.ItemDataRole.UserRole, ev.details)
                self._table.setItem(r, c, item)
        self._count_label.setText(f"{len(events)} events")
