"""BaseCollector — the plugin-style base class for every collector.

``run()`` wraps the subclass ``collect()`` with timing, error handling, and an
audit record in ``collection_runs``. One failing collector never crashes the
app: the caller receives a CollectorResult with status=error and the reason.
"""
from __future__ import annotations

import logging
import time

from ..database.repositories import CollectionRunRepository
from ..models.metrics import CollectorMeta, CollectorResult, CollectorStatus

log = logging.getLogger(__name__)


class BaseCollector:
    """Subclass and implement ``collect()``; ``run()`` handles the lifecycle.

    Args:
        run_repo: audit repository; pass ``None`` in unit tests.
        name:     collector name; defaults to the class name.
    """

    #: UI label for the health strip
    label: str = "Collector"

    def __collect_repo(self) -> CollectionRunRepository:
        return self._run_repo

    def __init__(self, run_repo: CollectionRunRepository | None = None) -> None:
        self._run_repo = run_repo or CollectionRunRepository()

    def collect(self) -> CollectorResult:
        """Override: gather real data and return a CollectorResult."""
        raise NotImplementedError

    @property
    def name(self) -> str:
        return type(self).__name__

    def run(self) -> CollectorResult:
        started = time.time()
        try:
            result = self.collect()
        except PermissionError as exc:
            result = CollectorResult(
                status=CollectorStatus.PERMISSION_DENIED, detail=str(exc), meta=self._meta()
            )
        except NotImplementedError:
            raise
        except Exception as exc:  # noqa: BLE001 — a collector must never crash the app
            log.exception("Collector %s failed", self.name)
            result = CollectorResult(status=CollectorStatus.ERROR, detail=str(exc), meta=self._meta())
        duration_ms = (time.time() - started) * 1000.0
        try:
            self._run_repo.record(
                collector=self.name, status=result.status.value,
                detail=result.detail[:500], started_at=started, duration_ms=duration_ms,
            )
        except Exception:  # noqa: BLE001 — audit failures must not break collection
            log.exception("Failed to record collection run for %s", self.name)
        return result

    def _meta(self, source: str = "", method: str = "") -> CollectorMeta:
        return CollectorMeta(collector=self.name, source=source, method=method)
