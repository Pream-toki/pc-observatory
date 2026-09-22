"""AI & Models page — local AI software and model files (spec §27).

Two tables: detected AI tools (Ollama, LM Studio, Jan, GPT4All) and model
files found in their documented model directories, with human-readable
sizes. Local-first: nothing about these models ever leaves the machine.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services.service import SystemService
from ...utils.format import fmt_gb
from ...widgets.how_discovered import HowDiscoveredDialog


def _fmt_size(nbytes: int) -> str:
    if nbytes <= 0:
        return "Unavailable"
    gb = nbytes / (1024 ** 3)
    if gb >= 0.1:
        return fmt_gb(gb, 2)
    mb = nbytes / (1024 ** 2)
    return f"{mb:.1f} MB"


class AiPage(QWidget):
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
        how_btn = QPushButton("How was this discovered?")
        how_btn.setObjectName("HowButton")
        how_btn.clicked.connect(self._show_how)
        controls.addWidget(how_btn)
        layout.addLayout(controls)

        tabs = QTabWidget()

        self._tools_table = QTableWidget(0, 4)
        self._tools_table.setHorizontalHeaderLabels(["AI tool", "Executable", "Folder", "Detected by"])
        self._tools_table.verticalHeader().setVisible(False)
        self._tools_table.setAlternatingRowColors(True)
        self._tools_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tools_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tabs.addTab(self._tools_table, "AI tools")

        self._models_table = QTableWidget(0, 4)
        self._models_table.setHorizontalHeaderLabels(["Model", "Runtime", "File", "Size on disk"])
        self._models_table.verticalHeader().setVisible(False)
        self._models_table.setAlternatingRowColors(True)
        self._models_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._models_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        tabs.addTab(self._models_table, "Models")

        layout.addWidget(tabs, 1)

        note = QLabel(
            "Only file names and sizes are read. Model contents are never opened "
            "or sent anywhere — local-first by design."
        )
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        self._service.inventoryChanged.connect(self._load)
        self._load()

    def _load(self) -> None:
        tools = self._service.ai_tools()
        self._tools_table.setRowCount(len(tools))
        for r, t in enumerate(tools):
            for c, text in enumerate([
                t.name, t.exe_path, t.install_dir or "Unavailable", t.detection_source,
            ]):
                self._tools_table.setItem(r, c, QTableWidgetItem(text))

        models = self._service.ai_models()
        self._models_table.setRowCount(len(models))
        total = 0
        for r, m in enumerate(models):
            total += m.size_bytes
            for c, text in enumerate([
                m.name, m.runtime, m.file_path, _fmt_size(m.size_bytes),
            ]):
                self._models_table.setItem(r, c, QTableWidgetItem(text))

        parts = [f"{len(tools)} AI tools", f"{len(models)} model files"]
        if total:
            parts.append(f"{_fmt_size(total)} total")
        self._count_label.setText(" · ".join(parts))

    def _show_how(self) -> None:
        result = self._service.last_result("AiCollector")
        if result is not None:
            HowDiscoveredDialog.from_result(result, parent=self).exec()
