"""GpuCollector — GPU name/utilization when a readable source exists.

Phase 1 tries NVIDIA's nvidia-smi if present. On machines without it, the
collector reports UNSUPPORTED — which the UI renders as 'Unavailable', not as
an error. Later phases can extend this to other vendors.
"""
from __future__ import annotations

import logging
import shutil
import subprocess  # noqa: S404 - only used with a fixed argument list below
import time

from ..models.metrics import CollectorResult, CollectorStatus
from .base import BaseCollector

log = logging.getLogger(__name__)


class GpuCollector(BaseCollector):
    label = "GPU"

    def collect(self) -> CollectorResult:
        smi = shutil.which("nvidia-smi")
        if smi is None:
            return CollectorResult(
                status=CollectorStatus.UNSUPPORTED,
                detail="No NVIDIA GPU tool (nvidia-smi) found; GPU telemetry is Unavailable.",
                meta=self._meta(
                    source="nvidia-smi (NVIDIA driver tool)",
                    method=(
                        "Looks for nvidia-smi.exe on PATH and, if present, runs it with a "
                        "fixed argument list to query GPU name and utilization. No other "
                        "GPU vendor reporting is implemented yet."
                    ),
                ),
            )
        # nvidia-smi occasionally blocks for many seconds while the driver is
        # busy (e.g. after a game or sleep/resume). Give it a generous timeout
        # and one retry before reporting PARTIAL — that keeps a transient hang
        # from flooding the collector health strip with errors.
        proc = None
        for attempt in (1, 2):
            try:
                # Fixed argument list — never a shell string (injection-safe).
                proc = subprocess.run(
                    [smi, "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=15, shell=False, check=True,
                )
                break
            except subprocess.TimeoutExpired:
                if attempt == 1:
                    time.sleep(1.0)
                    continue
                return CollectorResult(
                    status=CollectorStatus.PARTIAL,
                    detail="nvidia-smi did not answer within 15 s; GPU stats temporarily unavailable.",
                    meta=self._meta(source="nvidia-smi",
                                    method="Ran nvidia-smi twice; it stayed busy both times."),
                )
            except (subprocess.SubprocessError, OSError) as exc:
                return CollectorResult(
                    status=CollectorStatus.ERROR, detail=str(exc),
                    meta=self._meta(source="nvidia-smi", method="Ran nvidia-smi; it failed."),
                )
        if proc is None:
            return CollectorResult(
                status=CollectorStatus.PARTIAL,
                detail="nvidia-smi did not answer; GPU stats temporarily unavailable.",
                meta=self._meta(source="nvidia-smi", method="No response from nvidia-smi."),
            )
        line = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            return CollectorResult(
                status=CollectorStatus.PARTIAL, detail="Unexpected nvidia-smi output.",
                meta=self._meta(source="nvidia-smi", method="Ran nvidia-smi; output not parsed."),
            )
        data = {
            "name": parts[0],
            "utilization_percent": float(parts[1]) if parts[1] else None,
            "memory_used_mb": float(parts[2]) if parts[2] else None,
            "memory_total_mb": float(parts[3]) if parts[3] else None,
        }
        return CollectorResult(
            status=CollectorStatus.SUCCESS,
            data=data,
            meta=self._meta(
                source="nvidia-smi (NVIDIA driver tool)",
                method=(
                    "Runs nvidia-smi --query-gpu=name,utilization.gpu,memory.used,"
                    "memory.total --format=csv,noheader,nounits with a fixed argument "
                    "list (no shell) and parses the CSV row. Read-only; no admin rights."
                ),
            ),
        )
