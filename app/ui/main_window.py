"""MainWindow — sidebar, header, and the stacked pages.

Pages are created once from the registry and reused; switching pages only
swaps the visible widget. The window owns the theme and applies it globally.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..config.settings import AppConfig
from ..services.service import SystemService
from .pages.registry import PAGES, create_page
from .sidebar import Sidebar
from .theme import apply_theme

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, service: SystemService, config: AppConfig) -> None:
        super().__init__()
        self._service = service
        self._config = config
        self._pages: dict[str, QWidget] = {}

        self.setWindowTitle(APP_NAME)
        self.resize(1180, 760)
        self.setMinimumSize(940, 620)

        root = QWidget()
        root.setObjectName("Root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.pageSelected.connect(self._on_page_selected)
        root_layout.addWidget(self.sidebar)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("Header")
        header.setFixedHeight(64)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 8, 24, 8)
        self._page_title = QLabel("Dashboard")
        self._page_title.setObjectName("PageTitle")
        self._page_subtitle = QLabel("")
        self._page_subtitle.setObjectName("PageSubtitle")
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(self._page_title)
        title_col.addWidget(self._page_subtitle)
        header_layout.addLayout(title_col)
        header_layout.addStretch(1)
        self._content_layout.addWidget(header)

        self._stack = QStackedWidget()
        self._content_layout.addWidget(self._stack, 1)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

        # Pages are built lazily on first visit so the window appears fast.
        # Only the dashboard is built up front.
        for page_id, _section, _title, _subtitle, _factory in PAGES:
            if page_id == "dashboard":
                page = create_page(page_id, self._service, self._config)
                if page is not None:
                    self._pages[page_id] = page
                    self._stack.addWidget(page)

        self.sidebar.select_page("dashboard")
        apply_theme(self, config.theme)

    def _on_page_selected(self, page_id: str) -> None:
        if page_id not in self._pages:
            page = create_page(page_id, self._service, self._config)
            if page is None:
                log.warning("Unknown page requested: %s", page_id)
                return
            self._pages[page_id] = page
            self._stack.addWidget(page)
        page = self._pages[page_id]
        self._stack.setCurrentWidget(page)
        for pid, _section, title, subtitle, _f in PAGES:
            if pid == page_id:
                self._page_title.setText(title)
                self._page_subtitle.setText(subtitle)
                break

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        log.info("Shutting down: stopping background collectors")
        self._service.shutdown()
        super().closeEvent(event)
