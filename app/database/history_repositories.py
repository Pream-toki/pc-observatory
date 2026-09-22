"""Repositories for process history and the PC timeline.

ProcessRepository answers "what was running on this PC and when did I first
see it?" — every process gets first_seen / last_seen rows keyed by
(pid, name, exe_path), so a reboot creates fresh history per boot instead of
one stale entry.

TimelineRepository stores the chronological event feed (boot, process
first-seen, collector milestones — more kinds arrive in later phases).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .connection import get_connection

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessSeen:
    pid: int
    name: str
    exe_path: str
    first_seen: float
    last_seen: float
    last_cpu: float | None
    last_mem_mb: float | None


class ProcessRepository:
    """First-seen / last-seen history for every process identity."""

    def upsert_many(self, rows: list[ProcessSeen]) -> None:
        if not rows:
            return
        conn = get_connection()
        conn.executemany(
            "INSERT INTO process_seen (pid, name, exe_path, first_seen, last_seen,"
            " last_cpu, last_mem_mb) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(pid, name, exe_path) DO UPDATE SET"
            " last_seen=excluded.last_seen, last_cpu=excluded.last_cpu,"
            " last_mem_mb=excluded.last_mem_mb",
            [
                (r.pid, r.name, r.exe_path, r.first_seen, r.last_seen,
                 r.last_cpu, r.last_mem_mb)
                for r in rows
            ],
        )
        conn.commit()

    def recent(self, limit: int = 300) -> list[ProcessSeen]:
        rows = get_connection().execute(
            "SELECT * FROM process_seen ORDER BY last_seen DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            ProcessSeen(
                pid=r["pid"], name=r["name"], exe_path=r["exe_path"],
                first_seen=r["first_seen"], last_seen=r["last_seen"],
                last_cpu=r["last_cpu"], last_mem_mb=r["last_mem_mb"],
            )
            for r in rows
        ]

    def first_seen(self, name: str, exe_path: str, pid: int) -> float | None:
        row = get_connection().execute(
            "SELECT first_seen FROM process_seen WHERE pid=? AND name=? AND exe_path=?",
            (pid, name, exe_path),
        ).fetchone()
        return float(row[0]) if row else None

    def delete_before(self, ts: float) -> int:
        cur = get_connection().execute("DELETE FROM process_seen WHERE last_seen < ?", (ts,))
        get_connection().commit()
        return cur.rowcount


@dataclass(frozen=True)
class TimelineEvent:
    ts: float
    kind: str            # 'boot' | 'process_first_seen' | 'collector' | ...
    title: str
    details: str = ""
    ref_table: str = ""
    ref_key: str = ""


class TimelineRepository:
    """Append-mostly feed of chronological events."""

    def add(self, event: TimelineEvent) -> None:
        get_connection().execute(
            "INSERT INTO timeline_events (ts, kind, title, details, ref_table, ref_key)"
            " VALUES (?,?,?,?,?,?)",
            (event.ts, event.kind, event.title, event.details,
             event.ref_table, event.ref_key),
        )
        get_connection().commit()

    def add_many(self, events: list[TimelineEvent]) -> None:
        if not events:
            return
        conn = get_connection()
        conn.executemany(
            "INSERT INTO timeline_events (ts, kind, title, details, ref_table, ref_key)"
            " VALUES (?,?,?,?,?,?)",
            [(e.ts, e.kind, e.title, e.details, e.ref_table, e.ref_key) for e in events],
        )
        conn.commit()

    def latest(self, limit: int = 400, kind: str | None = None,
               since_ts: float | None = None) -> list[TimelineEvent]:
        sql = "SELECT * FROM timeline_events WHERE 1=1"
        params: list[object] = []
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if since_ts is not None:
            sql += " AND ts >= ?"
            params.append(since_ts)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        rows = get_connection().execute(sql, params).fetchall()
        return [
            TimelineEvent(
                ts=r["ts"], kind=r["kind"], title=r["title"], details=r["details"],
                ref_table=r["ref_table"], ref_key=r["ref_key"],
            )
            for r in rows
        ]

    def count(self) -> int:
        return int(get_connection().execute("SELECT COUNT(*) FROM timeline_events").fetchone()[0])

    def delete_before(self, ts: float) -> int:
        cur = get_connection().execute("DELETE FROM timeline_events WHERE ts < ?", (ts,))
        get_connection().commit()
        return cur.rowcount
