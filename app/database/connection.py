"""SQLite connection manager.

One connection per thread (SQLite connections are not safely shareable across
threads). WAL mode lets the background collection thread write while the UI
thread reads without blocking either side.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_local = threading.local()
_db_path: Path | None = None
_init_lock = threading.Lock()


def configure(db_path: Path) -> None:
    """Set the database location. Call once at startup before any query."""
    global _db_path
    with _init_lock:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _db_path = db_path


def _new_connection() -> sqlite3.Connection:
    if _db_path is None:
        raise RuntimeError("database.configure() must be called before get_connection()")
    conn = sqlite3.connect(str(_db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_connection() -> sqlite3.Connection:
    """Return this thread's connection, creating it on first use."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _new_connection()
        _local.conn = conn
        log.debug("Opened new SQLite connection for thread %s", threading.current_thread().name)
    return conn


def close_thread_connection() -> None:
    """Close this thread's connection (called when a worker thread exits)."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
