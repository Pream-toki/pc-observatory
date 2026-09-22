"""ProcessCollector — a live snapshot of every running process.

Design notes:
- A per-pid cache of psutil.Process objects is kept between polls so
  cpu_percent() returns the real usage *since the previous poll* (the first
  poll of a brand-new pid honestly reports 0.0 — one sample is not enough to
  compute a rate).
- Protected system processes refuse some reads. Those fields become None/''
  and the UI shows them as 'Permission required' — never as invented values.
- Command lines pass through utils.redact before leaving this collector, so
  secrets on a command line never reach the UI or the database.
"""
from __future__ import annotations

import logging
import time

import psutil

from ..models.processes import ProcessInfo
from ..models.metrics import CollectorResult, CollectorStatus
from ..utils.redact import redact_cmdline
from .base import BaseCollector

log = logging.getLogger(__name__)


class ProcessCollector(BaseCollector):
    label = "Processes"

    def __init__(self, run_repo=None) -> None:
        super().__init__(run_repo)
        self._cache: dict[int, psutil.Process] = {}
        # exe() and cmdline() cannot change while a pid is alive — cache them
        # per pid so each poll only pays for NEW processes. This roughly halves
        # the per-poll work (the biggest UI-thread-adjacent cost).
        self._static: dict[int, tuple[str, str]] = {}  # pid -> (exe, cmdline)

    def collect(self) -> CollectorResult:
        now = time.time()
        infos: list[ProcessInfo] = []
        seen_pids: set[int] = set()

        for proc in psutil.process_iter(["pid", "ppid", "name", "username", "create_time"]):
            d = proc.info
            pid = d["pid"]
            seen_pids.add(pid)
            cached = self._cache.get(pid)
            if cached is None:
                cached = proc
                self._cache[pid] = proc

            cpu: float | None
            try:
                cpu = float(cached.cpu_percent(None))  # None-interval: since last poll
            except psutil.Error:
                cpu = None
            try:
                mem_mb: float | None = cached.memory_info().rss / (1024 * 1024)
            except psutil.Error:
                mem_mb = None
            static = self._static.get(pid)
            if static is None:
                try:
                    exe_path = cached.exe() or ""
                except psutil.Error:
                    exe_path = ""
                try:
                    cmdline = redact_cmdline(list(cached.cmdline() or []))
                except psutil.Error:
                    cmdline = ""
                self._static[pid] = (exe_path, cmdline)
            else:
                exe_path, cmdline = static

            infos.append(
                ProcessInfo(
                    pid=pid,
                    ppid=int(d.get("ppid") or 0),
                    name=d.get("name") or f"pid {pid}",
                    user=d.get("username") or "",
                    cpu_percent=cpu,
                    mem_mb=round(mem_mb, 1) if mem_mb is not None else None,
                    create_time=float(d.get("create_time") or 0.0),
                    exe_path=exe_path,
                    cmdline=cmdline,
                )
            )

        # Forget processes that exited so neither cache can grow forever.
        self._cache = {pid: proc for pid, proc in self._cache.items() if pid in seen_pids}
        self._static = {pid: val for pid, val in self._static.items() if pid in seen_pids}

        infos.sort(key=lambda p: (p.cpu_percent if p.cpu_percent is not None else -1.0),
                   reverse=True)
        return CollectorResult(
            status=CollectorStatus.SUCCESS,
            data=infos,
            meta=self._meta(
                source="psutil.process_iter + psutil.Process APIs",
                method=(
                    "Walks the Windows process list through psutil (which wraps the "
                    "Win32 process APIs), then reads CPU (usage since the previous "
                    "poll), memory, executable path and command line per process. "
                    "Protected system processes report 'Permission required' for the "
                    "fields Windows hides. Command lines are scanned and any "
                    "credential-looking value is replaced with "
                    "'[SENSITIVE VALUE HIDDEN]' before display or storage. "
                    "Read-only; no admin rights."
                ),
            ),
        )
