"""Command resolution — "which python does Windows actually use?" (spec §12).

Implements the same lookup order Windows uses for a bare command name:
1. The command's own directory (if the name contains a separator) — not needed here.
2. Each PATH directory in order, for each PATHEXT extension in order
   (.COM, .EXE, .BAT, .CMD, ...).

Read-only: resolves and reports; never executes.
"""
from __future__ import annotations

import os
from pathlib import Path


def pathext_list() -> list[str]:
    raw = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD;.VBS;.JS;.WSH;.MSC")
    return [ext.upper() for ext in raw.split(";") if ext]


def resolve_command(name: str) -> list[Path]:
    """All PATH matches for a command name, in Windows lookup order.

    Returns every match (not just the first) so the UI can show ambiguity —
    e.g. two Pythons both visible on PATH, with the first one winning.
    """
    name = name.strip().strip('"')
    if not name or os.sep in name or "/" in name:
        return []
    lowered = name.lower()
    has_ext = Path(name).suffix.lower() in [e.lower() for e in pathext_list()]

    matches: list[Path] = []
    for dir_text in os.environ.get("PATH", "").split(os.pathsep):
        directory = Path(dir_text) if dir_text else Path(".")
        if not directory.is_dir():
            continue
        if has_ext:
            candidate = directory / name
            if candidate.is_file():
                matches.append(candidate)
        else:
            for ext in pathext_list():
                candidate = directory / f"{name}{ext.lower()}"
                if candidate.is_file():
                    matches.append(candidate)
                    break  # one match per directory, like Windows
    return matches
