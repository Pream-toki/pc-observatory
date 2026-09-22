"""Snapshot & change detection engine (spec §33-35).

A snapshot is a compact fingerprint of the inventories (applications, tools,
AI tools/models, services, startup, tasks, ports, projects). Diffing the new
fingerprint against the previous one yields NEW / REMOVED / CHANGED items
recorded in change_log — the data behind the Changes page and the future
"What changed since last week?" answer.
"""
from __future__ import annotations

import logging
import time

from ..database.inventory_repositories import (
    AiModelRepository,
    AiToolRepository,
    ApplicationRepository,
    ToolRepository,
)
from ..database.ops_repositories import (
    ChangeRepository,
    ServiceRepository,
    SnapshotRepository,
    StartupRepository,
    TaskRepository,
)

log = logging.getLogger(__name__)

_CATEGORIES = [
    "applications", "tools", "ai_tools", "ai_models",
    "services", "startup", "tasks", "ports",
]


def _fingerprint(
    apps, tools, ai_tools, ai_models, services, startup, tasks, ports,
) -> dict[str, dict[str, str]]:
    return {
        "applications": {a.key_path: f"{a.name} {a.version}".strip() for a in apps},
        "tools": {t.exe_path: f"{t.tool} ({t.tool})" for t in tools},
        "ai_tools": {t.exe_path: t.name for t in ai_tools},
        "ai_models": {m.file_path: f"{m.runtime}: {m.name}" for m in ai_models},
        "services": {s.name: f"{s.display_name} [{s.status}]" for s in services},
        "startup": {f"{s.source}\\{s.entry_name}": s.command for s in startup},
        "tasks": {t.task_path: f"{t.action_exe} [{t.status}]" for t in tasks},
        "ports": {f"{p.protocol}:{p.local_ip}:{p.local_port}":
                  f"{p.process_name} (PID {p.pid})" for p in ports},
    }


class SnapshotEngine:
    def __init__(self) -> None:
        self._snapshots = SnapshotRepository()
        self._changes = ChangeRepository()
        self._apps = ApplicationRepository()
        self._tools = ToolRepository()
        self._ai_tools = AiToolRepository()
        self._ai_models = AiModelRepository()
        self._services = ServiceRepository()
        self._startup = StartupRepository()
        self._tasks = TaskRepository()
        from ..database.ops_repositories import PortRepository
        self._ports = PortRepository()

    def take_snapshot(self, label: str = "manual") -> int:
        """Fingerprint current inventories, diff vs previous, record changes."""
        fp = _fingerprint(
            self._apps.all(), self._tools.all(), self._ai_tools.all(),
            self._ai_models.all(), self._services.all(), self._startup.all(),
            self._tasks.all(), self._ports.all(),
        )
        snapshot_id = self._snapshots.add(label, {k: len(v) for k, v in fp.items()})
        previous = self._snapshots.latest("fingerprint")
        changes: list[dict] = []
        if previous is not None:
            try:
                import json

                prev_fp = json.loads(previous.payload)
            except ValueError:
                prev_fp = {}
            now = time.time()
            for category in _CATEGORIES:
                old: dict = prev_fp.get(category, {})
                new: dict = fp.get(category, {})
                for key in new.keys() - old.keys():
                    changes.append({
                        "ts": now, "category": category, "change_type": "new",
                        "item_key": key, "title": f"NEW in {category}: {new[key]}",
                        "details": key,
                    })
                for key in old.keys() - new.keys():
                    changes.append({
                        "ts": now, "category": category, "change_type": "removed",
                        "item_key": key, "title": f"REMOVED from {category}: {old[key]}",
                        "details": key,
                    })
                for key in old.keys() & new.keys():
                    if old[key] != new[key]:
                        changes.append({
                            "ts": now, "category": category, "change_type": "modified",
                            "item_key": key,
                            "title": f"CHANGED in {category}: {old[key]} → {new[key]}",
                            "details": key,
                        })
        # Store the full fingerprint for the next diff.
        import json as _json

        from ..database.connection import get_connection
        get_connection().execute(
            "INSERT INTO snapshots (created_at, kind, payload) VALUES (?,?,?)",
            (time.time(), "fingerprint", _json.dumps(fp)),
        )
        get_connection().commit()
        self._changes.add_many(changes[:1000])
        log.info("Snapshot #%s taken (%s changes vs previous)", snapshot_id, len(changes))
        return snapshot_id

    def changes_since(self, since_ts: float):
        return self._changes.recent(limit=1000, since_ts=since_ts)
