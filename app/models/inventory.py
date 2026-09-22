"""Inventory models: installed applications, tool locations, AI tools/models.

All fields may be 'Unavailable' (empty string) when Windows does not expose
them — the UI renders those honestly instead of guessing.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApplicationInfo:
    key_path: str                # registry key — the stable identity
    name: str
    version: str
    publisher: str
    install_location: str
    install_date: str            # raw Windows date string (e.g. 20260917)
    source: str                  # detection source, e.g. 'Registry uninstall (64-bit)'


@dataclass(frozen=True)
class ToolLocation:
    tool: str                    # canonical tool name, e.g. 'Python'
    exe_path: str
    version: str                 # '' = not yet determined
    install_dir: str
    publisher: str
    detection_source: str
    path_visible: bool


@dataclass(frozen=True)
class AiTool:
    name: str
    exe_path: str
    version: str
    install_dir: str
    detection_source: str


@dataclass(frozen=True)
class AiModel:
    runtime: str                 # which AI tool uses it
    file_path: str
    name: str
    size_bytes: int
