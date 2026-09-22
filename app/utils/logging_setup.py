"""Logging configuration.

Everything goes to a rotating file in the project's ``logs/`` directory and
also to stderr. A ``log_errors`` decorator records when a whole method fails
without swallowing the traceback (the caller still receives ``None``).
"""
from __future__ import annotations

import functools
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any, Callable, TypeVar

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
T = TypeVar("T")


def setup_logging(log_dir: Path, level: int = logging.INFO) -> Path:
    """Install a rotating file handler + console handler. Returns the log file path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "pc_observatory.log"

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):          # avoid duplicates on re-run
        root.removeHandler(handler)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(file_handler)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(console)
    return log_file


def log_errors(_fn: Callable[..., T] | None = None, *, default: Any = None) -> Callable[..., T]:
    """Decorator: log a full traceback if the function raises, then return ``default``.

    Usage:  @log_errors            (returns None on error)
            @log_errors(default=[])
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception:
                logging.getLogger(fn.__module__).exception(
                    "%s.%s failed", fn.__qualname__, fn.__name__
                )
                return default
        return wrapper

    if _fn is not None:              # used as @log_errors without parentheses
        return decorator(_fn)
    return decorator
