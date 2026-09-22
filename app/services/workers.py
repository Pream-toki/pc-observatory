"""Background workers — QThreads that run collectors on a timer.

The UI thread is never blocked: workers emit Qt signals with fresh data and
the dashboard updates in its own thread. Collectors themselves are plain
Python (no Qt), so they stay testable without a QApplication.
"""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, QThread, Signal

from ..collectors.base import BaseCollector
from ..database.connection import close_thread_connection

log = logging.getLogger(__name__)


class _CollectorWorker(QObject):
    """Runs one collector on repeat inside its QThread."""

    resultReady = Signal(object)  # CollectorResult (object because models are not Qt types)

    def __init__(self, collector: BaseCollector, interval_s: float,
                 initial_delay_s: float = 0.0) -> None:
        super().__init__()
        self._collector = collector
        self._interval_s = max(0.5, interval_s)
        self._initial_delay_s = max(0.0, initial_delay_s)
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:  # executed inside the QThread
        # Heavy collectors take an initial delay so the window appears fast;
        # sleep in short slices so stop() is honored during the delay too.
        remaining = self._initial_delay_s
        while self._running and remaining > 0:
            step = min(0.25, remaining)
            time.sleep(step)
            remaining -= step
        # First run immediately after the delay so the UI fills without
        # waiting a full interval.
        while self._running:
            started = time.time()
            try:
                self.resultReady.emit(self._collector.run())
            except Exception:  # noqa: BLE001 — belt & braces; run() already catches
                log.exception("Worker loop error in %s", self._collector.name)
            # Sleep in short slices so stop() is honored quickly.
            elapsed = time.time() - started
            remaining = self._interval_s - elapsed
            while self._running and remaining > 0:
                step = min(0.25, remaining)
                time.sleep(step)
                remaining -= step
        close_thread_connection()


class CollectorScheduler(QObject):
    """Owns a thread per collector; UI connects to each collector's resultReady."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._threads: list[QThread] = []
        self._workers: list[_CollectorWorker] = []

    def add_collector(self, collector: BaseCollector, interval_s: float,
                      initial_delay_s: float = 0.0) -> _CollectorWorker:
        thread = QThread(self)
        worker = _CollectorWorker(collector, interval_s, initial_delay_s)
        worker.moveToThread(thread)
        worker.resultReady.connect(self._on_result)
        thread.started.connect(worker.run)
        self._threads.append(thread)
        self._workers.append(worker)
        thread.start()
        return worker

    def _on_result(self, result: object) -> None:
        status = getattr(result, "status", None)
        if status is not None and getattr(status, "value", "") in ("error", "permission_denied"):
            log.warning("Collector reported %s", status.value)

    def shutdown(self) -> None:
        for worker in self._workers:
            worker.stop()
        for thread in self._threads:
            thread.quit()
        for thread in self._threads:
            thread.wait(3000)
        self._threads.clear()
        self._workers.clear()
