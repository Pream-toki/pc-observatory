"""Tests for the database layer: migrations, repositories, retention."""
from __future__ import annotations

import time

from app.database.migrations import MIGRATIONS, migrate

_LATEST = max(v for v, _sql in MIGRATIONS)
from app.database.repositories import (
    CollectionRunRepository,
    MetricRepository,
    SystemInfoRepository,
)
from app.models.metrics import MetricSample, SystemInfo


def _sample(ts: float, cpu: float = 10.0) -> MetricSample:
    return MetricSample(
        ts=ts, cpu_percent=cpu, ram_used_gb=8.0, ram_percent=50.0,
        disk_read_mb_s=1.0, disk_write_mb_s=2.0,
        net_up_mb_s=0.1, net_down_mb_s=1.1,
        process_count=200, listening_ports=25,
    )


def test_migrate_creates_schema(tmp_db):
    version = migrate(tmp_db)
    assert version == _LATEST
    tables = {
        row[0] for row in tmp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"schema_migrations", "system_info", "metric_samples",
            "collection_runs", "process_seen", "timeline_events"} <= tables


def test_migrate_is_idempotent(tmp_db):
    assert migrate(tmp_db) == _LATEST
    assert migrate(tmp_db) == _LATEST  # running twice must not fail or duplicate


def test_metric_repository_round_trip(tmp_db):
    repo = MetricRepository()
    repo.insert_sample(_sample(1000.0))
    repo.insert_sample(_sample(1010.0, cpu=42.0))
    rows = repo.samples_since(1005.0)
    assert len(rows) == 1
    assert rows[0].ts == 1010.0
    assert rows[0].cpu_percent == 42.0
    assert repo.count() == 2


def test_retention_deletes_only_old_rows(tmp_db):
    repo = MetricRepository()
    repo.insert_sample(_sample(time.time() - 10 * 86400))  # 10 days old
    repo.insert_sample(_sample(time.time()))
    removed = repo.delete_before(time.time() - 86400)      # older than 1 day
    assert removed == 1
    assert repo.count() == 1


def test_system_info_upsert_single_row(tmp_db):
    repo = SystemInfoRepository()
    repo.upsert(SystemInfo(hostname="PC-1", ram_total_gb=16.0))
    repo.upsert(SystemInfo(hostname="PC-1", ram_total_gb=32.0))
    info = repo.latest()
    assert info is not None
    assert info.ram_total_gb == 32.0
    count = tmp_db.execute("SELECT COUNT(*) FROM system_info").fetchone()[0]
    assert count == 1


def test_collection_runs_latest_per_collector(tmp_db):
    repo = CollectionRunRepository()
    repo.record("A", "error", "old failure", started_at=1.0, duration_ms=5)
    repo.record("A", "success", "", started_at=2.0, duration_ms=5)
    repo.record("B", "partial", "some fields", started_at=3.0, duration_ms=5)
    health = repo.latest_per_collector()
    assert health["A"][0] == "success"          # newest run wins
    assert health["B"][0] == "partial"
    assert health["B"][1] == "some fields"
