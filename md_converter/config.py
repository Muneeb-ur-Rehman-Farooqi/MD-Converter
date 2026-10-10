"""Application paths and logging setup for MD Converter."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "MDConverter"


def get_app_data_dir() -> Path:
    """Return the per-user application data directory."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    return Path(appdata) / APP_NAME


def get_logs_dir() -> Path:
    """Return the directory where log files are stored."""
    return get_app_data_dir() / "logs"


def get_db_path() -> Path:
    """Return the path to the history database."""
    return get_app_data_dir() / "history.db"


def get_default_library_dir() -> Path:
    """Return the default document library folder."""
    # TODO(F12): Windows can redirect Documents, e.g. to OneDrive; resolve it
    # properly with the Known Folder API when the library feature is built.
    return Path.home() / "Documents" / "MDConverter"


def ensure_app_dirs() -> None:
    """Create the application data and log directories if needed."""
    get_app_data_dir().mkdir(parents=True, exist_ok=True)
    get_logs_dir().mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    """Configure the md_converter logger with a rotating file handler."""
    ensure_app_dirs()

    logger = logging.getLogger("md_converter")
    logger.setLevel(logging.INFO)

    log_path = get_logs_dir() / "md_converter.log"

    for handler in logger.handlers:
        if (
            isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename) == log_path
        ):
            return

    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_048_576,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    )
    logger.addHandler(handler)