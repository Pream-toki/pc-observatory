"""Repositories for the Automation Monitor: script inventory + run history.

ScriptRepository answers "what automations exist on this PC?" — every
.py/.ps1/.bat script found in the configured project folders, with what
usually triggers it when that link is safely detectable.

ScriptRunRepository answers "what is it doing, and when?" — each detected
execution becomes one row: started, still running or finished, by which
interpreter, with what (redacted) command line.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .connection import get_connection

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScriptRow:
    path: str
    name: str
    kind: str
    size_bytes: int
    modified: float
    project: str
    trigger_hint: str
    first_seen: float
    last_seen: float


@dataclass(frozen=True)
class ScriptRunRow:
    id: int
    script_path: str
    pid: int
    started_at: float
    last_seen: float
    ended_at: float | None
    interpreter: str
    cmdline: str
    trigger: str


class ScriptRepository:
    def upsert_many(self, rows: list[dict]) -> None:
        if not rows:
            return
        conn = get_connection()
        now = time.time()
        # Missing keys default sensibly (e.g. the tracker registers a newly
        # discovered script before the inventory has scanned it).
        conn.executemany(
            "INSERT INTO scripts (path, name, kind, size_bytes, modified, project,"
            " trigger_hint, first_seen, last_seen)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(path) DO UPDATE SET name=excluded.name,"
            " kind=excluded.kind, size_bytes=excluded.size_bytes,"
            " modified=excluded.modified, project=excluded.project,"
            " trigger_hint=excluded.trigger_hint, last_seen=excluded.last_seen",
            [
                (r["path"], r["name"], r.get("kind", "python"),
                 r.get("size_bytes", 0), r.get("modified", 0.0),
                 r.get("project", ""), r.get("trigger_hint", ""),
                 self._first_seen(conn, r["path"]), now)
                for r in rows
            ],
        )
        conn.commit()

    @staticmethod
    def _first_seen(conn, path: str) -> float:
        row = conn.execute("SELECT first_seen FROM scripts WHERE path=?", (path,)).fetchone()
        return float(row[0]) if row else time.time()

    def all(self) -> list[ScriptRow]:
        rows = get_connection().execute(
            "SELECT * FROM scripts ORDER BY name COLLATE NOCASE").fetchall()
        return [ScriptRow(**dict(r)) for r in rows]

    def get(self, path: str) -> ScriptRow | None:
        row = get_connection().execute(
            "SELECT * FROM scripts WHERE path=?", (path,)).fetchone()
        return ScriptRow(**dict(row)) if row else None

    def set_trigger_hint(self, path: str, hint: str) -> None:
        get_connection().execute(
            "UPDATE scripts SET trigger_hint=? WHERE path=?", (hint, path))
        get_connection().commit()


class ScriptRunRepository:
    def open_run(self, script_path: str, pid: int, started_at: float,
                 interpreter: str, cmdline: str, trigger: str) -> int:
        """Insert a run unless this exact (script, pid) is already open."""
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM script_runs WHERE script_path=? AND pid=? AND ended_at IS NULL",
            (script_path, pid)).fetchone()
        if row:
            return int(row[0])
        cur = conn.execute(
            "INSERT INTO script_runs (script_path, pid, started_at, last_seen,"
            " ended_at, interpreter, cmdline, trigger) VALUES (?,?,?,?,NULL,?,?,?)",
            (script_path, pid, started_at, started_at, interpreter, cmdline, trigger))
        conn.commit()
        return int(cur.lastrowid)

    def touch_many(self, keys: list[tuple[str, int]], now: float) -> None:
        """Update last_seen for many open runs in ONE transaction."""
        if not keys:
            return
        conn = get_connection()
        conn.executemany(
            "UPDATE script_runs SET last_seen=? WHERE script_path=? AND pid=?"
            " AND ended_at IS NULL",
            [(now, path, pid) for path, pid in keys])
        conn.commit()

    def touch(self, script_path: str, pid: int, now: float) -> None:
        get_connection().execute(
            "UPDATE script_runs SET last_seen=? WHERE script_path=? AND pid=? AND ended_at IS NULL",
            (now, script_path, pid))
        get_connection().commit()

    def close_run(self, script_path: str, pid: int, ended_at: float) -> None:
        get_connection().execute(
            "UPDATE script_runs SET ended_at=? WHERE script_path=? AND pid=? AND ended_at IS NULL",
            (ended_at, script_path, pid))
        get_connection().commit()

    def recent(self, limit: int = 200, script_path: str | None = None,
               since_ts: float | None = None) -> list[ScriptRunRow]:
        sql = "SELECT * FROM script_runs WHERE 1=1"
        params: list[object] = []
        if script_path:
            sql += " AND script_path = ?"
            params.append(script_path)
        if since_ts is not None:
            sql += " AND started_at >= ?"
            params.append(since_ts)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        rows = get_connection().execute(sql, params).fetchall()
        return [
            ScriptRunRow(
                id=r["id"], script_path=r["script_path"], pid=r["pid"],
                started_at=r["started_at"], last_seen=r["last_seen"],
                ended_at=r["ended_at"], interpreter=r["interpreter"],
                cmdline=r["cmdline"], trigger=r["trigger"],
            )
            for r in rows
        ]

    def open_runs(self) -> list[ScriptRunRow]:
        rows = get_connection().execute(
            "SELECT * FROM script_runs WHERE ended_at IS NULL ORDER BY started_at"
        ).fetchall()
        return [
            ScriptRunRow(
                id=r["id"], script_path=r["script_path"], pid=r["pid"],
                started_at=r["started_at"], last_seen=r["last_seen"],
                ended_at=r["ended_at"], interpreter=r["interpreter"],
                cmdline=r["cmdline"], trigger=r["trigger"],
            )
            for r in rows
        ]

    def delete_before(self, ts: float) -> int:
        cur = get_connection().execute("DELETE FROM script_runs WHERE started_at < ?", (ts,))
        get_connection().commit()
        return cur.rowcount
