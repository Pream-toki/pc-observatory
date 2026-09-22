"""Global Search page — type once, find anything.

Results are grouped by category (Applications, Tools, AI & Models, Scripts,
Tasks, Services, Startup, Projects) and come straight from the inventories
in the local database — nothing is executed and nothing leaves the machine.
Selecting a result jumps to the page that knows more about it.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...utils.format import fmt_gb

# page each category's details live on
_JUMP = {
    "Applications": "applications",
    "Tool Locations": "tools",
    "AI & Models": "ai",
    "Scripts": "scripts",
    "Scheduled Tasks": "automation",
    "Services": "automation",
    "Startup": "automation",
    "Python Projects": "projects",
}

_DEBOUNCE_MS = 250


class SearchPage(QWidget):
    def __init__(self, service, config) -> None:
        super().__init__()
        self._service = service
        self._results: dict[str, list] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        self._box = QLineEdit()
        self._box.setPlaceholderText(
            "Search everything — try: ollama, python, telegram_bot, backup…")
        self._box.setObjectName("SearchBox")
        self._box.setClearButtonEnabled(True)
        font = QFont("Segoe UI", 12)
        self._box.setFont(font)
        layout.addWidget(self._box)

        self._summary = QLabel("Type at least 2 characters to search.")
        self._summary.setObjectName("CardSub")
        layout.addWidget(self._summary)

        self._out = QTextBrowser()
        self._out.setObjectName("DetailsBox")
        self._out.setOpenExternalLinks(False)
        layout.addWidget(self._out, 1)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._run_search)
        self._box.textChanged.connect(self._debounce.start)

    # ---- search ----------------------------------------------------------
    def _run_search(self) -> None:
        q = self._box.text().strip()
        if len(q) < 2:
            self._results = {}
            self._summary.setText("Type at least 2 characters to search.")
            self._out.setHtml("")
            return
        self._results = self._service.global_search(q)
        total = sum(len(v) for v in self._results.values())
        cats = len(self._results)
        self._summary.setText(
            f"{total} result{'s' if total != 1 else ''} in {cats} categor"
            f"{'y' if cats == 1 else 'ies'} for “{q}”")
        self._render(q)

    def _render(self, q: str) -> None:
        parts = []
        for category, items in self._results.items():
            parts.append(
                f"<h2 style='color:#5b8def; margin-bottom:2px;'>{category}"
                f" <span style='color:#7a8494; font-size:11px;'>({len(items)})</span></h2>")
            rows = []
            for item in items:
                title, sub = self._describe(category, item)
                rows.append(f"<li><b>{title}</b>"
                            + (f"<br><span style='color:#9aa3b2; font-size:11px;'>{sub}</span>"
                               if sub else "") + "</li>")
            parts.append("<ul style='margin-top:0;'>" + "".join(rows) + "</ul>")
        if not parts:
            parts.append(f"<p style='color:#9aa3b2;'>No matches for “{q}” "
                         "in the stored inventories. Inventories refresh hourly — "
                         "very recent installs may not be listed yet.</p>")
        self._out.setHtml("".join(parts))

    @staticmethod
    def _describe(category: str, item) -> tuple[str, str]:
        if category == "Applications":
            return (f"{item.name}" + (f" — {item.version}" if item.version else ""),
                    item.install_location or item.publisher)
        if category == "Tool Locations":
            sub = f"{item.exe_path} · PATH-visible" if item.path_visible else item.exe_path
            return item.tool, sub
        if category == "AI & Models":
            if hasattr(item, "size_bytes"):        # AiModelRow
                return (f"{item.name} ({item.runtime})",
                        f"{item.file_path} · {fmt_gb(item.size_bytes / (1024 ** 3))}")
            return item.name, item.exe_path
        if category == "Scripts":
            sub = f"{item.path} · modified {item.modified and ''}{item.kind}"
            return f"{item.name} ({item.project})", item.path + \
                (f" · trigger: {item.trigger_hint}" if item.trigger_hint else "")
        if category == "Scheduled Tasks":
            return item.task_path, f"{item.action_exe} {item.action_args}".strip() + \
                (f" · {item.status}" if item.status else "")
        if category == "Services":
            status = item.status
            return f"{item.display_name or item.name}", \
                f"{item.description[:100]} · {status}"
        if category == "Startup":
            return item.entry_name, f"{item.command} · {item.source}"
        if category == "Python Projects":
            return item.name, item.path
        return ("?", "?")

    # called by the main window when this page is opened
    def focus(self) -> None:
        self._box.setFocus()
