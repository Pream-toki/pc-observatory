"""MetricsCollector — the fast live sample: CPU, RAM, disk, network, counts.

Note on psutil call order: disk_io_counters / net_io_counters rate math needs
two reads spaced by an interval. We reuse the *previous* sample's counters
(stored on the instance) instead of sleeping inside the collector, so a
2-second collection cycle never blocks anything.
"""
from __future__ import annotations

import logging
import time

import psutil

from ..models.metrics import CollectorResult, CollectorStatus, MetricSample
from .base import BaseCollector

log = logging.getLogger(__name__)

_BYTES_PER_MB = 1024.0 * 1024.0


class MetricsCollector(BaseCollector):
    """One call = one MetricSample. First call after construction returns zero rates."""

    label = "Live Metrics"

    def __init__(self, run_repo=None) -> None:
        super().__init__(run_repo)
        self._last_disk: tuple[int, int, float] | None = None   # (read, write, ts)
        self._last_net: tuple[int, int, float] | None = None    # (sent, recv, ts)

    def collect(self) -> CollectorResult:
        now = time.time()
        cpu_percent = psutil.cpu_percent(interval=None)  # non-blocking since last call
        vm = psutil.virtual_memory()

        disk = psutil.disk_io_counters()
        net = psutil.net_io_counters()

        read_mb_s = write_mb_s = up_mb_s = down_mb_s = 0.0
        if disk is not None:
            if self._last_disk is not None:
                dt = now - self._last_disk[2]
                if dt > 0:
                    read_mb_s = max(0.0, (disk.read_bytes - self._last_disk[0]) / dt / _BYTES_PER_MB)
                    write_mb_s = max(0.0, (disk.write_bytes - self._last_disk[1]) / dt / _BYTES_PER_MB)
            self._last_disk = (disk.read_bytes, disk.write_bytes, now)
        if net is not None:
            if self._last_net is not None:
                dt = now - self._last_net[2]
                if dt > 0:
                    up_mb_s = max(0.0, (net.bytes_sent - self._last_net[0]) / dt / _BYTES_PER_MB)
                    down_mb_s = max(0.0, (net.bytes_recv - self._last_net[1]) / dt / _BYTES_PER_MB)
            self._last_net = (net.bytes_sent, net.bytes_recv, now)

        connections = psutil.net_connections(kind="inet")
        listening = sum(1 for c in connections if c.status == psutil.CONN_LISTEN)

        sample = MetricSample(
            ts=now,
            cpu_percent=cpu_percent,
            ram_used_gb=round((vm.total - vm.available) / (1024 ** 3), 3),
            ram_percent=vm.percent,
            disk_read_mb_s=round(read_mb_s, 3),
            disk_write_mb_s=round(write_mb_s, 3),
            net_up_mb_s=round(up_mb_s, 3),
            net_down_mb_s=round(down_mb_s, 3),
            process_count=len(psutil.pids()),
            listening_ports=listening,
        )
        return CollectorResult(
            status=CollectorStatus.SUCCESS,
            data=sample,
            meta=self._meta(
                source="psutil (cpu_percent, virtual_memory, disk_io_counters, net_io_counters, net_connections)",
                method=(
                    "Reads CPU utilization, memory, disk I/O counters, network I/O counters "
                    "and the process/listening-port counts through the psutil library, which "
                    "wraps the Windows performance APIs. Disk/network speeds are the change "
                    "between the previous sample and this one. Read-only; no admin rights."
                ),
            ),
        )
