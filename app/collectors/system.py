"""SystemCollector — slow-changing machine facts (hostname, OS, CPU, RAM, boot)."""
from __future__ import annotations

import getpass
import logging
import platform

import psutil

from ..models.metrics import SystemInfo
from .base import BaseCollector
from ..models.metrics import CollectorResult, CollectorStatus

log = logging.getLogger(__name__)


def _registry_value(key_path: str, value_name: str) -> str | None:
    """Read one registry value (read-only, no admin required). None if unavailable."""
    try:
        import winreg  # Windows-only stdlib module

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            value, _type = winreg.QueryValueEx(key, value_name)
            return str(value)
    except OSError:
        return None


def windows_edition() -> str | None:
    """Windows product name, e.g. 'Windows 11 Home'."""
    return _registry_value(
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "ProductName"
    )


class SystemCollector(BaseCollector):
    """Collects hostname, Windows edition/version/build, CPU model, RAM, boot time."""

    label = "System"

    def collect(self) -> CollectorResult:
        uname = platform.uname()
        edition = windows_edition()
        vm = psutil.virtual_memory()

        info = SystemInfo(
            hostname=uname.node or "Unavailable",
            os_name=edition or uname.system or "Unavailable",
            os_version=uname.version or "Unavailable",
            os_build=platform.version() or "Unavailable",
            architecture=uname.machine or "Unavailable",
            cpu_model=self._cpu_model(),
            cpu_cores_logical=psutil.cpu_count(logical=True) or 0,
            cpu_cores_physical=psutil.cpu_count(logical=False) or 0,
            ram_total_gb=round(vm.total / (1024 ** 3), 2),
            boot_time=psutil.boot_time(),
            current_user=getpass.getuser() or "Unavailable",
        )
        return CollectorResult(
            status=CollectorStatus.SUCCESS,
            data=info,
            meta=self._meta(
                source="psutil + Python platform module + Windows registry (read-only)",
                method=(
                    "Uses psutil (virtual_memory, cpu_count, boot_time), Python's platform "
                    "module, and reads registry values under HKLM\\SOFTWARE\\Microsoft"
                    "\\Windows NT\\CurrentVersion and HKLM\\HARDWARE\\DESCRIPTION\\System"
                    "\\CentralProcessor\\0 via the winreg API. Read-only; no admin rights."
                ),
            ),
        )

    @staticmethod
    def _cpu_model() -> str:
        """CPU name from the registry; 'Unavailable' if unreadable."""
        value = _registry_value(
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString"
        )
        return value or "Unavailable"
