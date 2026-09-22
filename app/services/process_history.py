"""ProcessHistory — turns process polls into history.

Keeps the set of process identities seen since this app instance started and
diffs each poll against it: a brand-new (pid, name, exe_path) emits a
'process_first_seen' timeline event, and all current processes are upserted
into process_seen with first/last-seen timestamps.

Note on honesty: 'first seen' means the first time *PC Observatory* saw it.
A process that started before the app did shows the app's start time as its
first_seen — the UI labels this correctly rather than pretending.
"""
from __future__ import annotations

import logging
import time

from ..database.history_repositories import ProcessRepository, ProcessSeen, TimelineEvent
from ..models.processes import ProcessInfo

log = logging.getLogger(__name__)


class ProcessHistory:
    def __init__(self, proc_repo: ProcessRepository | None = None) -> None:
        self._proc_repo = proc_repo or ProcessRepository()
        self._known: set[tuple[int, str, str]] | None = None  # None = first poll

    def update(self, infos: list[ProcessInfo], now: float | None = None) -> list[TimelineEvent]:
        """Record a poll; returns any new timeline events (first-seen)."""
        now = now if now is not None else time.time()
        rows: list[ProcessSeen] = []
        new_events: list[TimelineEvent] = []

        current: set[tuple[int, str, str]] = set()
        for p in infos:
            key = (p.pid, p.name, p.exe_path)
            current.add(key)
            rows.append(ProcessSeen(
                pid=p.pid, name=p.name, exe_path=p.exe_path,
                first_seen=now, last_seen=now,
                last_cpu=p.cpu_percent, last_mem_mb=p.mem_mb,
            ))
            if self._known is not None and key not in self._known:
                when = p.create_time if p.create_time else now
                new_events.append(TimelineEvent(
                    ts=min(when, now),
                    kind="process_first_seen",
                    title=f"{p.name} started (PID {p.pid})",
                    details=p.exe_path or "Executable path: Permission required",
                    ref_table="process_seen",
                    ref_key=f"{p.pid}|{p.name}",
                ))

        if self._known is None:
            # Very first poll after app start: one summary event instead of
            # 300 individual 'first seen' rows for processes already running.
            new_events = [
                TimelineEvent(
                    ts=now,
                    kind="process_first_seen",
                    title=f"{len(infos)} processes already running at app start",
                    details="Individual first-seen tracking begins now.",
                )
            ]
        else:
            new_events = new_events[:50]  # cap bursts (e.g. a build spawning 200 procs)

        try:
            self._proc_repo.upsert_many(rows)
        except Exception:  # noqa: BLE001 — history must never break live collection
            log.exception("Failed to persist process history")

        self._known = current
        return new_events
