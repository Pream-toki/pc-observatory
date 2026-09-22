"""Tests for the PATH command resolver (read-only, temporary folders)."""
from __future__ import annotations

from pathlib import Path

from app.utils.command_resolver import resolve_command


def _make_dir_with_exe(tmp_path: Path, dirname: str, exe_name: str) -> Path:
    d = tmp_path / dirname
    d.mkdir(parents=True, exist_ok=True)
    (d / exe_name).write_bytes(b"MZ")  # content irrelevant; existence is what counts
    return d


def test_resolves_executable_on_path(tmp_path, monkeypatch):
    d = _make_dir_with_exe(tmp_path, "tools", "python.exe")
    monkeypatch.setenv("PATH", str(d))
    matches = resolve_command("python")
    assert matches == [d / "python.exe"]


def test_windows_lookup_order_first_dir_wins(tmp_path, monkeypatch):
    first = _make_dir_with_exe(tmp_path, "first", "git.exe")
    second = _make_dir_with_exe(tmp_path, "second", "git.exe")
    monkeypatch.setenv("PATH", f"{first};{second}")
    matches = resolve_command("git")
    assert matches[0] == first / "git.exe"
    assert matches[1] == second / "git.exe"


def test_pathext_resolution_for_cmd_files(tmp_path, monkeypatch):
    d = _make_dir_with_exe(tmp_path, "npm", "npm.cmd")
    monkeypatch.setenv("PATH", str(d))
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    matches = resolve_command("npm")
    assert matches == [d / "npm.cmd"]


def test_missing_command_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert resolve_command("definitely-not-here-xyz") == []


def test_names_with_separators_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert resolve_command(r"C:\evil\..\..\windows\system32\cmd.exe") == []
    assert resolve_command("") == []
