"""Automation Monitor collectors (spec §16-17).

Two pieces:

1. ``ScriptInventoryCollector`` — a shallow scan of the configured project
   folders for automation scripts (.py/.ps1/.bat/.cmd). Names, sizes and
   timestamps only; scripts are never executed. It also links scripts to the
   scheduled tasks / startup entries that reference them, so the UI can show
   *what usually triggers* each automation.

2. ``ScriptRunTracker`` — fed by every process poll. When Python/PowerShell/
   cmd runs one of the known scripts (matched from the redacted command
   line), a run row opens; while the process lives the row is touched; when
   it disappears the run is closed with its end time. Every new run also
   becomes a timeline event.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from ..config.settings import AppConfig
from ..database.script_repositories import ScriptRepository
from ..database.ops_repositories import StartupRepository, TaskRepository
from ..models.metrics import CollectorResult, CollectorStatus
from ..models.processes import ProcessInfo
from .base import BaseCollector

log = logging.getLogger(__name__)

_EXTENSIONS = {".py": "python", ".ps1": "powershell", ".bat": "batch", ".cmd": "batch"}
_MAX_SCRIPTS = 500

# Interpreters whose command lines we inspect for script paths.
_INTERPRETER_NAMES = {
    "python.exe", "pythonw.exe", "py.exe",
    "powershell.exe", "pwsh.exe",
    "cmd.exe",
}


class ScriptInventoryCollector(BaseCollector):
    label = "Scripts"

    def __init__(self, run_repo=None, config: AppConfig | None = None,
                 script_repo: ScriptRepository | None = None,
                 roots: list[str] | None = None) -> None:
        super().__init__(run_repo)
        self._config = config
        self._roots_override = roots
        self._script_repo = script_repo or ScriptRepository()

    def collect(self) -> CollectorResult:
        if self._roots_override:
            roots = self._roots_override
        else:
            roots = self._config.project_dirs if self._config \
                else AppConfig().project_dirs
        scripts: list[dict] = []
        skipped: list[str] = []
        for root_pattern in roots:
            root = Path(os.path.expandvars(root_pattern))
            if not root.is_dir():
                skipped.append(str(root))
                continue
            self._scan(root, scripts)
            if len(scripts) >= _MAX_SCRIPTS:
                log.warning("Script scan capped at %d", _MAX_SCRIPTS)
                break

        # The collector owns its write: inventory lands in the DB here, so
        # results are queryable no matter who invoked collect().
        if scripts:
            self._script_repo.upsert_many(scripts)
        self._link_triggers()
        status = CollectorStatus.SUCCESS if scripts or not skipped \
            else CollectorStatus.PARTIAL
        return CollectorResult(
            status=status,
            data=scripts,
            detail=f"Not present: {', '.join(skipped)}" if skipped else "",
            meta=self._meta(
                source="Shallow filesystem scan of configured project folders",
                method=(
                    "Walks the configured project folders (same roots as the "
                    "Python Projects page) up to 4 levels deep collecting "
                    ".py, .ps1, .bat and .cmd files — names, sizes and "
                    "timestamps only. Scripts are NEVER executed or opened. "
                    "Each script is also matched against scheduled-task and "
                    "startup commands to show what usually triggers it."
                ),
            ),
        )

    def _scan(self, root: Path, out: list[dict]) -> None:
        try:
            stack = [(root, 0)]
            while stack and len(out) < _MAX_SCRIPTS:
                current, depth = stack.pop()
                try:
                    children = list(current.iterdir())
                except OSError:
                    continue
                for child in children:
                    if len(out) >= _MAX_SCRIPTS:
                        return
                    try:
                        if child.is_file() and child.suffix.lower() in _EXTENSIONS:
                            st = child.stat()
                            out.append({
                                "path": str(child),
                                "name": child.name,
                                "kind": _EXTENSIONS[child.suffix.lower()],
                                "size_bytes": st.st_size,
                                "modified": st.st_mtime,
                                "project": current.name,
                            })
                        elif (child.is_dir() and depth < 4
                              and not child.name.startswith(".")
                              and child.name.lower() not in
                              (".venv", "venv", "node_modules", "__pycache__",
                               "site-packages")):
                            stack.append((child, depth + 1))
                    except OSError:
                        continue
        except Exception:  # noqa: BLE001 — one bad folder must not stop the scan
            log.exception("Script scan error under %s", root)

    def _link_triggers(self) -> None:
        """Mark scripts that a scheduled task or startup entry references.

        Matching covers the full command (exe + arguments), so a task running
        ``python.exe C:\\bots\\x.py --daily`` links to x.py. The exact task or
        entry name is shown in the trigger column.
        """
        try:
            sources: list[tuple[str, str]] = []  # (kind_label, combined_command)
            for t in TaskRepository().all():
                cmd = f"{t.action_exe} {t.action_args}".lower().replace("/", "\\")
                if cmd.strip():
                    sources.append((f"Scheduled Task: {t.task_path}", cmd))
            for s in StartupRepository().all():
                cmd = (s.command or "").lower().replace("/", "\\")
                if cmd.strip():
                    sources.append((f"Startup: {s.entry_name}", cmd))
        except Exception:  # noqa: BLE001
            return
        try:
            for script in self._script_repo.all():
                p = script.path.lower().replace("/", "\\")
                name_hit = script.name.lower()
                for label, cmd in sources:
                    if p in cmd or (" " + name_hit + " ") in (cmd + " "):
                        self._script_repo.set_trigger_hint(script.path, label)
                        break
        except Exception:  # noqa: BLE001
            log.exception("Trigger linking failed")


class ScriptRunTracker:
    """Detects script executions from process polls (no code is ever run)."""

    def __init__(self, script_repo: ScriptRepository | None = None) -> None:
        self._script_repo = script_repo or ScriptRepository()
        self._paths: list[str] | None = None  # lazy: filled from the DB

    def _known_paths(self) -> list[str]:
        if self._paths is None:
            self._paths = [s.path for s in self._script_repo.all()]
        return self._paths

    def invalidate(self) -> None:
        """Call after the inventory changes so paths reload next poll."""
        self._paths = None

    def update(self, infos: list[ProcessInfo]) -> list[dict]:
        """Feed one process poll; returns new-run events for the timeline."""
        now = time.time()
        seen_runs: set[tuple[str, int]] = set()
        opened: list[tuple[str, ProcessInfo, float]] = []
        new_events: list[dict] = []
        known = self._known_paths()
        known_lower = {p.lower(): p for p in known}

        for p in infos:
            if p.name.lower() not in _INTERPRETER_NAMES or not p.cmdline:
                continue
            cl = p.cmdline.lower().replace("/", "\\")
            matched = None
            for lp, orig in known_lower.items():
                if lp in cl:
                    matched = orig
                    break
            if matched is None:
                # Also catch scripts not yet inventoried: any .py/.ps1/.bat
                # argument on an interpreter command line is an automation we
                # should know about.
                matched = self._guess_path(p.cmdline)
                if matched is None:
                    continue
                # Register it so the inventory picks it up next scan.
                try:
                    self._script_repo.upsert_many([{
                        "path": matched, "name": Path(matched).name,
                        "kind": _EXTENSIONS.get(Path(matched).suffix.lower(), "python"),
                        "size_bytes": 0, "modified": 0.0,
                        "project": Path(matched).parent.name,
                        "trigger_hint": "",
                    }])
                    self.invalidate()
                except Exception:  # noqa: BLE001
                    log.exception("Failed to register discovered script")

            key = (matched, p.pid)
            seen_runs.add(key)
            started = p.create_time if p.create_time else now
            opened.append((matched, p, min(started, now)))
            if started >= now - 20:  # just started → timeline event
                new_events.append({
                    "ts": now,
                    "kind": "script_run",
                    "title": f"Automation running: {Path(matched).name} (PID {p.pid})",
                    "details": f"{matched} — {p.cmdline[:160]}",
                    "ref_table": "script_runs",
                    "ref_key": f"{matched}|{p.pid}",
                })

        # One transaction for all opens + one for all touches (was one commit
        # per running script per poll).
        try:
            from ..database.script_repositories import ScriptRunRepository
            if not hasattr(self, "_runs"):
                self._runs = ScriptRunRepository()
            for matched, p, started in opened:
                self._runs.open_run(matched, p.pid, started,
                                    interpreter=p.name, cmdline=p.cmdline,
                                    trigger="observed")
            self._runs.touch_many([(m, p.pid) for m, p, _ in opened], now)
        except Exception:  # noqa: BLE001
            log.exception("Failed to record script runs")

        self._close_dead_runs(seen_runs, now)
        return new_events

    @staticmethod
    def _guess_path(cmdline: str) -> str | None:
        """Pull a plausible script path out of a redacted command line."""
        for token in cmdline.replace('"', " ").split():
            t = token.lower()
            if t.endswith((".py", ".ps1", ".bat", ".cmd")) and len(token) > 3 \
                    and (":" in t or "\\" in t or "/" in t):
                return token
        return None

    def _close_dead_runs(self, seen: set[tuple[str, int]], now: float) -> None:
        from ..database.script_repositories import ScriptRunRepository
        if not hasattr(self, "_runs"):
            self._runs = ScriptRunRepository()
        for run in self._runs.open_runs():
            if (run.script_path, run.pid) not in seen:
                # The process is gone: close the run. A short grace period is
                # implicit — one missed poll closes it, which is fine at 5 s.
                self._runs.close_run(run.script_path, run.pid, now)
                log.info("Script run ended: %s (pid %s)", run.script_path, run.pid)
