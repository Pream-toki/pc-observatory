"""Repositories for the inventories (applications, tools, AI).

All of them follow the same pattern as the rest of the app: upsert with
first_seen/last_seen so history is preserved, and honest empty strings when
Windows does not expose a field.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .connection import get_connection

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplicationRow:
    key_path: str
    name: str
    version: str
    publisher: str
    install_location: str
    install_date: str
    source: str
    first_seen: float
    last_seen: float


class ApplicationRepository:
    """Installed-software inventory (spec §10)."""

    def upsert_many(self, apps: list) -> None:
        if not apps:
            return
        conn = get_connection()
        now = time.time()
        existing = {
            r["key_path"]: r["first_seen"]
            for r in conn.execute("SELECT key_path, first_seen FROM applications")
        }
        conn.executemany(
            "INSERT INTO applications (key_path, name, version, publisher,"
            " install_location, install_date, source, first_seen, last_seen)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(key_path) DO UPDATE SET"
            " name=excluded.name, version=excluded.version, publisher=excluded.publisher,"
            " install_location=excluded.install_location, install_date=excluded.install_date,"
            " source=excluded.source, last_seen=excluded.last_seen",
            [
                (a.key_path, a.name, a.version, a.publisher, a.install_location,
                 a.install_date, a.source, existing.get(a.key_path, now), now)
                for a in apps
            ],
        )
        conn.commit()

    def all(self) -> list[ApplicationRow]:
        rows = get_connection().execute(
            "SELECT * FROM applications ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [ApplicationRow(**dict(r)) for r in rows]

    def count(self) -> int:
        return int(get_connection().execute("SELECT COUNT(*) FROM applications").fetchone()[0])

    def delete_stale(self, current_keys: set[str], before_ts: float) -> int:
        """Optional: remove rows for keys no longer detected after a full scan."""
        cur = get_connection().execute(
            "DELETE FROM applications WHERE last_seen < ? AND key_path NOT IN"
            f" ({', '.join('?' * max(1, len(current_keys)))})",
            (before_ts, *current_keys) if current_keys else (before_ts, ""),
        )
        get_connection().commit()
        return cur.rowcount


@dataclass(frozen=True)
class ToolRow:
    tool: str
    exe_path: str
    version: str
    install_dir: str
    publisher: str
    detection_source: str
    path_visible: int
    first_seen: float
    last_seen: float


class ToolRepository:
    """Tool-location inventory (spec §11)."""

    def upsert_many(self, tools: list) -> None:
        if not tools:
            return
        conn = get_connection()
        now = time.time()
        existing = {
            (r["tool"], r["exe_path"]): r["first_seen"]
            for r in conn.execute("SELECT tool, exe_path, first_seen FROM tool_locations")
        }
        conn.executemany(
            "INSERT INTO tool_locations (tool, exe_path, version, install_dir, publisher,"
            " detection_source, path_visible, first_seen, last_seen)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(tool, exe_path) DO UPDATE SET"
            " version=excluded.version, install_dir=excluded.install_dir,"
            " publisher=excluded.publisher, detection_source=excluded.detection_source,"
            " path_visible=excluded.path_visible, last_seen=excluded.last_seen",
            [
                (t.tool, t.exe_path, t.version, t.install_dir, t.publisher,
                 t.detection_source, int(t.path_visible),
                 existing.get((t.tool, t.exe_path), now), now)
                for t in tools
            ],
        )
        conn.commit()

    def all(self) -> list[ToolRow]:
        rows = get_connection().execute(
            "SELECT * FROM tool_locations ORDER BY tool COLLATE NOCASE, exe_path"
        ).fetchall()
        return [ToolRow(**dict(r)) for r in rows]


@dataclass(frozen=True)
class AiToolRow:
    name: str
    exe_path: str
    version: str
    install_dir: str
    detection_source: str
    first_seen: float
    last_seen: float


class AiToolRepository:
    def upsert_many(self, tools: list) -> None:
        if not tools:
            return
        conn = get_connection()
        now = time.time()
        existing = {
            (r["name"], r["exe_path"]): r["first_seen"]
            for r in conn.execute("SELECT name, exe_path, first_seen FROM ai_tools")
        }
        conn.executemany(
            "INSERT INTO ai_tools (name, exe_path, version, install_dir,"
            " detection_source, first_seen, last_seen) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(name, exe_path) DO UPDATE SET"
            " version=excluded.version, install_dir=excluded.install_dir,"
            " detection_source=excluded.detection_source, last_seen=excluded.last_seen",
            [
                (t.name, t.exe_path, t.version, t.install_dir, t.detection_source,
                 existing.get((t.name, t.exe_path), now), now)
                for t in tools
            ],
        )
        conn.commit()

    def all(self) -> list[AiToolRow]:
        rows = get_connection().execute(
            "SELECT * FROM ai_tools ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [AiToolRow(**dict(r)) for r in rows]


@dataclass(frozen=True)
class AiModelRow:
    runtime: str
    file_path: str
    name: str
    size_bytes: int
    first_seen: float
    last_seen: float


class AiModelRepository:
    def upsert_many(self, models: list) -> None:
        if not models:
            return
        conn = get_connection()
        now = time.time()
        existing = {
            (r["runtime"], r["file_path"]): r["first_seen"]
            for r in conn.execute("SELECT runtime, file_path, first_seen FROM ai_models")
        }
        conn.executemany(
            "INSERT INTO ai_models (runtime, file_path, name, size_bytes,"
            " first_seen, last_seen) VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(runtime, file_path) DO UPDATE SET"
            " name=excluded.name, size_bytes=excluded.size_bytes,"
            " last_seen=excluded.last_seen",
            [
                (m.runtime, m.file_path, m.name, m.size_bytes,
                 existing.get((m.runtime, m.file_path), now), now)
                for m in models
            ],
        )
        conn.commit()

    def all(self) -> list[AiModelRow]:
        rows = get_connection().execute(
            "SELECT * FROM ai_models ORDER BY runtime COLLATE NOCASE, name COLLATE NOCASE"
        ).fetchall()
        return [AiModelRow(**dict(r)) for r in rows]
