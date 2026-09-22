"""Shared fixtures: temporary database and temporary config directory."""
from __future__ import annotations

import pytest

from app.config.settings import AppConfig
from app.database import connection
from app.database.migrations import migrate


@pytest.fixture()
def tmp_db(tmp_path):
    """Point the database layer at a throwaway file with schema applied."""
    connection.close_thread_connection()
    connection.configure(tmp_path / "test.db")
    conn = connection.get_connection()
    migrate(conn)
    yield conn
    connection.close_thread_connection()


@pytest.fixture()
def app_config(tmp_path) -> AppConfig:
    """AppConfig rooted in a temporary directory (no %APPDATA% touched)."""
    return AppConfig(config_dir=tmp_path / "cfg")
