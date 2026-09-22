"""Read-only real-machine smoke tests for the inventory collectors.

These read the registry and the filesystem only — the same access any
'Installed Apps' list has. Nothing is executed and nothing is modified.
"""
from __future__ import annotations

from app.collectors.ai import AiCollector
from app.collectors.applications import ApplicationsCollector
from app.collectors.tools import ToolLocationsCollector


def test_applications_collector_real_readonly(tmp_db):
    result = ApplicationsCollector().run()
    assert result.ok
    apps = result.data
    assert len(apps) > 0            # every Windows PC has *some* installed software
    names = {a.name for a in apps}
    assert all(n.strip() for n in names)
    assert all(a.key_path for a in apps)


def test_tool_locations_collector_real_readonly(tmp_db):
    result = ToolLocationsCollector().run()
    assert result.ok
    tools = result.data
    # This machine demonstrably has Python (verified during setup).
    python_hits = [t for t in tools if t.tool == "Python" and t.exe_path]
    assert python_hits
    assert all(t.path_visible in (True, False) for t in tools)


def test_ai_collector_real_readonly(tmp_db):
    result = AiCollector().run()
    assert result.ok
    data = result.data
    assert set(data.keys()) == {"tools", "models"}
    assert all(m.size_bytes >= 0 for m in data["models"])
