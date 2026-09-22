"""Assistant page — PC Observatory Assistant (spec §42), LOCAL ONLY.

Uses the user's own Ollama on 127.0.0.1. Nothing is ever sent to the
internet. Quick-question buttons cover the common asks; each builds a small
structured context slice from observed data — never the whole database.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...services import ollama_client
from ...services.service import SystemService
from ...utils.format import fmt_datetime


def _build_context(service: SystemService) -> str:
    """Compact observed-data slice — provenance-honest and small.

    Always includes the live snapshot: running Python/PowerShell processes
    (with their redacted command lines) and script runs, because "what is
    running right now" questions are the most common ones.
    """
    import time as _time
    lines: list[str] = []
    info = service.latest_system_info()
    if info:
        lines.append(f"PC: {info.hostname}, {info.os_name} {info.os_version}, "
                     f"{info.cpu_model}, {info.ram_total_gb:.0f} GB RAM")

    # LIVE: interpreter processes with their script arguments — what the user
    # usually means by "what python files are running". Uses the direct psutil
    # snapshot (fresh at question time) rather than the last 5 s poll, and
    # detects script files from the command line.
    py_running: list[str] = []
    for p in service.live_interpreter_processes():
        cmd = p.get("cmdline") or ""
        script = ""
        low = cmd.lower()
        if ".py " in low or low.endswith(".py"):
            import re as _re
            m = _re.search(r"([\w:.\\/-]+\.py)", low)
            if m:
                script = m.group(1)
        tag = f" -> runs script {script}" if script else ""
        py_running.append(f"PID {p['pid']}: {p['name']} {cmd[:140]}{tag}")
    if py_running:
        lines.append("RUNNING interpreter processes right now (" +
                     str(len(py_running)) + "): " + " | ".join(py_running[:12]))
    else:
        lines.append("RUNNING interpreter processes right now: none")

    # LIVE: script runs recorded by the Automation Monitor.
    open_runs = service.open_script_runs()
    if open_runs:
        lines.append("Automation scripts RUNNING now: " + "; ".join(
            f"{r.script_path} (PID {r.pid}, started "
            f"{_time.strftime('%H:%M:%S', _time.localtime(r.started_at))})"
            for r in open_runs[:10]))
    recent = service.script_runs(limit=10)
    if recent:
        lines.append("Most recent script runs: " + "; ".join(
            f"{r.script_path.split(chr(92))[-1]} "
            f"({'running' if r.ended_at is None else 'ended'})"
            for r in recent[:10]))

    apps = service.applications()
    lines.append(f"Installed applications: {len(apps)}")
    tools = service.tool_locations()
    lines.append("Tool locations: " + "; ".join(
        f"{t.tool} at {t.exe_path}" for t in tools[:15]) or "none")
    models = service.ai_models()
    lines.append("AI models: " + ("; ".join(
        f"{m.name} ({m.runtime}, {m.size_bytes / 1024**3:.1f} GB)" for m in models)
        or "none found"))
    tasks = service.scheduled_tasks()
    interesting = [t for t in tasks
                   if any(k in (t.action_exe or "").lower()
                          for k in ("python", "powershell", "cmd", "ollama"))][:10]
    lines.append(f"Scheduled tasks total: {len(tasks)}; script/AI-related ones: " +
                 ("; ".join(f"{t.task_path} -> {t.action_exe}" for t in interesting)
                  or "none"))
    startup = service.startup_items()
    lines.append("Startup entries: " + ("; ".join(
        f"{s.entry_name} ({s.source}): {s.command}" for s in startup[:10]) or "none"))
    events = service.recent_events(limit=200, since_ts=__import__("time").time() - 86400)
    errors = [e for e in events if e.level in ("Error", "Critical")][:8]
    lines.append(f"Events last 24h: {len(events)}; recent errors: " +
                 ("; ".join(f"[{e.level}] {e.provider} #{e.event_id}" for e in errors)
                  or "none"))
    changes = service.recent_changes()
    lines.append(f"Recorded changes: {len(changes)}" +
                 ("; latest: " + "; ".join(c.title for c in changes[:5]) if changes else ""))
    return "\n".join(lines)


class AssistantPage(QWidget):
    def __init__(self, service: SystemService, config) -> None:
        super().__init__()
        self._service = service
        self._busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        banner = QLabel(
            "LOCAL ONLY — answers come from your own Ollama on this PC. "
            "Nothing is sent to the internet. Answers are based on the data "
            "PC Observatory has collected so far."
        )
        banner.setObjectName("PageSubtitle")
        banner.setWordWrap(True)
        layout.addWidget(banner)

        self._status = QLabel("Checking local Ollama…")
        self._status.setObjectName("PageSubtitle")
        layout.addWidget(self._status)

        quick = QHBoxLayout()
        for text in ("What automations do I have?",
                     "What AI models do I have and what are they for?",
                     "What should I investigate next?"):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _=False, t=text: self.ask(t))
            quick.addWidget(btn)
        quick.addStretch(1)
        layout.addLayout(quick)

        ask_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText(
            "Ask about your PC — answered from observed data by your local AI…")
        self._input.returnPressed.connect(self._on_ask)
        send = QPushButton("Ask")
        send.clicked.connect(self._on_ask)
        ask_row.addWidget(self._input, 1)
        ask_row.addWidget(send)
        layout.addLayout(ask_row)

        self._answer = QTextEdit()
        self._answer.setReadOnly(True)
        layout.addWidget(self._answer, 1)

        self._check_availability()

    def _check_availability(self) -> None:
        ok, detail = ollama_client.is_available()
        if ok:
            self._status.setText(f"Local Ollama ready — models: {detail}")
        else:
            self._status.setText(
                "Local Ollama is not running. Open the Ollama app once (it stays "
                "in the tray), then come back — the Assistant picks it up "
                "automatically. Everything else keeps working without it. "
                f"(Detail: {detail})")
        # Re-check periodically so starting Ollama is picked up without
        # needing to restart PC Observatory.
        from PySide6.QtCore import QTimer
        self._recheck = QTimer(self)
        self._recheck.setInterval(15_000)
        self._recheck.timeout.connect(self._recheck_availability)
        self._recheck.start()

    def _recheck_availability(self) -> None:
        if self._busy:
            return
        ok, detail = ollama_client.is_available()
        if ok:
            self._status.setText(f"Local Ollama ready — models: {detail}")

    def _on_ask(self) -> None:
        question = self._input.text().strip()
        if question:
            self.ask(question)
            self._input.clear()

    def ask(self, question: str) -> None:
        if self._busy:
            return
        ok, detail = ollama_client.is_available()
        if not ok:
            self._answer.append(
                f"\n> {question}\n"
                f"⚠ Local Ollama is not running, so I can't answer. "
                "Open the Ollama app (it stays in the tray) and ask again — "
                "no restart needed.\n\n" + "—" * 60)
            return
        self._busy = True
        self._answer.append(f"\n> {question}\n")
        self._answer.append("Thinking with your local model… "
                            "(first question after a pause can take a minute "
                            "while the model loads)")
        context = _build_context(self._service)

        def work() -> None:
            answer, error = ollama_client.ask(question, context)
            self._answer.append("\n" + (answer or f"⚠ {error}"))
            self._answer.append("\n" + "—" * 60)
            self._busy = False

        threading.Thread(target=work, daemon=True).start()
