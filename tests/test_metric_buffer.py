"""Tests for MetricBuffer: ring behavior, windowing, downsampling."""
from __future__ import annotations

from app.models.metrics import MetricSample
from app.services.metric_buffer import MetricBuffer


def _sample(ts: float) -> MetricSample:
    return MetricSample(
        ts=ts, cpu_percent=1.0, ram_used_gb=1.0, ram_percent=1.0,
        disk_read_mb_s=0.0, disk_write_mb_s=0.0,
        net_up_mb_s=0.0, net_down_mb_s=0.0,
        process_count=1, listening_ports=0,
    )


def test_buffer_keeps_only_recent_samples():
    buf = MetricBuffer(max_seconds=60, persist_every=1000)
    buf.add(_sample(1000.0))
    buf.add(_sample(1070.0))   # evicts the 1000 sample (cutoff 1010)
    buf.add(_sample(1075.0))
    window = buf.window(30, now=1075.0)
    assert [s.ts for s in window] == [1070.0, 1075.0]
    assert buf.latest().ts == 1075.0


def test_downsampling_persists_every_interval():
    buf = MetricBuffer(max_seconds=60, persist_every=10)
    assert buf.add(_sample(1000.0)) is not None    # first always persists
    assert buf.add(_sample(1005.0)) is None        # 5 s < 10 s
    assert buf.add(_sample(1010.0)) is not None    # 10 s >= 10 s
    assert buf.add(_sample(1012.0)) is None


def test_empty_buffer_is_safe():
    buf = MetricBuffer(max_seconds=60, persist_every=10)
    assert buf.latest() is None
    assert buf.window(30, now=1000.0) == []
