"""
charon/config/logging.py
System Version: v0.2.0 | File Revision: 1.1.0

Module: config/logging — Central Logging Configuration for Charon.

Configures dual stream logging: stdout for systemd/journalctl and rotating file handlers
for main daemon events and error isolation.
Enforces standard lowercase dot-notation logger inheritance for all charon submodules,
dynamic skills, and Work Contracts while suppressing noise from third-party dependencies.
"""

import logging
from logging.handlers import RotatingFileHandler
import sys
from typing import Dict, Optional

from charon.config.paths import ERROR_LOG_FILE, LOGS_DIR, MAIN_LOG_FILE

# Default log levels for noisy third-party dependencies
THIRD_PARTY_LOG_LEVELS: Dict[str, int] = {
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "urllib3": logging.WARNING,
    "chromadb": logging.WARNING,
    "asyncio": logging.WARNING,
    "matplotlib": logging.WARNING,
    "click": logging.WARNING,
}


def setup_logging(
    level: int = logging.INFO,
    module_overrides: Optional[Dict[str, int]] = None,
) -> None:
    """Configures system-wide logging with stdout and rotating file output."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Prevent duplicate handlers across re-initialization calls
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # 1. Console Stream Handler (captured by systemd / journalctl / terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
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

    # 4. Mute noisy third-party libraries unless overridden
    for module_name, default_level in THIRD_PARTY_LOG_LEVELS.items():
        logging.getLogger(module_name).setLevel(default_level)

    # 5. Apply custom granular overrides (e.g., {"charon.core.skills": logging.DEBUG})
    if module_overrides:
        for module_name, custom_level in module_overrides.items():
            logging.getLogger(module_name).setLevel(custom_level)


def set_logger_level(module_name: str, level: int) -> None:
    """Helper function to dynamically adjust logging level for a specific namespace at runtime."""
    logger = logging.getLogger(module_name)
    logger.setLevel(level)
    logger.info(f"[LOGGING] Set namespace '{module_name}' level to {logging.getLevelName(level)}")