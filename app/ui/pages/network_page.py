"""Network page — which programs are listening on which ports (spec §22)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services.service import SystemService
from ...utils.exporters import export_csv
from ...widgets.how_discovered import HowDiscoveredDialog

_COLUMNS = ["Port", "Address", "Protocol", "Process", "PID", "Executable"]


class NetworkPage(QWidget):
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
        export = QPushButton("Export CSV")
        export.clicked.connect(self._export)
        how = QPushButton("How was this discovered?")
        how.setObjectName("HowButton")
        how.clicked.connect(self._show_how)
        controls.addWidget(refresh)
        controls.addWidget(export)
        controls.addWidget(how)
        layout.addLayout(controls)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        for col in range(5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        note = QLabel(
            "Listening ports only — this page observes your PC, it never scans "
            "other computers. An unknown port is 'Unknown', not malicious."
        )
        note.setObjectName("PageSubtitle")
        layout.addWidget(note)
        self._load()

    def _load(self) -> None:
        ports = self._service.listening_ports()
        self._table.setRowCount(len(ports))
        for r, p in enumerate(ports):
            values = [str(p.local_port), p.local_ip, p.protocol,
                      p.process_name or "Permission required",
                      str(p.pid) if p.pid else "—",
                      p.exe_path or "Permission required"]
            for c, text in enumerate(values):
                self._table.setItem(r, c, QTableWidgetItem(text))
        self._count_label.setText(f"{len(ports)} listening ports")

    def _export(self) -> None:
        rows = [[
            self._table.item(r, c).text() if self._table.item(r, c) else ""
            for c in range(self._table.columnCount())
        ] for r in range(self._table.rowCount())]
        path = export_csv(_COLUMNS, rows, "listening_ports")
        QMessageBox.information(self, "Exported", f"Saved to:\n{path}")

    def _show_how(self) -> None:
        result = self._service.last_result("NetworkCollector")
        if result is not None:
            HowDiscoveredDialog.from_result(result, parent=self).exec()
