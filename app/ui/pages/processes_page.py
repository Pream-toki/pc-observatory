"""Processes page — every running program, refreshed in the background.

The table is populated from SystemService.processesUpdated (every 5 s).
Search filters across name, path, and user. Selecting a row shows the full
details, including the redacted command line and the 'How was this
discovered?' provenance for the whole list.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
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

from ...models.processes import ProcessInfo
from ...services.service import SystemService
from ...utils.format import fmt_datetime
from ...widgets.how_discovered import HowDiscoveredDialog

_COLUMNS = ["Name", "PID", "CPU %", "RAM (MB)", "User", "Started", "Executable path"]


class ProcessesPage(QWidget):
    def __init__(self, service: SystemService, config) -> None:
        super().__init__()
        self._service = service
        self._infos: list[ProcessInfo] = []
        self._selected_pid: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        controls = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by name, path, or user…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh_table)
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
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._table, 3)

        details_card = QFrame()
        details_card.setObjectName("Card")
        form = QGridLayout(details_card)
        form.setContentsMargins(14, 10, 14, 10)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(4)
        self._detail_labels: dict[str, QLabel] = {}
        for row, (key, title) in enumerate([
            ("name", "Name"), ("pid", "PID / Parent"), ("user", "User"),
            ("started", "Started"), ("path", "Executable"),
            ("cmd", "Command line (secrets are hidden automatically)"),
        ]):
            title_lbl = QLabel(title.upper())
            title_lbl.setObjectName("CardTitle")
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addWidget(title_lbl, row, 0, Qt.AlignmentFlag.AlignTop)
            form.addWidget(value, row, 1)
            self._detail_labels[key] = value
        layout.addWidget(details_card, 2)

        self._service.processesUpdated.connect(self._on_processes)

    # ---- live updates ----------------------------------------------------
    def _on_processes(self, infos: list[ProcessInfo]) -> None:
        self._infos = infos
        self._refresh_table()

    def _refresh_table(self) -> None:
        query = self._search.text().strip().lower()
        rows = [
            p for p in self._infos
            if not query
            or query in p.name.lower()
            or query in p.exe_path.lower()
            or query in p.user.lower()
        ]
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        for r, p in enumerate(rows):
            values = [
                p.name,
                str(p.pid),
                "—" if p.cpu_percent is None else f"{p.cpu_percent:.1f}",
                "—" if p.mem_mb is None else f"{p.mem_mb:,.0f}",
                p.user or "Permission required",
                fmt_datetime(p.create_time) if p.create_time else "Unavailable",
                p.exe_path or "Permission required",
            ]
            for c, text in enumerate(values):
                item = QTableWidgetItem(text)
                if c in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                item.setData(Qt.ItemDataRole.UserRole, id(p))
                self._table.setItem(r, c, item)
        self._table.setSortingEnabled(True)
        self._count_label.setText(f"{len(rows)} of {len(self._infos)} processes")
        self._update_details()

    # ---- details ----------------------------------------------------------
    def _on_selection(self) -> None:
        selected = self._table.selectedItems()
        if selected:
            self._selected_pid = int(self._table.item(selected[0].row(), 1).text())
        else:
            self._selected_pid = None
        self._update_details()

    def _current_info(self) -> ProcessInfo | None:
        if self._selected_pid is None:
            return None
        for p in self._infos:
            if p.pid == self._selected_pid:
                return p
        return None

    def _update_details(self) -> None:
        p = self._current_info()
        if p is None:
            for label in self._detail_labels.values():
                label.setText("—")
            return
        values = {
            "name": p.name,
            "pid": f"{p.pid} / parent {p.ppid}",
            "user": p.user or "Permission required",
            "started": fmt_datetime(p.create_time) if p.create_time else "Unavailable",
            "path": p.exe_path or "Permission required",
            "cmd": p.cmdline or "Permission required",
        }
        for key, text in values.items():
            self._detail_labels[key].setText(text)

    def _show_how(self) -> None:
        result = self._service.last_result("ProcessCollector")
        if result is not None:
            HowDiscoveredDialog.from_result(result, parent=self).exec()
