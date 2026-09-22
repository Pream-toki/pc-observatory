"""Global error handling.

Qt swallows exceptions raised inside slots unless we install an excepthook.
This hook logs the full traceback so nothing fails silently, and keeps the
app running (one broken slot must not take the whole window down).
"""
from __future__ import annotations

import logging
import sys
import traceback


def install_excepthook() -> None:
    def hook(exc_type, exc_value, exc_tb) -> None:
        logging.getLogger("pc_observatory").critical(
            "Uncaught exception:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = hook
