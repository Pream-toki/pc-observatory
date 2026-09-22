"""Python Projects page — your development projects (spec §15)."""
from __future__ import annotations

from PySide6.QtWidgets import (
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

_COLUMNS = ["Project", "Path", ".py files", "venv", "Git", "requirements", "Last modified"]


class ProjectsPage(QWidget):
    def __init__(self, service: SystemService, config) -> None:
        super().__init__()
        self._service = service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        controls = QHBoxLayout()
        self._count_label = QLabel("")
        self._count_label.setObjectName("PageSubtitle")
        controls.addWidget(self._count_label)
        controls.addStretch(1)
        refresh = QPushButton("Refresh now")
        refresh.clicked.connect(self._load)
        how = QPushButton("How was this discovered?")
        how.setObjectName("HowButton")
        how.clicked.connect(self._show_how)
        controls.addWidget(refresh)
        controls.addWidget(how)
        layout.addLayout(controls)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (0, 2, 3, 4, 5, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        note = QLabel(
            "Found by scanning configured folders (Documents, C:\\dev, …) up to 3 "
            "levels deep for Python markers. Project code is never executed."
        )
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        self._service.inventoryChanged.connect(self._load)
        self._load()

    def _load(self) -> None:
        projects = self._service.python_projects()
        self._table.setRowCount(len(projects))
        for r, p in enumerate(projects):
            values = [
                p.name, p.path, str(p.py_files),
                "Yes" if p.has_venv else "—",
                "Yes" if p.has_git else "—",
                "Yes" if p.has_requirements else "—",
                fmt_datetime(p.last_modified) if p.last_modified else "Unavailable",
            ]
            for c, text in enumerate(values):
                self._table.setItem(r, c, QTableWidgetItem(text))
        self._count_label.setText(f"{len(projects)} Python projects found")

    def _show_how(self) -> None:
        result = self._service.last_result("PythonProjectCollector")
        if result is not None:
            HowDiscoveredDialog.from_result(result, parent=self).exec()
