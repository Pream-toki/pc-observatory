"""ApplicationsCollector — installed software from the Windows registry.

Reads the standard uninstall keys (the same place 'Installed Apps' and every
uninstaller look). Strictly read-only via the winreg API — no subprocess, no
admin rights. The registry key path is kept as the stable identity so
first-seen/last-seen history works across rescans.

Honesty notes:
- Entries with no name are skipped (they are uninstaller stubs, not apps).
- 'System Components' (KB hotfixes etc.) are skipped to keep the list human.
"""
from __future__ import annotations

import logging
import winreg

from ..models.inventory import ApplicationInfo
from ..models.metrics import CollectorResult, CollectorStatus
from .base import BaseCollector

log = logging.getLogger(__name__)

_UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
_SOURCES = [
    (0x80000002, "64-bit"),   # HKLM, KEY_WOW64_64KEY view
    (0x80000002, "32-bit"),   # HKLM, KEY_WOW64_32KEY view
    (0x80000001, "user"),     # HKCU
]
_SKIP_PREFIXES = ("KB",)


def _read_str(key, name: str) -> str:
    try:
        value, _type = winreg.QueryValueEx(key, name)
        return str(value).strip() if value is not None else ""
    except OSError:
        return ""


class ApplicationsCollector(BaseCollector):
    label = "Applications"

    def collect(self) -> CollectorResult:
        apps: list[ApplicationInfo] = []
        errors: list[str] = []
        for hive, view in _SOURCES:
            view_label = f"Registry uninstall ({view})"
            access = winreg.KEY_READ | (
                winreg.KEY_WOW64_64KEY if view == "64-bit" else
                winreg.KEY_WOW64_32KEY if view == "32-bit" else 0
            )
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE if hive == 0x80000002
                                    else winreg.HKEY_CURRENT_USER,
                                    _UNINSTALL_KEY, 0, access) as root:
                    subkeys = winreg.QueryInfoKey(root)[0]
                    for i in range(subkeys):
                        try:
                            sub_name = winreg.EnumKey(root, i)
                            key_path = f"{_UNINSTALL_KEY}\\{sub_name}"
                            with winreg.OpenKey(root, sub_name) as key:
                                name = _read_str(key, "DisplayName")
                                if not name:
                                    continue
                                if name.startswith(_SKIP_PREFIXES) and \
                                        "Update" in _read_str(key, "DisplayName"):
                                    continue
                                system_component = _read_str(key, "SystemComponent")
                                if system_component == "1":
                                    continue
                                apps.append(ApplicationInfo(
                                    key_path=key_path,
                                    name=name,
                                    version=_read_str(key, "DisplayVersion"),
                                    publisher=_read_str(key, "Publisher"),
                                    install_location=_read_str(key, "InstallLocation"),
                                    install_date=_read_str(key, "InstallDate"),
                                    source=view_label,
                                ))
                        except OSError as exc:
                            errors.append(f"{sub_name}: {exc}")
            except OSError as exc:
                errors.append(f"{view_label}: {exc}")

        status = CollectorStatus.SUCCESS if apps or not errors else CollectorStatus.PARTIAL
        if errors and apps:
            status = CollectorStatus.PARTIAL
        detail = "; ".join(errors[:3]) if errors else ""
        return CollectorResult(
            status=status,
            data=apps,
            detail=detail,
            meta=self._meta(
                source="Windows registry: HKLM/HKCU Software\\Microsoft\\Windows"
                       "\\CurrentVersion\\Uninstall (read-only)",
                method=(
                    "Enumerates the standard Windows uninstall registry keys — the "
                    "same official list that 'Settings > Apps' and 'Programs and "
                    "Features' are built from. Reads DisplayName, DisplayVersion, "
                    "Publisher, InstallLocation and InstallDate via the winreg API. "
                    "Hidden system components and nameless uninstaller stubs are "
                    "skipped. Read-only; nothing is modified; no admin rights."
                ),
            ),
        )
