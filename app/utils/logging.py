"""Structured application logging.

Log lines use a ``key=value`` friendly format so they can be grepped or parsed
later when reconstructing what happened during an experiment session.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from types import TracebackType

LOGGER_NAME = "crosshair_research"
_LOG_FORMAT = "%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s"


def configure_logging(logs_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Configure console + rotating file logging and return the root app logger."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(_LOG_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        logs_dir / "app.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger of the application logger."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def install_excepthook(logger: logging.Logger) -> None:
    """Log any uncaught exception instead of letting it vanish."""
    previous_hook = sys.excepthook

    def _hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            previous_hook(exc_type, exc_value, exc_tb)
            return
        logger.critical("uncaught_exception", exc_info=(exc_type, exc_value, exc_tb))
        previous_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
