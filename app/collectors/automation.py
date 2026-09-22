"""AutomationCollector — services, startup entries, scheduled tasks (spec §18-20).

Strictly read-only:
- Services via psutil (win_service_iter) — the same list services.msc shows.
- Startup via the documented HKCU/HKLM Run keys and the two Startup folders.
- Scheduled tasks via one fixed PowerShell query (Get-ScheduledTask). The
  command is a constant string — no user input is ever inserted, so there is
  no injection surface. We never Start/Stop/Enable/Delete anything.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess  # noqa: S404 - fixed argument list, read-only query below
from pathlib import Path

import psutil

from ..models.metrics import CollectorResult, CollectorStatus
from .base import BaseCollector

log = logging.getLogger(__name__)

_TASK_QUERY = (
    "Get-ScheduledTask | ForEach-Object { "
    "$t = $_; "
    "[PSCustomObject]@{ "
    "path = ($t.TaskPath + $t.TaskName); "
    "state = [string]$t.State; "
    "author = [string]$t.Author; "
    "exe = (@($t.Actions) | ForEach-Object { [string]$_.Execute }) -join '; '; "
    "args = (@($t.Actions) | ForEach-Object { [string]$_.Arguments }) -join '; '; "
    "trigger = (@($t.Triggers) | ForEach-Object { [string]$_.StartBoundary }) -join '; ' "
    "} } | ConvertTo-Json -Compress -Depth 3"
)


def _services() -> list[dict]:
    rows: list[dict] = []
    for svc in psutil.win_service_iter():
        try:
            info = svc.as_dict()
        except (psutil.Error, OSError):
            # Some services have broken/removed config entries; keep the name.
            try:
                info = {"name": svc.name(), "status": "unknown"}
            except (psutil.Error, OSError):
                continue
        rows.append({
            "name": info.get("name") or "",
            "display_name": info.get("display_name") or "",
            "status": info.get("status") or "unknown",
            "start_type": info.get("start_type") or "unknown",
            "account": info.get("username") or "",
            "exe_path": info.get("binpath") or "",
            "description": info.get("description") or "",
        })
    return rows


def _startup_entries() -> list[dict]:
    entries: list[dict] = []
    import winreg

    run_keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
         "Registry HKCU Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run",
         "Registry HKLM Run"),
    ]
    for hive, path, source in run_keys:
        try:
            with winreg.OpenKey(hive, path) as key:
                index = 0
                while True:
                    try:
                        name, value, _type = winreg.EnumValue(key, index)
                        entries.append({
                            "source": source,
                            "entry_name": str(name),
                            "command": str(value),
                        })
                        index += 1
                    except OSError:
                        break
        except OSError:
            continue  # key missing on some systems — fine

    startup_folders = [
        (Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")),
         "Startup folder (user)"),
        (Path(os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup")),
         "Startup folder (all users)"),
    ]
    for folder, source in startup_folders:
        if folder.is_dir():
            for item in folder.iterdir():
                entries.append({
                    "source": source,
                    "entry_name": item.name,
                    "command": str(item),
                })
    return entries


def _scheduled_tasks() -> list[dict]:
    """One fixed read-only PowerShell query; output parsed as JSON."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _TASK_QUERY],
            capture_output=True, text=True, timeout=60, shell=False, check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        log.info("Scheduled task query unavailable: %s", exc)
        return []
    stdout = (proc.stdout or "").strip()
    if not stdout:
        return []
    try:
        parsed = json.loads(stdout)
    except ValueError:
        log.info("Scheduled task query returned non-JSON output")
        return []
    if isinstance(parsed, dict):
        parsed = [parsed]
    rows: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        rows.append({
            "task_path": str(item.get("path") or ""),
            "status": str(item.get("state") or "Unknown"),
            "trigger_info": str(item.get("trigger") or ""),
            "action_exe": str(item.get("exe") or ""),
            "action_args": str(item.get("args") or ""),
            "author": str(item.get("author") or ""),
        })
    return rows


class AutomationCollector(BaseCollector):
    label = "Automation"

    def collect(self) -> CollectorResult:
        data = {
            "services": _services(),
            "startup": _startup_entries(),
            "tasks": _scheduled_tasks(),
        }
        total = len(data["services"]) + len(data["startup"]) + len(data["tasks"])
        status = CollectorStatus.SUCCESS if total else CollectorStatus.PARTIAL
        return CollectorResult(
            status=status,
            data=data,
            detail="" if total else "No automation entries could be read.",
            meta=self._meta(
                source="psutil services API + registry Run keys + Startup folders"
                       " + Get-ScheduledTask (fixed read-only query)",
                method=(
                    "Services come from psutil's Windows service API (same list as "
                    "services.msc). Startup entries come from the documented Run "
                    "registry keys and Startup folders. Scheduled tasks come from "
                    "one fixed, read-only PowerShell query whose command string "
                    "never contains user input. Nothing is started, stopped, "
                    "enabled, disabled, or deleted by this app."
                ),
            ),
        )
