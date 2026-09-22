"""Settings page — every control writes through AppConfig.save(); nothing else
touches the config file. Theme applies immediately; collection intervals
restart the background workers on save.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...config.settings import THEME_CHOICES
from ...services.service import SystemService
from ...utils.format import fmt_datetime

log = logging.getLogger(__name__)


class SettingsPage(QWidget):
    def __init__(self, service: SystemService, config) -> None:
        super().__init__()
        self._service = service
        self._config = config

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(14)

        outer.addWidget(self._section_card("Appearance", self._appearance_form()))
        outer.addWidget(self._section_card("Background collection", self._collection_form()))
        outer.addWidget(self._section_card("Data storage", self._storage_form()))
        outer.addWidget(self._section_card("Diagnostics", self._diagnostics_form()))
        outer.addStretch(1)

    # ---- small builders ---------------------------------------------------
    def _section_card(self, title: str, form: QFormLayout) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        heading = QLabel(title.upper())
        heading.setObjectName("CardTitle")
        layout.addWidget(heading)
        layout.addSpacing(4)
        layout.addLayout(form)
        return card

    def _appearance_form(self) -> QFormLayout:
        form = QFormLayout()
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(list(THEME_CHOICES))
        self._theme_combo.setCurrentText(self._config.theme)
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)
        form.addRow("Theme", self._theme_combo)
        return form

    def _collection_form(self) -> QFormLayout:
        form = QFormLayout()
        self._metrics_spin = QDoubleSpinBox()
        self._metrics_spin.setRange(1.0, 60.0)
        self._metrics_spin.setSuffix(" s")
        self._metrics_spin.setDecimals(1)
        self._metrics_spin.setSingleStep(0.5)
        self._metrics_spin.setValue(self._config.metrics_interval_s)
        form.addRow("Live metrics every", self._metrics_spin)

        self._system_spin = QDoubleSpinBox()
        self._system_spin.setRange(60.0, 3600.0)
        self._system_spin.setSuffix(" s")
        self._system_spin.setSingleStep(30.0)
        self._system_spin.setValue(self._config.system_info_interval_s)
        form.addRow("System facts every", self._system_spin)

        apply_btn = QPushButton("Apply collection settings")
        apply_btn.clicked.connect(self._on_apply_collection)
        form.addRow("", apply_btn)
        return form

    def _storage_form(self) -> QFormLayout:
        form = QFormLayout()
        self._retention_spin = QSpinBox()
        self._retention_spin.setRange(1, 3650)
        self._retention_spin.setSuffix(" days")
        self._retention_spin.setValue(self._config.retention_days)
        form.addRow("Keep metric history for", self._retention_spin)

        apply_btn = QPushButton("Apply and clean up now")
        apply_btn.clicked.connect(self._on_apply_retention)
        form.addRow("", apply_btn)
        return form

    def _diagnostics_form(self) -> QFormLayout:
        form = QFormLayout()
        buttons_row = QHBoxLayout()
        logs_btn = QPushButton("Open logs folder")
        logs_btn.clicked.connect(self._open_logs)
        data_btn = QPushButton("Open data folder")
        data_btn.clicked.connect(self._open_data)
        buttons_row.addWidget(logs_btn)
        buttons_row.addWidget(data_btn)
        buttons_row.addStretch(1)
        form.addRow(buttons_row)

        self._db_info = QLabel("Database: loading…")
        self._db_info.setStyleSheet("color: #8b95a3;")
        form.addRow(self._db_info)
        self._refresh_db_info()
        return form

    # ---- handlers -----------------------------------------------------------
    def _on_theme_changed(self, theme: str) -> None:
        from ..theme import apply_theme  # local import avoids a cycle

        self._config.theme = theme
        self._config.save()
        apply_theme(self.window(), theme)
        log.info("Theme changed to %s", theme)

    def _on_apply_collection(self) -> None:
        self._config.metrics_interval_s = float(self._metrics_spin.value())
        self._config.system_info_interval_s = float(self._system_spin.value())
        self._config.save()
        self._service.restart_workers(self._config)
        log.info("Collection intervals applied")

    def _on_apply_retention(self) -> None:
        self._config.retention_days = int(self._retention_spin.value())
        self._config.save()
        self._service.apply_retention()
        self._refresh_db_info()
        log.info("Retention set to %s days", self._config.retention_days)

    def _open_logs(self) -> None:
        from ...config.settings import project_root

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(project_root() / "logs")))

    def _open_data(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._config.config_dir)))

    def _refresh_db_info(self) -> None:
        try:
            from ...database.connection import get_connection

            row = get_connection().execute(
                "SELECT COUNT(*) FROM metric_samples"
            ).fetchone()
            count = int(row[0])
            self._db_info.setText(
                f"Database: {self._config.config_path.parent / 'observatory.db'} · "
                f"{count} stored metric samples"
            )
        except Exception as exc:  # noqa: BLE001 — diagnostics must never crash the page
            self._db_info.setText(f"Database status: {exc}")

    def showEvent(self, event) -> None:  # noqa: N802 — Qt naming
        self._refresh_db_info()
        super().showEvent(event)
