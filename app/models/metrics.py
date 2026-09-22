"""Data models shared across the application.

Collectors produce these models; services persist and serve them; the UI
displays them. Keeping them in one place keeps the layers decoupled.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CollectorStatus(str, Enum):
    """Outcome of a collector run. See spec section 45."""

    SUCCESS = "success"
    PARTIAL = "partial"                # some fields collected, some unavailable
    PERMISSION_DENIED = "permission_denied"
    UNSUPPORTED = "unsupported"        # e.g. no NVIDIA GPU on this machine
    ERROR = "error"


@dataclass(frozen=True)
class CollectorMeta:
    """Provenance of a piece of data — powers the 'How was this discovered?' dialog."""

    collector: str                     # e.g. "MetricsCollector"
    source: str                        # e.g. "psutil.cpu_percent"
    method: str                        # human-readable description of how it works
    collected_at: float = field(default_factory=time.time)  # unix seconds


@dataclass(frozen=True)
class CollectorResult:
    """What every collector returns: a status, the data, and full provenance."""

    status: CollectorStatus
    data: Any = None
    meta: CollectorMeta | None = None
    detail: str = ""                   # error text / 'Unavailable' reason

    @property
    def ok(self) -> bool:
        return self.status in (CollectorStatus.SUCCESS, CollectorStatus.PARTIAL)


@dataclass(frozen=True)
class MetricSample:
    """One instantaneous system metrics reading. Thread-safe by immutability."""

    ts: float                          # unix timestamp (seconds)
    cpu_percent: float
    ram_used_gb: float
    ram_percent: float
    disk_read_mb_s: float
    disk_write_mb_s: float
    net_up_mb_s: float
    net_down_mb_s: float
    process_count: int
    listening_ports: int


@dataclass(frozen=True)
class SystemInfo:
    """Slow-changing machine facts, collected once at startup (and refreshed rarely)."""

    hostname: str = "Unavailable"
    os_name: str = "Unavailable"
    os_version: str = "Unavailable"
    os_build: str = "Unavailable"
    architecture: str = "Unavailable"
    cpu_model: str = "Unavailable"
    cpu_cores_logical: int = 0
    cpu_cores_physical: int = 0
    ram_total_gb: float = 0.0
    boot_time: float = 0.0            # unix timestamp; 0 = unknown
    current_user: str = "Unavailable"
