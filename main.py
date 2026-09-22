"""PC Observatory — application entry point.

Startup order matters: logging first (so anything after it is recorded),
then config, then the database, then a splash window, then the heavy
imports in small chunks, then background collection, then the window.

Cold-start note: the first import of the heavy modules (psutil, numpy,
pyqtgraph, the page modules) can take tens of seconds while Windows
real-time scanning touches every DLL. The splash is therefore shown BEFORE
those imports and the event loop is pumped between import chunks, so the
user sees the app is starting instead of a dead double-click. All Qt work
stays on the main thread — background-thread import tricks crash PySide6
(fail-fast 0xc0000409 in Qt6Core) on this setup and were removed.
"""
from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from app import APP_NAME, APP_TAGLINE, __version__
from app.config.settings import AppConfig, project_root
from app.database.connection import configure as configure_db
from app.database.connection import get_connection
from app.database.migrations import migrate
from app.utils.errors import install_excepthook
from app.utils.logging_setup import setup_logging

log = logging.getLogger("pc_observatory")


def _make_splash() -> QSplashScreen:
    """A simple dark splash shown while heavy modules load."""
    px = QPixmap(460, 240)
    px.fill(QColor("#141821"))
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#e8eaf0"))
    title = QFont("Segoe UI", 20)
    title.setBold(True)
    painter.setFont(title)
    painter.drawText(px.rect().adjusted(20, 40, -20, -90),
                     Qt.AlignmentFlag.AlignHCenter, APP_NAME)
    sub = QFont("Segoe UI", 9)
    painter.setFont(sub)
    painter.setPen(QColor("#9aa3b2"))
    painter.drawText(px.rect().adjusted(20, 100, -20, -60),
                     Qt.AlignmentFlag.AlignHCenter | Qt.TextWordWrap, APP_TAGLINE)
    painter.setPen(QColor("#5b8def"))
    painter.drawText(px.rect().adjusted(20, -50, -20, -22),
                     Qt.AlignmentFlag.AlignHCenter, "Starting…")
    painter.end()
    splash = QSplashScreen(px)
    splash.setWindowTitle(APP_NAME)
    return splash


def _pump(splash: QSplashScreen, app: QApplication, message: str) -> None:
    """Keep the splash honest between import chunks."""
    splash.showMessage(message,
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                       QColor("#9aa3b2"))
    app.processEvents()


def main() -> int:
    install_excepthook()
    log_file = setup_logging(project_root() / "logs")
    log.info("Starting %s v%s", APP_NAME, __version__)

    config = AppConfig.load()
    db_path = config.config_dir / "observatory.db"
    configure_db(db_path)
    schema_version = migrate(get_connection())
    log.info("Database ready (schema v%d) at %s", schema_version, db_path)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)

    # Splash FIRST: something is on screen within ~1-2 s even while Windows
    # real-time scanning makes the first heavy import slow.
    splash = _make_splash()
    splash.show()
    app.processEvents()
    log.info("Splash shown")

    # Heavy imports, chunked so the splash keeps repainting in between.
    _pump(splash, app, "Loading system libraries…")
    import psutil  # noqa: F401 — primes the biggest DLL chain first
    from app.services import service as _service_mod  # noqa: F401

    _pump(splash, app, "Loading charts…")
    import pyqtgraph  # noqa: F401
    from app.widgets import charts as _charts_mod  # noqa: F401

    _pump(splash, app, "Preparing interface…")
    from app.ui.main_window import MainWindow

    _pump(splash, app, "Starting collectors…")
    from app.services.service import SystemService
    service = SystemService(config)

    _pump(splash, app, "Building interface…")
    window = MainWindow(service, config)  # applies the saved theme
    window.show()
    splash.finish(window)
    log.info("UI ready — log file: %s", log_file)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
