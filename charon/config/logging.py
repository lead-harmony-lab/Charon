"""
charon/config/logging.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: config/logging — Central Logging Configuration for Charon.

Configures dual stream logging: stdout for systemd/journalctl and rotating file handlers
for main daemon events and error isolation.
"""

import logging
from logging.handlers import RotatingFileHandler
import sys

from charon.config.paths import ERROR_LOG_FILE, LOGS_DIR, MAIN_LOG_FILE


def setup_logging(level: int = logging.INFO) -> None:
    """Configures system-wide logging with stdout and rotating file output."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers if setup_logging is invoked multiple times
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # 1. Console Stream Handler (captured by systemd/journalctl)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. Main Rotating File Handler (5 MB max, 3 backups)
    main_file_handler = RotatingFileHandler(
        MAIN_LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    main_file_handler.setFormatter(formatter)
    main_file_handler.setLevel(logging.INFO)
    root_logger.addHandler(main_file_handler)

    # 3. Dedicated Error File Handler (2 MB max, 2 backups)
    error_file_handler = RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    error_file_handler.setFormatter(formatter)
    error_file_handler.setLevel(logging.WARNING)
    root_logger.addHandler(error_file_handler)
