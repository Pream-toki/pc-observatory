"""Automation Center — services, startup entries, scheduled tasks (spec §17-20)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services.service import SystemService
from ...widgets.how_discovered import HowDiscoveredDialog


class _TableWithSearch(QWidget):
    def __init__(self, headers: list[str], stretch_col: int) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply)
        self._count = QLabel("")
        self._count.setObjectName("PageSubtitle")
        row.addWidget(self._search, 1)
        row.addWidget(self._count)
        layout.addLayout(row)

        self._headers = headers
        self._table = QTableWidget(0, len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            stretch_col, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table)
        self._all_rows: list[list[str]] = []

    def set_rows(self, rows: list[list[str]]) -> None:
        self._all_rows = rows
        self._apply()

    def _apply(self) -> None:
        query = self._search.text().strip().lower()
        rows = [r for r in self._all_rows
                if not query or any(query in cell.lower() for cell in r)]
        self._table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, text in enumerate(values):
                self._table.setItem(r, c, QTableWidgetItem(text))
        self._count.setText(f"{len(rows)} of {len(self._all_rows)}")


class AutomationPage(QWidget):
    def __init__(self, service: SystemService, config) -> None:
        super().__init__()
        self._service = service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        controls = QHBoxLayout()
        controls.addStretch(1)
        refresh = QPushButton("Refresh now")
        refresh.clicked.connect(self._load)
        how = QPushButton("How was this discovered?")
        how.setObjectName("HowButton")
        how.clicked.connect(self._show_how)
        controls.addWidget(refresh)
        controls.addWidget(how)
        layout.addLayout(controls)

        tabs = QTabWidget()
        self._services = _TableWithSearch(
            ["Service", "Display name", "Status", "Start type", "Account", "Executable"], 1)
        tabs.addTab(self._services, "Services")
        self._startup = _TableWithSearch(["Source", "Entry", "Command"], 2)
        tabs.addTab(self._startup, "Startup")
        self._tasks = _TableWithSearch(
            ["Task", "Status", "Runs", "Arguments", "Author"], 0)
        tabs.addTab(self._tasks, "Scheduled Tasks")
        layout.addWidget(tabs, 1)

        note = QLabel(
            "Read-only inventory. This app never starts, stops, enables, or "
            "deletes any automation — that protection is by design."
        )
        note.setObjectName("PageSubtitle")
        layout.addWidget(note)
        self._service.inventoryChanged.connect(self._load)
        self._load()

    def _load(self) -> None:
        self._services.set_rows([
            [s.name, s.display_name or "Unavailable", s.status, s.start_type,
             s.account or "Unavailable", s.exe_path or "Unavailable"]
            for s in self._service.services()
        ])
        self._startup.set_rows([
            [s.source, s.entry_name, s.command or "Unavailable"]
            for s in self._service.startup_items()
        ])
        self._tasks.set_rows([
            [t.task_path, t.status, t.action_exe or "Unavailable",
             t.action_args or "", t.author or "Unavailable"]
            for t in self._service.scheduled_tasks()
        ])

    def _show_how(self) -> None:
        result = self._service.last_result("AutomationCollector")
        if result is not None:
            HowDiscoveredDialog.from_result(result, parent=self).exec()
