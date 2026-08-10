"""
charon/config/__init__.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Package-level Configuration Entry Point.
Centralizes exports from paths, settings, and logging for clean import syntax
across the Charon application stack.
"""

from charon.config.logging import setup_logging
from charon.config.paths import (
    BASE_DIR,
    CHARON_DATA_DIR,
    CHARON_ENV_FILE,
    CHARON_PKG_DIR,
    CHROMA_DB_DIR,
    DATA_DIR,
    DATASHEET_DIR,
    DATASHEETS_DIR,
    ERROR_LOG_FILE,
    KICAD_DBL_PATH,
    LEDGER_DB_PATH,
    LOGS_DIR,
    MAIN_LOG_FILE,
    PARTVAULT_DATA_DIR,
    PROJECT_LOGS_DIR,
    PROJECT_MEMORY_DIR,
    PROJECTS_DIR,
    QUARTERMASTER_DB_PATH,
    STATE_DB_PATH,
    TASK_QUEUE_DB_PATH,
    USER_CONFIG_DIR,
    XDG_CACHE_HOME,
    XDG_CONFIG_HOME,
    XDG_DATA_HOME,
    XDG_STATE_HOME,
    ensure_ecosystem_directories,
    resolve_project_path,
)
from charon.config.settings import (
    API_KEY_HEADER_NAME,
    CHARON_API_KEY,
    DEFAULT_CONCIERGE_MIN_CONFIDENCE,
    DEFAULT_HEAVY_MODEL,
    DEFAULT_TRIAGE_MODEL,
    OLLAMA_HOST,
)

__all__ = [
    # Logging Configuration
    "setup_logging",
    # XDG Base & Ecosystem Paths
    "XDG_DATA_HOME",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "USER_CONFIG_DIR",
    "CHARON_ENV_FILE",
    "KICAD_DBL_PATH",
    "CHARON_DATA_DIR",
    "CHARON_PKG_DIR",
    "PROJECT_MEMORY_DIR",
    "CHROMA_DB_DIR",
    "STATE_DB_PATH",
    "LEDGER_DB_PATH",
    "TASK_QUEUE_DB_PATH",
    "PROJECT_LOGS_DIR",
    "LOGS_DIR",
    "MAIN_LOG_FILE",
    "ERROR_LOG_FILE",
    "DATA_DIR",
    "PARTVAULT_DATA_DIR",
    "QUARTERMASTER_DB_PATH",
    "BASE_DIR",
    "PROJECTS_DIR",
    "DATASHEETS_DIR",
    "DATASHEET_DIR",
    "ensure_ecosystem_directories",
    "resolve_project_path",
    # Settings & Environment Constants
    "CHARON_API_KEY",
    "API_KEY_HEADER_NAME",
    "OLLAMA_HOST",
    "DEFAULT_HEAVY_MODEL",
    "DEFAULT_TRIAGE_MODEL",
    "DEFAULT_CONCIERGE_MIN_CONFIDENCE",
]
