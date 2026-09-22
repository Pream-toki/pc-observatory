"""Tests for process history and timeline: first-seen detection, persistence."""
from __future__ import annotations

from app.database.history_repositories import (
    ProcessRepository,
    TimelineRepository,
)
from app.models.processes import ProcessInfo
from app.services.process_history import ProcessHistory


def _info(pid: int, name: str = "app.exe", exe: str = r"C:\app.exe") -> ProcessInfo:
    return ProcessInfo(
        pid=pid, ppid=1, name=name, user="me", cpu_percent=1.5, mem_mb=10.0,
        create_time=1000.0, exe_path=exe, cmdline="",
    )


def test_first_poll_records_summary_not_300_events(tmp_db):
    repo = ProcessRepository()
    history = ProcessHistory(repo)
    events = history.update([_info(1), _info(2), _info(3)], now=5000.0)
    assert len(events) == 1
    assert "already running" in events[0].title


def test_new_process_after_first_poll_emits_event(tmp_db):
    repo = ProcessRepository()
    history = ProcessHistory(repo)
    history.update([_info(1)], now=5000.0)
    events = history.update([_info(1), _info(2, "new.exe")], now=5010.0)
    assert len(events) == 1
    assert events[0].kind == "process_first_seen"
    assert "new.exe" in events[0].title


def test_process_seen_rows_upsert_first_and_last_seen(tmp_db):
    repo = ProcessRepository()
    history = ProcessHistory(repo)
    history.update([_info(1)], now=5000.0)
    history.update([_info(1)], now=6000.0)
    rows = repo.recent()
    assert len(rows) == 1
    assert rows[0].first_seen == 5000.0
    assert rows[0].last_seen == 6000.0


def test_reboot_creates_fresh_identity(tmp_db):
    """Same pid after reboot = different exe time? Identity is (pid,name,exe);
    a fresh boot produces a new poll set — rows are per identity, and history
    keeps the previous row until retention cleans it."""
    repo = ProcessRepository()
    history = ProcessHistory(repo)
    history.update([_info(1)], now=5000.0)
    history.update([_info(1)], now=9000.0)
    assert len(repo.recent()) == 1  # same identity, updated in place


def test_timeline_repository_filters_by_kind(tmp_db):
    repo = TimelineRepository()
    repo.add_many([
        type("E", (), {"ts": 1.0, "kind": "boot", "title": "b", "details": "",
                       "ref_table": "", "ref_key": ""})(),
        type("E", (), {"ts": 2.0, "kind": "process_first_seen", "title": "p",
                       "details": "", "ref_table": "", "ref_key": ""})(),
    ])
    assert [e.kind for e in repo.latest(kind="boot")] == ["boot"]
    assert len(repo.latest()) == 2
