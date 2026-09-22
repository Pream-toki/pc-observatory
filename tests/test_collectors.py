"""Collector tests.

Everything is mocked except one read-only SystemCollector smoke test that
touches nothing but harmless API reads. No Windows configuration is modified.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.collectors.gpu as gpu_mod
import app.collectors.metrics as metrics_mod
from app.collectors.base import BaseCollector
from app.collectors.gpu import GpuCollector
from app.collectors.metrics import MetricsCollector
from app.collectors.system import SystemCollector
from app.models.metrics import CollectorStatus


class FailingCollector(BaseCollector):
    """Simulates a collector hitting a permission wall."""

    label = "Failing"

    def collect(self):
        raise PermissionError("Administrator permission is required")


class ExplodingCollector(BaseCollector):
    """Simulates any other unexpected failure."""

    def collect(self):
        raise RuntimeError("boom")


def test_permission_error_maps_to_permission_denied(tmp_db):
    result = FailingCollector().run()
    assert result.status is CollectorStatus.PERMISSION_DENIED
    assert "Administrator" in result.detail


def test_unexpected_error_maps_to_error(tmp_db):
    result = ExplodingCollector().run()
    assert result.status is CollectorStatus.ERROR
    assert "boom" in result.detail


def test_run_records_audit_trail(tmp_db):
    from app.database.repositories import CollectionRunRepository

    SystemCollector().run()
    health = CollectionRunRepository().latest_per_collector()
    assert "SystemCollector" in health
    status, detail, started = health["SystemCollector"]
    assert status == CollectorStatus.SUCCESS.value
    assert started > 0


def test_metrics_collector_rate_math(tmp_db, monkeypatch):
    """Second sample's speeds must equal counter deltas divided by elapsed time."""
    col = MetricsCollector()
    state = {"disk": 0, "net": 0, "collect": 0}

    disk = [
        SimpleNamespace(read_bytes=1_000_000, write_bytes=2_000_000),
        SimpleNamespace(read_bytes=3_000_000, write_bytes=4_000_000),
    ]
    net = [
        SimpleNamespace(bytes_sent=10_000_000, bytes_recv=20_000_000),
        SimpleNamespace(bytes_sent=16_000_000, bytes_recv=50_000_000),
    ]
    vm = SimpleNamespace(total=16 * 1024 ** 3, available=8 * 1024 ** 3, percent=50.0)
    conns = [SimpleNamespace(status="LISTEN"),
             SimpleNamespace(status="ESTABLISHED"),
             SimpleNamespace(status="LISTEN")]

    def fake_disk():
        result = disk[min(state["disk"], 1)]
        state["disk"] += 1
        return result

    def fake_net():
        result = net[min(state["net"], 1)]
        state["net"] += 1
        return result

    def fake_time():
        return 1000.0 + 2.0 * state["collect"]

    monkeypatch.setattr(metrics_mod.psutil, "cpu_percent", lambda interval=None: 33.0)
    monkeypatch.setattr(metrics_mod.psutil, "virtual_memory", lambda: vm)
    monkeypatch.setattr(metrics_mod.psutil, "disk_io_counters", fake_disk)
    monkeypatch.setattr(metrics_mod.psutil, "net_io_counters", fake_net)
    monkeypatch.setattr(metrics_mod.psutil, "net_connections", lambda kind="inet": conns)
    monkeypatch.setattr(metrics_mod.psutil, "pids", lambda: list(range(42)))
    monkeypatch.setattr(metrics_mod.time, "time", fake_time)

    first = col.run()
    state["collect"] += 1
    second = col.run()

    # First run: no previous counters -> zero rates (honest, not invented).
    assert first.data.disk_read_mb_s == 0.0
    assert first.data.listening_ports == 2
    assert first.data.process_count == 42
    assert first.data.cpu_percent == 33.0

    # Second run: 2,000,000 bytes read over 2 s = 0.954 MB/s, etc.
    assert second.data.disk_read_mb_s == pytest.approx(0.954, abs=0.01)
    assert second.data.disk_write_mb_s == pytest.approx(0.954, abs=0.01)
    assert second.data.net_up_mb_s == pytest.approx(2.861, abs=0.01)
    assert second.data.net_down_mb_s == pytest.approx(14.305, abs=0.01)
    assert second.data.ram_used_gb == pytest.approx(8.0, abs=0.01)


def test_gpu_reports_unsupported_without_nvidia(tmp_db, monkeypatch):
    monkeypatch.setattr(gpu_mod.shutil, "which", lambda name: None)
    result = GpuCollector().run()
    assert result.status is CollectorStatus.UNSUPPORTED
    assert "Unavailable" in result.detail or "nvidia" in result.detail.lower()


def test_gpu_parses_nvidia_smi_output(tmp_db, monkeypatch):
    class FakeCompleted:
        stdout = "NVIDIA GeForce RTX 4070, 35, 1024, 12288\n"

    monkeypatch.setattr(gpu_mod.shutil, "which", lambda name: r"C:\fake\nvidia-smi.exe")
    monkeypatch.setattr(gpu_mod.subprocess, "run", lambda *a, **k: FakeCompleted())
    result = GpuCollector().run()
    assert result.status is CollectorStatus.SUCCESS
    assert result.data["name"] == "NVIDIA GeForce RTX 4070"
    assert result.data["utilization_percent"] == 35.0
    assert result.data["memory_total_mb"] == 12288.0


def test_system_collector_real_readonly(tmp_db):
    """Real machine, strictly read-only: no settings or system state touched."""
    result = SystemCollector().run()
    assert result.ok
    info = result.data
    assert info.hostname
    assert info.ram_total_gb > 0
    assert info.boot_time > 0
    assert info.cpu_cores_logical >= 1
    assert info.cpu_model  # 'Unavailable' is acceptable, empty is not
