"""Automations page — your Python/PowerShell/batch automations in one view.

Top: every script found in the configured project folders, with what usually
triggers it (scheduled task / startup entry / nothing detected).
Bottom: run history for the selected script — when it ran, how long, with
which interpreter, and the (secret-redacted) command line.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...widgets.cards import StatCard
from ...widgets.how_discovered import HowDiscoveredDialog

_KIND_LABELS = {"python": "Python", "powershell": "PowerShell", "batch": "Batch"}


def _fmt_duration(seconds: float) -> str:
    if seconds < 1:
        return "<1 s"
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 5400:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.1f} h"


class ScriptsPage(QWidget):
    def __init__(self, service, config) -> None:
        super().__init__()
        self._service = service
        self._config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(14)

        # ---- summary cards -------------------------------------------------
        top = QHBoxLayout()
        self._card_total = StatCard("Scripts Found")
        self._card_running = StatCard("Running Now")
        self._card_runs = StatCard("Runs (7 days)")
        top.addWidget(self._card_total, 1)
        top.addWidget(self._card_running, 1)
        top.addWidget(self._card_runs, 1)
        layout.addLayout(top)

        # ---- provenance button ---------------------------------------------
        controls = QHBoxLayout()
        how = QPushButton("How was this discovered?")
        how.setObjectName("HowButton")
        how.clicked.connect(self._show_provenance)
        controls.addWidget(how)
        refresh = QPushButton("Refresh now")
        refresh.clicked.connect(self._load)
        controls.addWidget(refresh)
        controls.addStretch(1)
        layout.addLayout(controls)

        # ---- script table + details -----------------------------------------
        split = QSplitter(Qt.Orientation.Vertical)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Script", "Type", "Location", "Modified", "Usually triggered by"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._on_select)
        split.addWidget(self._table)

        self._details = QTextBrowser()
        self._details.setObjectName("DetailsBox")
        split.addWidget(self._details)
        split.setSizes([320, 260])
        layout.addWidget(split, 1)

        self._rows: list = []
        self._runs_by_script: dict[str, list] = {}
        self._selected_path: str | None = None

        self._service.inventoryChanged.connect(self._on_inventory)
        self._service.timelineChanged.connect(self._on_inventory)
        self._load()

    # ---- data ------------------------------------------------------------
    def _load(self) -> None:
        self._rows = list(self._service.scripts())
        runs = self._service.script_runs(limit=1000,
                                         since_ts=time.time() - 7 * 86400)
        self._runs_by_script = {}
        for r in runs:
            self._runs_by_script.setdefault(r.script_path, []).append(r)

        open_now = {r.script_path for r in self._service.open_script_runs()}

        self._table.setRowCount(len(self._rows))
        for i, s in enumerate(self._rows):
            name_item = QTableWidgetItem(s.name + ("   ● running" if s.path in open_now else ""))
            if s.path in open_now:
                name_item.setForeground(Qt.GlobalColor.darkGreen)
            self._table.setItem(i, 0, name_item)
            self._table.setItem(i, 1, QTableWidgetItem(_KIND_LABELS.get(s.kind, s.kind)))
            self._table.setItem(i, 2, QTableWidgetItem(s.path))
            self._table.setItem(i, 3, QTableWidgetItem(
                time.strftime("%Y-%m-%d %H:%M", time.localtime(s.modified))
                if s.modified else "Unavailable"))
            self._table.setItem(i, 4, QTableWidgetItem(s.trigger_hint or "Nothing detected"))
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        runs_7d = sum(len(v) for v in self._runs_by_script.values())
        self._card_total.set_value(str(len(self._rows)))
        self._card_running.set_value(str(len(open_now)),
                                     sub="automations active right now")
        self._card_runs.set_value(str(runs_7d), sub="in the last 7 days")

        if self._selected_path:
            self._render_details(self._selected_path)

    def _on_inventory(self) -> None:
        self._load()

    # ---- details -----------------------------------------------------------
    def _on_select(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        self._selected_path = self._rows[row].path
        self._render_details(self._selected_path)

    def _render_details(self, path: str) -> None:
        runs = self._runs_by_script.get(path, [])
        script = next((s for s in self._rows if s.path == path), None)
        parts = [f"<h3>{Path(path).name}</h3>"]
        if script is not None:
            trigger = script.trigger_hint or "No automatic trigger detected — runs are observed whenever they happen."
            parts.append(
                f"<p><b>Location:</b> {path}<br>"
                f"<b>Size:</b> {script.size_bytes:,} bytes<br>"
                f"<b>Usually triggered by:</b> {trigger}</p>")
        if not runs:
            parts.append("<p>No runs recorded in the last 7 days. "
                         "PC Observatory is watching — the next execution will appear here "
                         "and in the Timeline, with start time, duration and interpreter.</p>")
        else:
            parts.append("<p><b>Run history (last 7 days)</b></p><table cellpadding='3'>"
                         "<tr><th align='left'>Started</th><th align='left'>Duration</th>"
                         "<th align='left'>Interpreter</th><th align='left'>Command</th></tr>")
            for r in runs[:25]:
                started = time.strftime("%m-%d %H:%M:%S", time.localtime(r.started_at))
                if r.ended_at:
                    dur = _fmt_duration(r.ended_at - r.started_at)
                else:
                    dur = f"<b style='color:#2e7d32'>still running</b> ({_fmt_duration(time.time() - r.started_at)})"
                parts.append(
                    f"<tr><td>{started}</td><td>{dur}</td>"
                    f"<td>{r.interpreter}</td><td>{r.cmdline[:90]}</td></tr>")
            parts.append("</table>")
        self._details.setHtml("".join(parts))

    # ---- provenance -----------------------------------------------------
    def _show_provenance(self) -> None:
        result = self._service.last_result("ScriptInventoryCollector")
        if result is not None:
            HowDiscoveredDialog.from_result(result, parent=self).exec()
