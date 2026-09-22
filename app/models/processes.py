"""Process-related models.

ProcessInfo is one row of the live process table. Fields that Windows refuses
to expose (protected system processes) are None — the UI renders those as
"Permission required" rather than pretending they are zero.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    ppid: int
    name: str
    user: str                    # '' when unreadable
    cpu_percent: float | None    # None = unreadable this poll
    mem_mb: float | None         # None = unreadable
    create_time: float           # unix timestamp; 0 = unknown
    exe_path: str                # '' when unreadable
    cmdline: str                 # already redacted; '' when unreadable
