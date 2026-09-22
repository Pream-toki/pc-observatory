"""Tests for inventory repositories (first/last-seen semantics)."""
from __future__ import annotations

from app.database.inventory_repositories import (
    AiModelRepository,
    AiToolRepository,
    ApplicationRepository,
    ToolRepository,
)
from app.models.inventory import AiModel, AiTool, ApplicationInfo, ToolLocation


def _app(key: str, name: str = "App") -> ApplicationInfo:
    return ApplicationInfo(
        key_path=key, name=name, version="1.0", publisher="Pub",
        install_location=r"C:\Program Files\App", install_date="20260918",
        source="Registry uninstall (64-bit)",
    )


def test_application_upsert_preserves_first_seen(tmp_db):
    repo = ApplicationRepository()
    repo.upsert_many([_app("k1")])
    repo.upsert_many([_app("k1", "App Renamed")])
    rows = repo.all()
    assert len(rows) == 1
    assert rows[0].name == "App Renamed"
    assert rows[0].first_seen < rows[0].last_seen


def test_application_two_keys_two_rows(tmp_db):
    repo = ApplicationRepository()
    repo.upsert_many([_app("k1"), _app("k2", "Other")])
    assert repo.count() == 2


def test_tool_upsert_and_path_flag(tmp_db):
    repo = ToolRepository()
    repo.upsert_many([
        ToolLocation(
            tool="Python", exe_path=r"C:\py\python.exe", version="",
            install_dir=r"C:\py", publisher="PSF",
            detection_source="Filesystem", path_visible=True,
        ),
    ])
    rows = repo.all()
    assert len(rows) == 1
    assert rows[0].path_visible == 1
    repo.upsert_many([
        ToolLocation(
            tool="Python", exe_path=r"C:\py\python.exe", version="",
            install_dir=r"C:\py", publisher="PSF",
            detection_source="Filesystem", path_visible=False,
        ),
    ])
    rows = repo.all()
    assert rows[0].path_visible == 0            # updated
    assert rows[0].first_seen < rows[0].last_seen


def test_ai_tools_and_models_upsert(tmp_db):
    tools = AiToolRepository()
    models = AiModelRepository()
    tools.upsert_many([
        AiTool(name="Ollama", exe_path=r"C:\o\ollama.exe", version="",
               install_dir=r"C:\o", detection_source="Filesystem"),
    ])
    models.upsert_many([
        AiModel(runtime="Ollama", file_path=r"C:\m\llama.gguf",
                name="llama", size_bytes=4_000_000_000),
    ])
    assert tools.all()[0].name == "Ollama"
    row = models.all()[0]
    assert row.size_bytes == 4_000_000_000
    assert row.name == "llama"
