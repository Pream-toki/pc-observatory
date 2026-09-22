"""NetworkCollector — listening ports and the process that owns each (spec §22).

Read-only local observation only: no external scanning, no remote probes.
Owner lookup uses psutil's connection table (same data netstat shows).
"""
from __future__ import annotations

import logging
import socket

import psutil

from ..models.metrics import CollectorResult, CollectorStatus
from .base import BaseCollector

log = logging.getLogger(__name__)


class NetworkCollector(BaseCollector):
    label = "Network"

    def collect(self) -> CollectorResult:
        ports: list[dict] = []
        name_cache: dict[int, tuple[str, str]] = {}

        for conn in psutil.net_connections(kind="inet"):
            if conn.status != psutil.CONN_LISTEN or conn.laddr is None:
                continue
            pid = conn.pid or 0
            if pid not in name_cache:
                try:
                    proc = psutil.Process(pid)
                    name_cache[pid] = (proc.name(), proc.exe() or "")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    name_cache[pid] = ("Permission required", "")
            proc_name, exe_path = name_cache[pid]
            try:
                local_ip = conn.laddr.ip
                # Resolve 0.0.0.0/:: to a friendly label — honest about wildcard.
                if local_ip in ("0.0.0.0", "::"):
                    local_ip = f"{local_ip} (all interfaces)"
            except Exception:  # noqa: BLE001
                local_ip = str(getattr(conn.laddr, "ip", "Unavailable"))
            ports.append({
                "protocol": "TCP" if conn.type == socket.SOCK_STREAM else "UDP",
                "local_ip": local_ip,
                "local_port": int(conn.laddr.port),
                "pid": pid,
                "process_name": proc_name,
                "exe_path": exe_path,
            })

        # One row per (proto, ip, port): dedupe multiple listen sockets.
        deduped = {(p["protocol"], p["local_ip"], p["local_port"]): p for p in ports}
        return CollectorResult(
            status=CollectorStatus.SUCCESS,
            data=list(deduped.values()),
            meta=self._meta(
                source="psutil.net_connections (Windows TCP/IP table)",
                method=(
                    "Reads the operating system's TCP/IP connection table and keeps "
                    "the listening sockets, then resolves the owning process for "
                    "each port from the process table — the same information "
                    "netstat -ano shows, without running any command. Nothing is "
                    "sent to the network; purely local observation. Read-only."
                ),
            ),
        )
