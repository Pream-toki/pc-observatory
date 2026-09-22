"""Tests for formatting helpers — edge cases included."""
from __future__ import annotations

from app.utils.format import (
    fmt_bytes_per_sec,
    fmt_datetime,
    fmt_duration,
    fmt_gb,
    fmt_percent,
)


def test_bytes_per_sec_bands():
    assert fmt_bytes_per_sec(0.0) == "0 B/s"
    assert fmt_bytes_per_sec(0.5) == "500 KB/s"
    assert fmt_bytes_per_sec(2.0) == "2.0 MB/s"
    assert fmt_bytes_per_sec(2048.0) == "2.0 GB/s"


def test_gb_to_tb():
    assert fmt_gb(1536.0) == "1.5 TB"
    assert fmt_gb(512.0) == "512.0 GB"


def test_duration_days():
    assert fmt_duration(90061) == "1d 1h 1m"
    assert fmt_duration(3720) == "1h 2m"
    assert fmt_duration(120) == "2m"


def test_percent_and_datetime():
    assert fmt_percent(42.4) == "42%"
    assert fmt_datetime(0).startswith("1970-01-01")  # unix epoch, UTC-local alignment
