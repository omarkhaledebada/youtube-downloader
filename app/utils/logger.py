"""Centralised application logging.

Writes to a rotating log file under the user's local application-data
directory (or ./logs when that is not resolvable) so unhandled errors
can be diagnosed after the fact without a console attached.
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def _log_directory() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        log_dir = os.path.join(base, "YouTubeDownloader", "logs")
    else:
        log_dir = os.path.join(os.path.expanduser("~"), ".youtube_downloader", "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("ytdownloader")
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        log_path = os.path.join(_log_directory(), "app.log")
        file_handler = RotatingFileHandler(
            log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        pass  # fall back to console-only logging if the file can't be created

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("ytdownloader")
