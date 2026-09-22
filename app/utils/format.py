"""Formatting helpers: one place so numbers look identical everywhere."""
from __future__ import annotations

import datetime as dt

TIME_FMT = "%H:%M:%S"


def fmt_bytes_per_sec(mb_s: float) -> str:
    if mb_s >= 1024:
        return f"{mb_s / 1024:.1f} GB/s"
    if mb_s >= 1:
        return f"{mb_s:.1f} MB/s"
    if mb_s >= 0.001:
        return f"{mb_s * 1000:.0f} KB/s"
    return "0 B/s"


def fmt_gb(value: float, decimals: int = 1) -> str:
    if value >= 1024:
        return f"{value / 1024:.{decimals}f} TB"
    return f"{value:.{decimals}f} GB"


def fmt_percent(value: float) -> str:
    return f"{value:.0f}%"


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, _ = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def fmt_time(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime(TIME_FMT)


def fmt_datetime(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
