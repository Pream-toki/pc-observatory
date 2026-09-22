"""PythonProjectCollector — discover Python projects (spec §15).

Shallow scan (depth-capped) of configured project directories only — never
the whole disk. A folder counts as a project when it contains Python markers
(.py files, requirements.txt, pyproject.toml, .venv, .git). No code is ever
executed; Git status is limited to 'has .git folder' (honest, no git calls).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from ..config.settings import AppConfig
from ..models.metrics import CollectorResult, CollectorStatus
from .base import BaseCollector

log = logging.getLogger(__name__)

_DEFAULT_ROOTS = [
    r"%USERPROFILE%\Documents",
    r"%USERPROFILE%\dev",
    r"C:\dev",
    r"C:\ai tasks",
]
_MAX_DEPTH = 3
_MAX_PROJECTS = 200
_PROJECT_MARKERS = ("requirements.txt", "pyproject.toml", "setup.py")


class PythonProjectCollector(BaseCollector):
    label = "Python Projects"

    def __init__(self, run_repo=None, roots: list[str] | None = None,
                 config: "AppConfig | None" = None) -> None:
        super().__init__(run_repo)
        if config is not None and config.project_dirs:
            roots = list(config.project_dirs)
        self._roots = roots or _DEFAULT_ROOTS

    def collect(self) -> CollectorResult:
        projects: list[dict] = []
        skipped_roots: list[str] = []
        for root_pattern in self._roots:
            root = Path(os.path.expandvars(root_pattern))
            if not root.is_dir():
                skipped_roots.append(str(root))
                continue
            self._scan(root, root, 0, projects)
            if len(projects) >= _MAX_PROJECTS:
                log.warning("Project scan capped at %d", _MAX_PROJECTS)
                break

        status = CollectorStatus.SUCCESS if projects or not skipped_roots \
            else CollectorStatus.PARTIAL
        detail = f"Not present: {', '.join(skipped_roots)}" if skipped_roots else ""
        return CollectorResult(
            status=status,
            data=projects,
            detail=detail,
            meta=self._meta(
                source="Shallow filesystem scan of configured project directories",
                method=(
                    "Walks the configured project folders (Documents, C:\\dev, …) up "
                    "to 3 levels deep looking for Python project markers: .py "
                    "files, requirements.txt, pyproject.toml, setup.py, .venv, "
                    ".git. Only names, sizes and timestamps are read — project "
                    "code is never executed. Configure the scanned folders in "
                    "later Settings phases; the whole disk is never scanned."
                ),
            ),
        )

    def _scan(self, root: Path, current: Path, depth: int, out: list[dict]) -> None:
        if depth > _MAX_DEPTH or len(out) >= _MAX_PROJECTS:
            return
        try:
            children = list(current.iterdir())
        except OSError:
            return
        py_count = sum(1 for c in children if c.suffix == ".py" and c.is_file())
        has_venv = any(c.name in (".venv", "venv") and c.is_dir() for c in children)
        has_git = (current / ".git").exists()
        has_req = any(c.name in _PROJECT_MARKERS for c in children)

        if py_count >= 3 or has_req or has_venv:
            try:
                last_modified = max(
                    (c.stat().st_mtime for c in children if c.is_file()),
                    default=current.stat().st_mtime,
                )
            except OSError:
                last_modified = 0.0
            out.append({
                "path": str(current),
                "name": current.name or str(current),
                "py_files": py_count,
                "has_venv": int(has_venv),
                "has_git": int(has_git),
                "has_requirements": int(has_req),
                "last_modified": last_modified,
            })
            # Don't nest-scan inside a detected project (venvs would explode it).
            return
        for child in children:
            if child.is_dir() and not child.name.startswith("."):
                self._scan(root, child, depth + 1, out)
