"""Application configuration.

A small dataclass holds every setting; it is saved as JSON in
``%APPDATA%\\PCObservatory\\config.json``. Settings UI writes through
``AppConfig.save`` so nothing else touches the file directly.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

THEME_CHOICES = ("dark", "light")
DEFAULT_THEME = "dark"
METRICS_INTERVAL_S = 2.0
SYSTEM_INFO_INTERVAL_S = 300.0

CHART_RANGES_S = (30, 60, 300, 1800)  # 30 s / 1 m / 5 m / 30 m


def app_data_dir() -> Path:
    """Where config and the database live: %APPDATA%\\PCObservatory."""
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    return root / "PCObservatory"


def project_root() -> Path:
    """The folder containing main.py (logs/ lives here)."""
    return Path(__file__).resolve().parents[2]


@dataclass
class AppConfig:
    # General
    theme: str = DEFAULT_THEME
    metrics_interval_s: float = METRICS_INTERVAL_S
    system_info_interval_s: float = SYSTEM_INFO_INTERVAL_S
    # Collection / history
    retention_days: int = 30
    persist_sample_every_s: float = 15.0   # DB keeps one row per 15 s; charts stay in RAM
    # Python project scan roots (spec §15) — never the whole disk.
    project_dirs: tuple[str, ...] = (
        r"%USERPROFILE%\Documents",
        r"%USERPROFILE%\dev",
        r"C:\dev",
        r"C:\ai tasks",
    )
    # Privacy
    local_only: bool = True

    config_dir: Path = field(default_factory=app_data_dir, repr=False, compare=False)

    # ---- persistence -------------------------------------------------
    @property
    def config_path(self) -> Path:
        return self.config_dir / "config.json"

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload["config_dir"] = str(self.config_dir)
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, config_dir: Path | None = None) -> "AppConfig":
        """Load config, filling in defaults for anything missing or unknown."""
        cfg = cls()
        if config_dir is not None:
            cfg.config_dir = config_dir
        path = cfg.config_path
        if not path.exists():
            cfg.save()
            return cfg
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cfg  # corrupt config -> fall back to defaults, keep defaults saved
        valid = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key in valid:
                setattr(cfg, key, value)
        if not isinstance(cfg.config_dir, Path):  # JSON round-trips Path as str
            cfg.config_dir = Path(cfg.config_dir)
        cfg.sanitize()
        return cfg

    # ---- validation --------------------------------------------------
    def sanitize(self) -> None:
        """Clamp values so a hand-edited config can never break the app."""
        self.theme = self.theme if self.theme in THEME_CHOICES else DEFAULT_THEME
        self.metrics_interval_s = min(max(self.metrics_interval_s, 1.0), 60.0)
        self.system_info_interval_s = min(max(self.system_info_interval_s, 60.0), 3600.0)
        self.retention_days = min(max(self.retention_days, 1), 3650)
        self.persist_sample_every_s = min(max(self.persist_sample_every_s, 5.0), 300.0)
        if isinstance(self.project_dirs, str):  # tolerate hand-edited JSON
            self.project_dirs = (self.project_dirs,)
        self.project_dirs = tuple(
            d.strip() for d in self.project_dirs if isinstance(d, str) and d.strip()
        )
