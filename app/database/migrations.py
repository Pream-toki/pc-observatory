"""Database migrations — append-only; never edit an applied migration.

Each entry is applied once and recorded in schema_migrations. Fresh
databases replay everything; existing databases only get the new scripts.
"""
from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)

# v1 — Phase 1: live metrics, system facts, collection runs.
_V1 = """
CREATE TABLE IF NOT EXISTS system_info (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    hostname      TEXT NOT NULL,
    os_name       TEXT NOT NULL,
    os_version    TEXT NOT NULL,
    os_build      TEXT NOT NULL,
    architecture  TEXT NOT NULL,
    cpu_model     TEXT NOT NULL,
    cpu_cores_logical  INTEGER NOT NULL,
    cpu_cores_physical INTEGER NOT NULL,
    ram_total_gb  REAL NOT NULL,
    boot_time     REAL NOT NULL,
    current_user  TEXT NOT NULL,
    collected_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS metric_samples (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                REAL NOT NULL,
    cpu_percent       REAL NOT NULL,
    ram_used_gb       REAL NOT NULL,
    ram_percent       REAL NOT NULL,
    disk_read_mb_s    REAL NOT NULL,
    disk_write_mb_s   REAL NOT NULL,
    net_up_mb_s       REAL NOT NULL,
    net_down_mb_s     REAL NOT NULL,
    process_count     INTEGER NOT NULL,
    listening_ports   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metric_samples_ts ON metric_samples (ts);

CREATE TABLE IF NOT EXISTS collection_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collector     TEXT NOT NULL,
    status        TEXT NOT NULL,
    detail        TEXT NOT NULL DEFAULT '',
    started_at    REAL NOT NULL,
    duration_ms   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_collection_runs_started ON collection_runs (started_at);
CREATE INDEX IF NOT EXISTS idx_collection_runs_collector ON collection_runs (collector, started_at);
"""

# v2 — ① Processes + Timeline: first/last-seen process history and events.
_V2 = """
CREATE TABLE IF NOT EXISTS process_seen (
    pid            INTEGER NOT NULL,
    name           TEXT NOT NULL,
    exe_path       TEXT NOT NULL DEFAULT '',
    first_seen     REAL NOT NULL,
    last_seen      REAL NOT NULL,
    last_cpu       REAL,
    last_mem_mb    REAL,
    PRIMARY KEY (pid, name, exe_path)
);
CREATE INDEX IF NOT EXISTS idx_process_seen_last_seen ON process_seen (last_seen);

CREATE TABLE IF NOT EXISTS timeline_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    kind       TEXT NOT NULL,
    title      TEXT NOT NULL,
    details    TEXT NOT NULL DEFAULT '',
    ref_table  TEXT NOT NULL DEFAULT '',
    ref_key    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_timeline_ts ON timeline_events (ts);
CREATE INDEX IF NOT EXISTS idx_timeline_kind ON timeline_events (kind, ts);
"""

# v3 — ②③ Inventories: applications, tool locations, AI tools & models.
_V3 = """
CREATE TABLE IF NOT EXISTS applications (
    key_path        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    version         TEXT NOT NULL DEFAULT '',
    publisher       TEXT NOT NULL DEFAULT '',
    install_location TEXT NOT NULL DEFAULT '',
    install_date    TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL,
    first_seen      REAL NOT NULL,
    last_seen       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_applications_name ON applications (name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS tool_locations (
    tool            TEXT NOT NULL,
    exe_path        TEXT NOT NULL,
    version         TEXT NOT NULL DEFAULT '',
    install_dir     TEXT NOT NULL DEFAULT '',
    publisher       TEXT NOT NULL DEFAULT '',
    detection_source TEXT NOT NULL DEFAULT '',
    path_visible    INTEGER NOT NULL DEFAULT 0,
    first_seen      REAL NOT NULL,
    last_seen       REAL NOT NULL,
    PRIMARY KEY (tool, exe_path)
);

CREATE TABLE IF NOT EXISTS ai_tools (
    name            TEXT NOT NULL,
    exe_path        TEXT NOT NULL,
    version         TEXT NOT NULL DEFAULT '',
    install_dir     TEXT NOT NULL DEFAULT '',
    detection_source TEXT NOT NULL DEFAULT '',
    first_seen      REAL NOT NULL,
    last_seen       REAL NOT NULL,
    PRIMARY KEY (name, exe_path)
);

CREATE TABLE IF NOT EXISTS ai_models (
    runtime         TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    name            TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    first_seen      REAL NOT NULL,
    last_seen       REAL NOT NULL,
    PRIMARY KEY (runtime, file_path)
);
"""

# v4 — Network, automation, events, snapshots, changes, projects.
_V4 = """
CREATE TABLE IF NOT EXISTS network_ports (
    protocol    TEXT NOT NULL,
    local_ip    TEXT NOT NULL,
    local_port  INTEGER NOT NULL,
    pid         INTEGER NOT NULL,
    process_name TEXT NOT NULL DEFAULT '',
    exe_path    TEXT NOT NULL DEFAULT '',
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    PRIMARY KEY (protocol, local_ip, local_port)
);

CREATE TABLE IF NOT EXISTS services_seen (
    name        TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT '',
    start_type  TEXT NOT NULL DEFAULT '',
    account     TEXT NOT NULL DEFAULT '',
    exe_path    TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    PRIMARY KEY (name)
);

CREATE TABLE IF NOT EXISTS startup_items (
    source      TEXT NOT NULL,
    entry_name  TEXT NOT NULL,
    command     TEXT NOT NULL DEFAULT '',
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    PRIMARY KEY (source, entry_name)
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    task_path   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT '',
    trigger_info TEXT NOT NULL DEFAULT '',
    action_exe  TEXT NOT NULL DEFAULT '',
    action_args TEXT NOT NULL DEFAULT '',
    author      TEXT NOT NULL DEFAULT '',
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    PRIMARY KEY (task_path)
);

CREATE TABLE IF NOT EXISTS event_log_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    log_name    TEXT NOT NULL,
    provider    TEXT NOT NULL DEFAULT '',
    event_id    INTEGER NOT NULL,
    level       TEXT NOT NULL DEFAULT '',
    message     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON event_log_entries (ts);
CREATE INDEX IF NOT EXISTS idx_events_level ON event_log_entries (level, ts);

CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  REAL NOT NULL,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS change_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    category    TEXT NOT NULL,
    change_type TEXT NOT NULL,
    item_key    TEXT NOT NULL,
    title       TEXT NOT NULL,
    details     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_changes_ts ON change_log (ts);

CREATE TABLE IF NOT EXISTS python_projects (
    path        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    py_files    INTEGER NOT NULL DEFAULT 0,
    has_venv    INTEGER NOT NULL DEFAULT 0,
    has_git     INTEGER NOT NULL DEFAULT 0,
    has_requirements INTEGER NOT NULL DEFAULT 0,
    last_modified REAL NOT NULL DEFAULT 0,
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL
);
"""

# v5 — Automation Monitor: script inventory + per-run history.
_V5 = """
CREATE TABLE IF NOT EXISTS scripts (
    path        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,               -- python | powershell | batch
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    modified    REAL NOT NULL DEFAULT 0,
    project     TEXT NOT NULL DEFAULT '',    -- owning project folder if any
    trigger_hint TEXT NOT NULL DEFAULT '',   -- task/startup link when found
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scripts_kind ON scripts (kind);

CREATE TABLE IF NOT EXISTS script_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    script_path TEXT NOT NULL,
    pid         INTEGER NOT NULL,
    started_at  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    ended_at    REAL,                        -- NULL = still running
    interpreter TEXT NOT NULL DEFAULT '',
    cmdline     TEXT NOT NULL DEFAULT '',    -- redacted
    trigger     TEXT NOT NULL DEFAULT ''     -- scheduled task / startup / manual
);
CREATE INDEX IF NOT EXISTS idx_script_runs_script ON script_runs (script_path, started_at);
CREATE INDEX IF NOT EXISTS idx_script_runs_started ON script_runs (started_at);
"""

MIGRATIONS: list[tuple[int, str]] = [(1, _V1), (2, _V2), (3, _V3), (4, _V4), (5, _V5)]


def migrate(conn: sqlite3.Connection) -> int:
    """Apply all pending migrations. Returns the final schema version."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    for version, script in MIGRATIONS:
        if version in applied:
            continue
        log.info("Applying database migration v%d", version)
        conn.executescript(script)
        conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
    conn.commit()
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0] or 0)
