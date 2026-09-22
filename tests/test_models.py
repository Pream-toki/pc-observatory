"""Model behavior tests."""
from __future__ import annotations

import time

from app.models.metrics import (
    CollectorMeta,
    CollectorResult,
    CollectorStatus,
    SystemInfo,
)


def test_collector_result_ok_property():
    assert CollectorResult(status=CollectorStatus.SUCCESS).ok
    assert CollectorResult(status=CollectorStatus.PARTIAL).ok
    assert not CollectorResult(status=CollectorStatus.ERROR).ok
    assert not CollectorResult(status=CollectorStatus.PERMISSION_DENIED).ok
    assert not CollectorResult(status=CollectorStatus.UNSUPPORTED).ok


def test_collector_meta_timestamp_defaults_to_now():
    before = time.time()
    meta = CollectorMeta(collector="X", source="s", method="m")
    assert before - 1 <= meta.collected_at <= time.time() + 1


def test_system_info_defaults_are_unavailable():
    info = SystemInfo()
    assert info.hostname == "Unavailable"
    assert info.cpu_model == "Unavailable"
    assert info.boot_time == 0.0


def test_metric_sample_is_immutable():
    sample = CollectorResult(status=CollectorStatus.SUCCESS)  # unrelated sanity
    meta = CollectorMeta(collector="X", source="s", method="m")
    try:
        meta.collector = "Y"  # type: ignore[misc]
        raise AssertionError("CollectorMeta should be frozen")
    except AttributeError:
        pass
    assert sample.status is CollectorStatus.SUCCESS
