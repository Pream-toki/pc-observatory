"""Read-only real-machine smoke tests for ops collectors."""
from __future__ import annotations

import time

from app.collectors.ai import _jan_models, _ollama_models
from app.collectors.automation import AutomationCollector
from app.collectors.events import EventLogCollector
from app.collectors.network import NetworkCollector
from app.collectors.projects import PythonProjectCollector


def test_network_collector_finds_listening_ports(tmp_db):
    result = NetworkCollector().run()
    assert result.ok
    ports = result.data
    assert len(ports) > 10           # any Windows box has dozens of listeners
    assert all(p["local_port"] > 0 for p in ports)
    owners = {p["process_name"] for p in ports}
    assert any(name not in ("", "Permission required") for name in owners)


def test_automation_collector_finds_services_and_startup(tmp_db):
    result = AutomationCollector().run()
    assert result.ok
    data = result.data
    assert len(data["services"]) > 50       # Windows always runs many services
    assert any(s["status"] == "running" for s in data["services"])
    assert isinstance(data["startup"], list)
    assert isinstance(data["tasks"], list)  # may be large; presence is what we test


def test_event_collector_reads_system_log(tmp_db):
    collector = EventLogCollector()
    collector._last_ts = time.time() - 6 * 3600  # quiet machines may have no fresh events
    result = collector.run()
    assert result.status.value in ("success", "partial")
    events = collector._event_repo.recent(limit=10)
    assert events                          # System log is readable without admin
    assert all(e.event_id >= 0 for e in events)


def test_ollama_model_parser_real_machine(tmp_db):
    """This machine demonstrably has 4 Ollama models (verified earlier)."""
    models = _ollama_models()
    names = {m.name for m in models}
    assert len(models) >= 4
    assert any("qwen2.5-coder" in n for n in names)
    assert all(m.size_bytes > 1_000_000_000 for m in models if ":7b" in m.name)


def test_project_collector_runs_readonly(tmp_db):
    result = PythonProjectCollector(roots=[r"%USERPROFILE%\Documents"]).run()
    assert result.status.value in ("success", "partial")
    assert isinstance(result.data, list)
