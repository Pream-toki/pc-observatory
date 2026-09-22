"""Repositories: the only code that speaks SQL for its table.

Services and UI never write queries themselves — they call repositories.
This keeps the schema in one place and makes the storage layer testable.
"""
from __future__ import annotations

import logging
import time
from typing import Iterable, Sequence

from ..models.metrics import MetricSample, SystemInfo
from .connection import get_connection

log = logging.getLogger(__name__)


class MetricRepository:
    """Persists downsampled metric samples and serves chart windows."""

    def insert_sample(self, s: MetricSample) -> None:
        get_connection().execute(
            "INSERT INTO metric_samples (ts, cpu_percent, ram_used_gb, ram_percent,"
            " disk_read_mb_s, disk_write_mb_s, net_up_mb_s, net_down_mb_s,"
            " process_count, listening_ports) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                s.ts, s.cpu_percent, s.ram_used_gb, s.ram_percent,
                s.disk_read_mb_s, s.disk_write_mb_s, s.net_up_mb_s, s.net_down_mb_s,
                s.process_count, s.listening_ports,
            ),
        )
        get_connection().commit()

    def samples_since(self, since_ts: float) -> list[MetricSample]:
        rows = get_connection().execute(
            "SELECT * FROM metric_samples WHERE ts >= ? ORDER BY ts", (since_ts,)
        ).fetchall()
        return [
            MetricSample(
                ts=r["ts"], cpu_percent=r["cpu_percent"], ram_used_gb=r["ram_used_gb"],
                ram_percent=r["ram_percent"], disk_read_mb_s=r["disk_read_mb_s"],
                disk_write_mb_s=r["disk_write_mb_s"], net_up_mb_s=r["net_up_mb_s"],
                net_down_mb_s=r["net_down_mb_s"], process_count=r["process_count"],
                listening_ports=r["listening_ports"],
            )
            for r in rows
        ]

    def count(self) -> int:
        return int(get_connection().execute("SELECT COUNT(*) FROM metric_samples").fetchone()[0])

    def delete_before(self, ts: float) -> int:
        cur = get_connection().execute("DELETE FROM metric_samples WHERE ts < ?", (ts,))
        get_connection().commit()
        if cur.rowcount:
            log.debug("Retention: removed %d metric samples", cur.rowcount)
        return cur.rowcount


class SystemInfoRepository:
    """Stores the single latest SystemInfo row (id = 1)."""

    def upsert(self, info: SystemInfo) -> None:
        get_connection().execute(
            "INSERT INTO system_info (id, hostname, os_name, os_version, os_build,"
            " architecture, cpu_model, cpu_cores_logical, cpu_cores_physical,"
            " ram_total_gb, boot_time, current_user, collected_at)"
            " VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " hostname=excluded.hostname, os_name=excluded.os_name,"
            " os_version=excluded.os_version, os_build=excluded.os_build,"
            " architecture=excluded.architecture, cpu_model=excluded.cpu_model,"
            " cpu_cores_logical=excluded.cpu_cores_logical,"
            " cpu_cores_physical=excluded.cpu_cores_physical,"
            " ram_total_gb=excluded.ram_total_gb, boot_time=excluded.boot_time,"
            " current_user=excluded.current_user, collected_at=excluded.collected_at",
            (
                info.hostname, info.os_name, info.os_version, info.os_build,
                info.architecture, info.cpu_model, info.cpu_cores_logical,
                info.cpu_cores_physical, info.ram_total_gb, info.boot_time,
                info.current_user, time.time(),
            ),
        )
        get_connection().commit()

    def latest(self) -> SystemInfo | None:
        row = get_connection().execute("SELECT * FROM system_info WHERE id = 1").fetchone()
        if row is None:
            return None
        return SystemInfo(
            hostname=row["hostname"], os_name=row["os_name"], os_version=row["os_version"],
            os_build=row["os_build"], architecture=row["architecture"],
            cpu_model=row["cpu_model"], cpu_cores_logical=row["cpu_cores_logical"],
            cpu_cores_physical=row["cpu_cores_physical"], ram_total_gb=row["ram_total_gb"],
            boot_time=row["boot_time"], current_user=row["current_user"],
        )


class CollectionRunRepository:
    """Audit trail of every collector run — feeds the health strip and 'How discovered?'."""

    def record(self, collector: str, status: str, detail: str,
               started_at: float, duration_ms: float) -> None:
        get_connection().execute(
            "INSERT INTO collection_runs (collector, status, detail, started_at, duration_ms)"
            " VALUES (?,?,?,?,?)",
            (collector, status, detail, started_at, duration_ms),
        )
        get_connection().commit()

    def latest_per_collector(self) -> dict[str, tuple[str, str, float]]:
        """collector -> (status, detail, started_at) of its most recent run."""
        rows = get_connection().execute(
            "SELECT collector, status, detail, started_at FROM collection_runs cr"
            " WHERE started_at = (SELECT MAX(started_at) FROM collection_runs c2"
            "                      WHERE c2.collector = cr.collector)"
        ).fetchall()
        return {r["collector"]: (r["status"], r["detail"], r["started_at"]) for r in rows}

    def count(self) -> int:
        return int(get_connection().execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0])

    def delete_before(self, ts: float) -> int:
        cur = get_connection().execute("DELETE FROM collection_runs WHERE started_at < ?", (ts,))
        get_connection().commit()
        return cur.rowcount
