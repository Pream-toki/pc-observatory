"""Changes page — snapshots and 'what changed?' (spec §33-35, §54)."""
from __future__ import annotations

import time

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
from ...utils.exporters import export_csv, export_html
from ...utils.format import fmt_datetime


class ChangesPage(QWidget):
    def __init__(self, service: SystemService, config) -> None:
        super().__init__()
        self._service = service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        self._snapshot_info = QLabel("")
        self._snapshot_info.setObjectName("PageSubtitle")
        snap_btn = QPushButton("Take snapshot now")
        snap_btn.clicked.connect(self._take_snapshot)
        export_html_btn = QPushButton("Export HTML report")
        export_html_btn.clicked.connect(self._export_report)
        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self._export_csv)
        top.addWidget(self._snapshot_info)
        top.addStretch(1)
        top.addWidget(snap_btn)
        top.addWidget(export_html_btn)
        top.addWidget(export_csv_btn)
        layout.addLayout(top)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["When", "Change", "Category"])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (0, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, 1)

        note = QLabel(
            "New is not dangerous — changes are recorded so you can review them "
            "calmly, with the source available via each page's 'How?' button."
        )
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        self._load()

    def _load(self) -> None:
        snapshots = self._service.snapshot_list()
        if snapshots:
            latest = max(s.created_at for s in snapshots if s.kind == "manual") \
                if any(s.kind == "manual" for s in snapshots) else \
                max(s.created_at for s in snapshots)
            self._snapshot_info.setText(
                f"{len(snapshots)} snapshots stored · latest {fmt_datetime(latest)}")
        changes = self._service.recent_changes(since_ts=time.time() - 30 * 86400)
        self._table.setRowCount(len(changes))
        for r, ch in enumerate(changes):
            values = [fmt_datetime(ch.ts), ch.title, ch.category]
            for c, text in enumerate(values):
                self._table.setItem(r, c, QTableWidgetItem(text))

    def _take_snapshot(self) -> None:
        snapshot_id = self._service.take_snapshot("manual")
        QMessageBox.information(
            self, "Snapshot taken",
            f"Snapshot #{snapshot_id} stored.\n\nThe next snapshot will be "
            "compared against this one, and any new / removed / changed item "
            "will appear on this page.")
        self._load()

    def _export_csv(self) -> None:
        rows = [[
            self._table.item(r, c).text() if self._table.item(r, c) else ""
            for c in range(3)
        ] for r in range(self._table.rowCount())]
        path = export_csv(["When", "Change", "Category"], rows, "changes")
        QMessageBox.information(self, "Exported", f"Saved to:\n{path}")

    def _export_report(self) -> None:
        sections = []
        changes = self._service.recent_changes(since_ts=time.time() - 30 * 86400)
        sections.append(("Observed changes (last 30 days)",
                         ["When", "Category", "Change"],
                         [[fmt_datetime(c.ts), c.category, c.title] for c in changes]))
        sections.append(("Applications",
                         ["Name", "Version", "Publisher"],
                         [[a.name, a.version or "—", a.publisher or "—"]
                          for a in self._service.applications()]))
        sections.append(("AI models",
                         ["Model", "Runtime", "Size (bytes)"],
                         [[m.name, m.runtime, str(m.size_bytes)]
                          for m in self._service.ai_models()]))
        sections.append(("Startup entries",
                         ["Source", "Entry", "Command"],
                         [[s.source, s.entry_name, s.command]
                          for s in self._service.startup_items()]))
        path = export_html("PC Observatory Report", sections, "report")
        QMessageBox.information(self, "Report exported", f"Saved to:\n{path}")
