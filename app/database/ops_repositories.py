"""Repositories for network ports, automation, events, changes, snapshots, projects."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from .connection import get_connection

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PortRow:
    protocol: str
    local_ip: str
    local_port: int
    pid: int
    process_name: str
    exe_path: str
    first_seen: float
    last_seen: float


class PortRepository:
    def upsert_many(self, rows: list[dict]) -> None:
        if not rows:
            return
        conn = get_connection()
        now = time.time()
        conn.executemany(
            "INSERT INTO network_ports (protocol, local_ip, local_port, pid,"
            " process_name, exe_path, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(protocol, local_ip, local_port) DO UPDATE SET"
            " pid=excluded.pid, process_name=excluded.process_name,"
            " exe_path=excluded.exe_path, last_seen=excluded.last_seen",
            [
                (r["protocol"], r["local_ip"], r["local_port"], r["pid"],
                 r["process_name"], r["exe_path"],
                 self._first_seen(conn, r), now)
                for r in rows
            ],
        )
        conn.commit()

    @staticmethod
    def _first_seen(conn, r: dict) -> float:
        row = conn.execute(
            "SELECT first_seen FROM network_ports WHERE protocol=? AND local_ip=? AND local_port=?",
            (r["protocol"], r["local_ip"], r["local_port"]),
        ).fetchone()
        return float(row[0]) if row else time.time()

    def all(self) -> list[PortRow]:
        rows = get_connection().execute(
            "SELECT * FROM network_ports ORDER BY local_port"
        ).fetchall()
        return [PortRow(**dict(r)) for r in rows]


@dataclass(frozen=True)
class ServiceRow:
    name: str
    display_name: str
    status: str
    start_type: str
    account: str
    exe_path: str
    description: str
    first_seen: float
    last_seen: float


class ServiceRepository:
    def upsert_many(self, rows: list[dict]) -> None:
        if not rows:
            return
        conn = get_connection()
        now = time.time()
        conn.executemany(
            "INSERT INTO services_seen (name, display_name, status, start_type, account,"
            " exe_path, description, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(name) DO UPDATE SET display_name=excluded.display_name,"
            " status=excluded.status, start_type=excluded.start_type,"
            " account=excluded.account, exe_path=excluded.exe_path,"
            " description=excluded.description, last_seen=excluded.last_seen",
            [
                (r["name"], r["display_name"], r["status"], r["start_type"],
                 r["account"], r["exe_path"], r["description"],
                 self._first_seen(conn, r["name"]), now)
                for r in rows
            ],
        )
        conn.commit()

    @staticmethod
    def _first_seen(conn, name: str) -> float:
        row = conn.execute(
            "SELECT first_seen FROM services_seen WHERE name=?", (name,)
        ).fetchone()
        return float(row[0]) if row else time.time()

    def all(self) -> list[ServiceRow]:
        rows = get_connection().execute(
            "SELECT * FROM services_seen ORDER BY display_name COLLATE NOCASE"
        ).fetchall()
        return [ServiceRow(**dict(r)) for r in rows]


@dataclass(frozen=True)
class StartupRow:
    source: str
    entry_name: str
    command: str
    first_seen: float
    last_seen: float


class StartupRepository:
    def upsert_many(self, rows: list[dict]) -> None:
        if not rows:
            return
        conn = get_connection()
        now = time.time()
        conn.executemany(
            "INSERT INTO startup_items (source, entry_name, command, first_seen, last_seen)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(source, entry_name) DO UPDATE SET"
            " command=excluded.command, last_seen=excluded.last_seen",
            [
                (r["source"], r["entry_name"], r["command"],
                 self._first_seen(conn, r["source"], r["entry_name"]), now)
                for r in rows
            ],
        )
        conn.commit()

    @staticmethod
    def _first_seen(conn, source: str, entry: str) -> float:
        row = conn.execute(
            "SELECT first_seen FROM startup_items WHERE source=? AND entry_name=?",
            (source, entry),
        ).fetchone()
        return float(row[0]) if row else time.time()

    def all(self) -> list[StartupRow]:
        rows = get_connection().execute(
            "SELECT * FROM startup_items ORDER BY source, entry_name COLLATE NOCASE"
        ).fetchall()
        return [StartupRow(**dict(r)) for r in rows]


@dataclass(frozen=True)
class TaskRow:
    task_path: str
    status: str
    trigger_info: str
    action_exe: str
    action_args: str
    author: str
    first_seen: float
    last_seen: float


class TaskRepository:
    def upsert_many(self, rows: list[dict]) -> None:
        if not rows:
            return
        conn = get_connection()
        now = time.time()
        conn.executemany(
            "INSERT INTO scheduled_tasks (task_path, status, trigger_info, action_exe,"
            " action_args, author, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(task_path) DO UPDATE SET status=excluded.status,"
            " trigger_info=excluded.trigger_info, action_exe=excluded.action_exe,"
            " action_args=excluded.action_args, author=excluded.author,"
            " last_seen=excluded.last_seen",
            [
                (r["task_path"], r["status"], r["trigger_info"], r["action_exe"],
                 r["action_args"], r["author"],
                 self._first_seen(conn, r["task_path"]), now)
                for r in rows
            ],
        )
        conn.commit()

    @staticmethod
    def _first_seen(conn, path: str) -> float:
        row = conn.execute(
            "SELECT first_seen FROM scheduled_tasks WHERE task_path=?", (path,)
        ).fetchone()
        return float(row[0]) if row else time.time()

    def all(self) -> list[TaskRow]:
        rows = get_connection().execute(
            "SELECT * FROM scheduled_tasks ORDER BY task_path"
        ).fetchall()
        return [TaskRow(**dict(r)) for r in rows]


@dataclass(frozen=True)
class EventRow:
    ts: float
    log_name: str
    provider: str
    event_id: int
    level: str
    message: str


class EventRepository:
    def insert_many(self, rows: list[dict]) -> None:
        if not rows:
            return
        conn = get_connection()
        conn.executemany(
            "INSERT INTO event_log_entries (ts, log_name, provider, event_id, level, message)"
            " VALUES (?,?,?,?,?,?)",
            [(r["ts"], r["log_name"], r["provider"], r["event_id"], r["level"],
              r["message"][:800]) for r in rows],
        )
        conn.commit()

    def recent(self, limit: int = 400, level: str | None = None,
               since_ts: float | None = None) -> list[EventRow]:
        sql = "SELECT * FROM event_log_entries WHERE 1=1"
        params: list[object] = []
        if level:
            sql += " AND level = ?"
            params.append(level)
        if since_ts is not None:
            sql += " AND ts >= ?"
            params.append(since_ts)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        rows = get_connection().execute(sql, params).fetchall()
        return [
            EventRow(
                ts=r["ts"], log_name=r["log_name"], provider=r["provider"],
                event_id=r["event_id"], level=r["level"], message=r["message"],
            )
            for r in rows
        ]

    def count_since(self, ts: float) -> int:
        return int(get_connection().execute(
            "SELECT COUNT(*) FROM event_log_entries WHERE ts >= ?", (ts,)
        ).fetchone()[0])

    def delete_before(self, ts: float) -> int:
        cur = get_connection().execute(
            "DELETE FROM event_log_entries WHERE ts < ?", (ts,))
        get_connection().commit()
        return cur.rowcount


@dataclass(frozen=True)
class ChangeRow:
    ts: float
    category: str
    change_type: str
    item_key: str
    title: str
    details: str


class ChangeRepository:
    def add_many(self, rows: list[dict]) -> None:
        if not rows:
            return
        conn = get_connection()
        conn.executemany(
            "INSERT INTO change_log (ts, category, change_type, item_key, title, details)"
            " VALUES (?,?,?,?,?,?)",
            [(r["ts"], r["category"], r["change_type"], r["item_key"],
              r["title"], r["details"]) for r in rows],
        )
        conn.commit()

    def recent(self, limit: int = 400, since_ts: float | None = None) -> list[ChangeRow]:
        sql = "SELECT * FROM change_log"
        params: list[object] = []
        if since_ts is not None:
            sql += " WHERE ts >= ?"
            params.append(since_ts)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        rows = get_connection().execute(sql, params).fetchall()
        return [
            ChangeRow(
                ts=r["ts"], category=r["category"], change_type=r["change_type"],
                item_key=r["item_key"], title=r["title"], details=r["details"],
            )
            for r in rows
        ]

    def count(self) -> int:
        return int(get_connection().execute("SELECT COUNT(*) FROM change_log").fetchone()[0])


@dataclass(frozen=True)
class SnapshotRow:
    id: int
    created_at: float
    kind: str
    payload: str


class SnapshotRepository:
    def add(self, kind: str, payload: dict) -> int:
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO snapshots (created_at, kind, payload) VALUES (?,?,?)",
            (time.time(), kind, json.dumps(payload)),
        )
        conn.commit()
        return int(cur.lastrowid)

    def latest(self, kind: str) -> SnapshotRow | None:
        row = get_connection().execute(
            "SELECT * FROM snapshots WHERE kind=? ORDER BY created_at DESC LIMIT 1",
            (kind,),
        ).fetchone()
        return SnapshotRow(**dict(row)) if row else None

    def all(self) -> list[SnapshotRow]:
        rows = get_connection().execute(
            "SELECT id, created_at, kind, payload FROM snapshots ORDER BY created_at DESC"
        ).fetchall()
        return [SnapshotRow(**dict(r)) for r in rows]


@dataclass(frozen=True)
class ProjectRow:
    path: str
    name: str
    py_files: int
    has_venv: int
    has_git: int
    has_requirements: int
    last_modified: float
    first_seen: float
    last_seen: float


class ProjectRepository:
    def upsert_many(self, rows: list[dict]) -> None:
        if not rows:
            return
        conn = get_connection()
        now = time.time()
        conn.executemany(
            "INSERT INTO python_projects (path, name, py_files, has_venv, has_git,"
            " has_requirements, last_modified, first_seen, last_seen)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(path) DO UPDATE SET py_files=excluded.py_files,"
            " has_venv=excluded.has_venv, has_git=excluded.has_git,"
            " has_requirements=excluded.has_requirements,"
            " last_modified=excluded.last_modified, last_seen=excluded.last_seen",
            [
                (r["path"], r["name"], r["py_files"], r["has_venv"], r["has_git"],
                 r["has_requirements"], r["last_modified"],
                 self._first_seen(conn, r["path"]), now)
                for r in rows
            ],
        )
        conn.commit()

    @staticmethod
    def _first_seen(conn, path: str) -> float:
        row = conn.execute(
            "SELECT first_seen FROM python_projects WHERE path=?", (path,)
        ).fetchone()
        return float(row[0]) if row else time.time()

    def all(self) -> list[ProjectRow]:
        rows = get_connection().execute(
            "SELECT * FROM python_projects ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [ProjectRow(**dict(r)) for r in rows]
