"""Tests for AppConfig: defaults, round-trip, sanitizing, corrupt files."""
from __future__ import annotations

from app.config.settings import AppConfig


def test_load_without_file_returns_defaults(tmp_path):
    cfg = AppConfig.load(config_dir=tmp_path)
    assert cfg.theme == "dark"
    assert cfg.metrics_interval_s == 2.0
    assert cfg.retention_days == 30
    assert cfg.config_path.exists()  # defaults written for next launch


def test_save_and_load_round_trip(tmp_path):
    cfg = AppConfig.load(config_dir=tmp_path)
    cfg.theme = "light"
    cfg.metrics_interval_s = 4.5
    cfg.retention_days = 7
    cfg.save()

    cfg2 = AppConfig.load(config_dir=tmp_path)
    assert cfg2.theme == "light"
    assert cfg2.metrics_interval_s == 4.5
    assert cfg2.retention_days == 7


def test_sanitize_clamps_bad_values():
    cfg = AppConfig()
    cfg.theme = "neon"
    cfg.metrics_interval_s = 999.0
    cfg.retention_days = -5
    cfg.sanitize()
    assert cfg.theme == "dark"
    assert cfg.metrics_interval_s == 60.0
    assert cfg.retention_days == 1


def test_corrupt_config_falls_back_to_defaults(tmp_path):
    (tmp_path / "config.json").write_text("{not valid json", encoding="utf-8")
    cfg = AppConfig.load(config_dir=tmp_path)
    assert cfg.theme == "dark"
