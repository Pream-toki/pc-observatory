"""Applications page — what is installed on this PC (spec §10).

Reads from the database (the ApplicationsCollector refreshes it at startup
and hourly). Search filters by name, publisher, and location.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...database.inventory_repositories import ApplicationRow
from ...services.service import SystemService
from ...widgets.how_discovered import HowDiscoveredDialog

_COLUMNS = ["Application", "Version", "Publisher", "Installed", "Install location", "Source"]


class ApplicationsPage(QWidget):
    def __init__(self, service: SystemService, config) -> None:
        super().__init__()
        self._service = service
        self._rows: list[ApplicationRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        controls = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search applications, publishers, paths…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh)
        controls.addWidget(self._search, 1)
        self._count_label = QLabel("")
        self._count_label.setObjectName("PageSubtitle")
        controls.addWidget(self._count_label)
        how_btn = QPushButton("How was this discovered?")
        how_btn.setObjectName("HowButton")
        how_btn.clicked.connect(self._show_how)
        controls.addWidget(how_btn)
        layout.addLayout(controls)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for col in (0, 1, 2, 3, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        self._service.inventoryChanged.connect(self._load)
        self._load()

    def _load(self) -> None:
        self._rows = self._service.applications()
        self._refresh()

    def _refresh(self) -> None:
        query = self._search.text().strip().lower()
        rows = [
            a for a in self._rows
            if not query
            or query in a.name.lower()
            or query in a.publisher.lower()
            or query in a.install_location.lower()
        ]
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        for r, app in enumerate(rows):
            date = app.install_date
            if len(date) == 8 and date.isdigit():
                date = f"{date[0:4]}-{date[4:6]}-{date[6:8]}"
            values = [
                app.name,
                app.version or "Unavailable",
                app.publisher or "Unavailable",
                date or "Unavailable",
                app.install_location or "Unavailable",
                app.source,
            ]
            for c, text in enumerate(values):
                self._table.setItem(r, c, QTableWidgetItem(text))
        self._table.setSortingEnabled(True)
        self._count_label.setText(f"{len(rows)} of {len(self._rows)} applications")

    def _show_how(self) -> None:
        result = self._service.last_result("ApplicationsCollector")
        if result is not None:
            HowDiscoveredDialog.from_result(result, parent=self).exec()
