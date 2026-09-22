"""Tool Locations page — "where exactly is my software installed?" (spec §11-12).

Two parts:
1. The inventory table: every detected tool install with its path and whether
   it is PATH-visible, with 'Open Location' / 'Copy Path' buttons.
2. The command resolver: type a command name ('python', 'git', …) and see
   which executable Windows would actually run — without executing anything.
"""
from __future__ import annotations

from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication,
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

from ...services.service import SystemService
from ...utils.command_resolver import resolve_command
from ...widgets.how_discovered import HowDiscoveredDialog

_COLUMNS = ["Tool", "Executable path", "Install directory", "On PATH?", "Detected by"]


class ToolsPage(QWidget):
    def __init__(self, service: SystemService, config) -> None:
        super().__init__()
        self._service = service
        self._rows = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        # ---- command resolver card ----------------------------------------
        resolver_card = QWidget()
        resolver_layout = QVBoxLayout(resolver_card)
        resolver_layout.setContentsMargins(0, 0, 0, 0)
        resolver_row = QHBoxLayout()
        prompt = QLabel("Which command?")
        prompt.setObjectName("PageSubtitle")
        self._cmd_input = QLineEdit()
        self._cmd_input.setPlaceholderText("Type a command, e.g. python — then Enter")
        self._cmd_input.returnPressed.connect(self._resolve)
        resolve_btn = QPushButton("Resolve")
        resolve_btn.clicked.connect(self._resolve)
        resolver_row.addWidget(prompt)
        resolver_row.addWidget(self._cmd_input, 1)
        resolver_row.addWidget(resolve_btn)
        resolver_layout.addLayout(resolver_row)

        self._cmd_result = QLabel(
            "Shows which executable Windows would run for that command — "
            "without executing anything."
        )
        self._cmd_result.setObjectName("PageSubtitle")
        self._cmd_result.setWordWrap(True)
        resolver_layout.addWidget(self._cmd_result)
        layout.addWidget(resolver_card)

        # ---- inventory table ------------------------------------------------
        controls = QHBoxLayout()
        self._count_label = QLabel("")
        self._count_label.setObjectName("PageSubtitle")
        controls.addWidget(self._count_label)
        controls.addStretch(1)
        open_btn = QPushButton("Open Location")
        open_btn.clicked.connect(self._open_location)
        copy_btn = QPushButton("Copy Path")
        copy_btn.clicked.connect(self._copy_path)
        how_btn = QPushButton("How was this discovered?")
        how_btn.setObjectName("HowButton")
        how_btn.clicked.connect(self._show_how)
        controls.addWidget(open_btn)
        controls.addWidget(copy_btn)
        controls.addWidget(how_btn)
        layout.addLayout(controls)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (0, 2, 3, 4):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        self._service.inventoryChanged.connect(self._load)
        self._load()

    def _load(self) -> None:
        self._rows = self._service.tool_locations()
        self._table.setRowCount(len(self._rows))
        for r, tool in enumerate(self._rows):
            values = [
                tool.tool,
                tool.exe_path,
                tool.install_dir or "Unavailable",
                "Yes" if tool.path_visible else "No",
                tool.detection_source,
            ]
            for c, text in enumerate(values):
                self._table.setItem(r, c, QTableWidgetItem(text))
        self._count_label.setText(f"{len(self._rows)} tool installations found")

    # ---- command resolver ---------------------------------------------------
    def _resolve(self) -> None:
        name = self._cmd_input.text().strip()
        if not name:
            return
        matches = resolve_command(name)
        if not matches:
            self._cmd_result.setText(
                f"No executable named '{name}' was found on PATH. "
                "Either it is not installed, or its folder is not on PATH."
            )
            return
        winner = matches[0]
        extra = ""
        if len(matches) > 1:
            others = "\n".join(f"    {m}" for m in matches[1:6])
            extra = f"\nAlso found (later on PATH, would be shadowed):\n{others}"
        self._cmd_result.setText(
            f"Command '{name}' → Windows would run:\n    {winner}{extra}"
        )

    # ---- row actions ----------------------------------------------------------
    def _selected_row(self):
        rows = {index.row() for index in self._table.selectedIndexes()}
        if not rows:
            return None
        return self._rows[rows.pop()]

    def _open_location(self) -> None:
        row = self._selected_row()
        if row:
            QDesktopServices.openUrl(QUrl.fromLocalFile(row.install_dir or row.exe_path))

    def _copy_path(self) -> None:
        row = self._selected_row()
        if row:
            QApplication.clipboard().setText(row.exe_path)

    def _show_how(self) -> None:
        result = self._service.last_result("ToolLocationsCollector")
        if result is not None:
            HowDiscoveredDialog.from_result(result, parent=self).exec()
