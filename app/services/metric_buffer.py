"""MetricBuffer — in-memory ring buffer for live charts.

Charts must never wait on the database: every sample is kept in RAM for the
longest chart window (30 minutes). A downsampled copy (one row per
``persist_every`` seconds) is written to SQLite so later phases — History,
Timeline, change detection — have data even after a restart.
"""
from __future__ import annotations

import threading
from collections import deque

from ..models.metrics import MetricSample


class MetricBuffer:
    def __init__(self, max_seconds: float, persist_every: float = 15.0) -> None:
        self._lock = threading.Lock()
        self._samples: deque[MetricSample] = deque()
        self._max_seconds = max_seconds
        self._persist_every = persist_every
        self._last_persisted_ts: float | None = None

    def add(self, sample: MetricSample) -> MetricSample | None:
        """Store a sample. Returns the sample that should be persisted (or None).

        Downsampling rule: persist a sample only if at least ``persist_every``
        seconds have passed since the last persisted one.
        """
        with self._lock:
            self._samples.append(sample)
            cutoff = sample.ts - self._max_seconds
            while self._samples and self._samples[0].ts < cutoff:
                self._samples.popleft()
            if self._last_persisted_ts is None or \
                    sample.ts - self._last_persisted_ts >= self._persist_every:
                self._last_persisted_ts = sample.ts
                return sample
            return None

    def window(self, seconds: float, now: float | None = None) -> list[MetricSample]:
        """Samples from the last ``seconds`` (oldest first). ``now`` is injectable
        for tests; real callers use the wall clock."""
        import time

        cutoff = (now if now is not None else time.time()) - seconds
        with self._lock:
            return [s for s in self._samples if s.ts >= cutoff]

    def latest(self) -> MetricSample | None:
        with self._lock:
            return self._samples[-1] if self._samples else None
