"""ToolLocationsCollector — "where exactly is my software installed?" (spec §11-13).

Strategy: search well-known install roots for the executables of common
development/AI tools, plus check PATH visibility. **Never executes the
tools** — that could launch GUIs or run arbitrary code; versions are read
from file metadata or left 'Pending' until a safe source provides them.

The CommandResolver answers "which python does Windows actually use?" by
searching PATH in the same order Windows would.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from ..models.inventory import ToolLocation
from ..models.metrics import CollectorResult, CollectorStatus
from .base import BaseCollector

log = logging.getLogger(__name__)

# (canonical name, exe filename, publisher, extra search dirs)
_TOOL_DEFS = [
    ("Python", "python.exe", "Python Software Foundation", [
        r"%LocalAppData%\Programs\Python", r"%LocalAppData%\Python",
        r"C:\Python*", r"%LocalAppData%\Microsoft\WindowsApps",
    ]),
    ("Git", "git.exe", "Git for Windows", [r"%ProgramFiles%\Git\cmd", r"%ProgramFiles(x86)%\Git\cmd"]),
    ("Node.js", "node.exe", "OpenJS Foundation", [r"%ProgramFiles%\nodejs"]),
    ("npm", "npm.cmd", "npm, Inc.", [r"%ProgramFiles%\nodejs", r"%AppData%\npm"]),
    ("PowerShell 7", "pwsh.exe", "Microsoft", [r"%ProgramFiles%\PowerShell\*"]),
    ("Windows PowerShell", "powershell.exe", "Microsoft", [r"%SystemRoot%\System32\WindowsPowerShell\v1.0"]),
    ("VS Code", "Code.exe", "Microsoft", [r"%LocalAppData%\Programs\Microsoft VS Code"]),
    ("Godot", "Godot.exe", "Godot Engine", [r"C:\dev\Godot*", r"%LocalAppData%\Programs\Godot*"]),
    ("Ollama", "ollama.exe", "Ollama", [r"%LocalAppData%\Programs\Ollama"]),
    ("Docker", "docker.exe", "Docker Inc.", [r"%ProgramFiles%\Docker\Docker\resources\bin"]),
]


def _expand(pattern: str) -> list[Path]:
    import glob
    expanded = os.path.expandvars(pattern)
    return [Path(p) for p in glob.glob(expanded)]


def _search_dirs(patterns: list[str]) -> list[Path]:
    dirs: list[Path] = []
    for pattern in patterns:
        dirs.extend(_expand(pattern))
    return dirs


class ToolLocationsCollector(BaseCollector):
    label = "Tool Locations"

    def collect(self) -> CollectorResult:
        path_dirs = [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
        tools: list[ToolLocation] = []

        for name, exe, publisher, extra_dirs in _TOOL_DEFS:
            candidates: set[Path] = set()
            for directory in _search_dirs(extra_dirs):
                candidate = directory / exe
                if candidate.is_file():
                    candidates.add(candidate)
            where = shutil.which(exe)
            if where:
                candidates.add(Path(where))

            for exe_path in sorted(candidates):
                try:
                    resolved = exe_path.resolve()
                except OSError:
                    resolved = exe_path
                tools.append(ToolLocation(
                    tool=name,
                    exe_path=str(resolved),
                    version="",  # filled by a later safe source; never faked
                    install_dir=str(resolved.parent),
                    publisher=publisher,
                    detection_source="Filesystem scan of known install locations + PATH",
                    path_visible=any(
                        str(resolved.parent).lower() == str(d).lower()
                        for d in path_dirs
                    ),
                ))

        return CollectorResult(
            status=CollectorStatus.SUCCESS,
            data=tools,
            meta=self._meta(
                source="Filesystem scan of known install roots + PATH environment",
                method=(
                    "Looks for the executables of well-known tools (Python, Git, "
                    "Node.js, VS Code, Ollama, …) inside their standard install "
                    "directories and checks whether each found location is on PATH. "
                    "Files are only read for existence — tools are never executed. "
                    "Read-only; no admin rights."
                ),
            ),
        )
