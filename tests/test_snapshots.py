"""Tests for the snapshot & change-detection engine (mocked inventory rows)."""
from __future__ import annotations

import time
from dataclasses import replace

from app.database.inventory_repositories import ApplicationRow
from app.database.ops_repositories import ChangeRepository
from app.services.snapshots import SnapshotEngine


def _app(key: str, name: str = "App", version: str = "1.0") -> ApplicationRow:
    now = time.time()
    return ApplicationRow(
        key_path=key, name=name, version=version, publisher="P",
        install_location="", install_date="", source="test",
        first_seen=now, last_seen=now,
    )


def test_first_snapshot_records_no_changes(tmp_db):
    engine = SnapshotEngine()
    # Empty inventories: fingerprint all empty; previous None -> no changes.
    sid = engine.take_snapshot("test")
    assert sid > 0
    assert engine.changes_since(0) == []


def test_second_snapshot_detects_new_and_removed(tmp_db, monkeypatch):
    import app.services.snapshots as snap_mod

    engine = SnapshotEngine()

    apps_v1 = [_app("k1", "Keep"), _app("k2", "Gone")]
    monkeypatch.setattr(engine._apps, "all", lambda: apps_v1)
    monkeypatch.setattr(engine._tools, "all", lambda: [])
    monkeypatch.setattr(engine._ai_tools, "all", lambda: [])
    monkeypatch.setattr(engine._ai_models, "all", lambda: [])
    monkeypatch.setattr(engine._services, "all", lambda: [])
    monkeypatch.setattr(engine._startup, "all", lambda: [])
    monkeypatch.setattr(engine._tasks, "all", lambda: [])
    monkeypatch.setattr(engine._ports, "all", lambda: [])
    engine.take_snapshot("test")

    apps_v2 = [_app("k1", "Keep"), _app("k3", "NewApp", "2.0")]
    monkeypatch.setattr(engine._apps, "all", lambda: apps_v2)
    engine.take_snapshot("test")

    changes = engine.changes_since(0)
    types = {(c.category, c.change_type, c.item_key) for c in changes}
    assert ("applications", "new", "k3") in types
    assert ("applications", "removed", "k2") in types
    assert all(item != "k1" for _c, _t, item in types)  # unchanged key: no event


def test_version_change_is_modified(tmp_db, monkeypatch):
    engine = SnapshotEngine()
    monkeypatch.setattr(engine._apps, "all", lambda: [_app("k1", "App", "1.0")])
    monkeypatch.setattr(engine._tools, "all", lambda: [])
    monkeypatch.setattr(engine._ai_tools, "all", lambda: [])
    monkeypatch.setattr(engine._ai_models, "all", lambda: [])
    monkeypatch.setattr(engine._services, "all", lambda: [])
    monkeypatch.setattr(engine._startup, "all", lambda: [])
    monkeypatch.setattr(engine._tasks, "all", lambda: [])
    monkeypatch.setattr(engine._ports, "all", lambda: [])
    engine.take_snapshot("test")

    monkeypatch.setattr(engine._apps, "all", lambda: [_app("k1", "App", "2.0")])
    engine.take_snapshot("test")

    changes = engine.changes_since(0)
    assert any(
        c.change_type == "modified" and c.item_key == "k1" and "2.0" in c.title
        for c in changes
    )
