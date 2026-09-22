"""Sidebar — grouped navigation.

Sections and entries are generated from ui.pages.PAGES, so adding a page in a
later phase automatically adds its navigation entry. Buttons are checkable
and exclusive; the main window listens for selection changes.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_TAGLINE
from .pages.registry import PAGES


class Sidebar(QFrame):
    pageSelected = Signal(str)  # page_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(230)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 16, 14, 16)
        outer.setSpacing(2)

        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        outer.addWidget(title)
        tagline = QLabel(APP_TAGLINE)
        tagline.setObjectName("AppTagline")
        tagline.setWordWrap(True)
        outer.addWidget(tagline)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self._nav_layout = QVBoxLayout(inner)
        self._nav_layout.setContentsMargins(0, 4, 0, 4)
        self._nav_layout.setSpacing(2)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._build_buttons()

        outer.addStretch(1)
        version = QLabel("Phase 1 — Foundation")
        version.setObjectName("AppTagline")
        outer.addWidget(version)

    def _build_buttons(self) -> None:
        current_section: str | None = None
        for page_id, section, title, _subtitle, _factory in PAGES:
            if section != current_section:
                current_section = section
                header = QLabel(section.upper())
                header.setObjectName("NavSection")
                self._nav_layout.addWidget(header)
            btn = QPushButton(title)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(self.cursor())
            self._group.addButton(btn)
            btn.clicked.connect(lambda _=False, pid=page_id: self.pageSelected.emit(pid))
            self._nav_layout.addWidget(btn)

    def select_page(self, page_id: str) -> None:
        """Programmatic selection (used for the default page at startup)."""
        for page_id_arg, _s, title, _sub, _f in PAGES:
            if page_id_arg == page_id:
                for btn in self._group.buttons():
                    if btn.text() == title:
                        btn.setChecked(True)
                        self.pageSelected.emit(page_id)
                        return
