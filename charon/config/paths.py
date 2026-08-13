"""
charon/config/paths.py
System Version: v0.2.0 | File Revision: 1.6.0

Module: Application & Ecosystem XDG Path Resolver
Defines canonical XDG-compliant storage paths for Charon background daemon runtime,
logs, state machines, vector stores, dynamic skill registries, task sandboxes, and
external PartVault integrations.
"""

import os
from pathlib import Path
from typing import Union

# =============================================================================
# 0. Repository & Package Base Directories
# =============================================================================
CHARON_PKG_DIR = Path(__file__).resolve().parent.parent  # .../Charon/charon
BASE_DIR = CHARON_PKG_DIR.parent                          # .../Charon

# Internal Module Directories
CONFIG_DIR = CHARON_PKG_DIR / "config"
DEFINITIONS_DIR = CONFIG_DIR / "definitions"
CLI_DIR = CHARON_PKG_DIR / "cli"
LIBRARIAN_DIR = CLI_DIR / "librarian"
STORAGE_DIR = LIBRARIAN_DIR / "storage"

# =============================================================================
# 1. XDG Base Directory Specification Standards
# =============================================================================
XDG_DATA_HOME = Path(
    os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")
).resolve()

XDG_CONFIG_HOME = Path(
    os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
).resolve()

XDG_STATE_HOME = Path(
    os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state")
).resolve()

XDG_CACHE_HOME = Path(
    os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")
).resolve()

# =============================================================================
# 2. Application-Specific XDG Directories & Databases
# =============================================================================
# System Configuration & Core Blueprint Files
USER_CONFIG_DIR = XDG_CONFIG_HOME / "charon"
CHARON_ENV_FILE = USER_CONFIG_DIR / "env"
KICAD_DBL_PATH = USER_CONFIG_DIR / "partvault.kicad_dbl"
SYSTEM_ACTIONS_FILE = DEFINITIONS_DIR / "system_actions.json"

# Charon Runtime Data & Memory Storage
CHARON_DATA_DIR = XDG_DATA_HOME / "charon"
DATA_DIR = CHARON_DATA_DIR
PROJECT_MEMORY_DIR = CHARON_DATA_DIR / "chroma_db"
CHROMA_DB_DIR = PROJECT_MEMORY_DIR

# Persistent Daemon Databases
STATE_DB_PATH = CHARON_DATA_DIR / "charon_state.db"
LEDGER_DB_PATH = CHARON_DATA_DIR / "charon_ledger.db"
TASK_QUEUE_DB_PATH = STATE_DB_PATH  # Task queue state shares StateManager DB

# User-Level Dynamic Skill & Task Sandbox Directories (XDG Runtime Overrides)
DYNAMIC_SKILLS_DIR = CHARON_DATA_DIR / "storage"
WORKSPACES_DIR = CHARON_DATA_DIR / "workspaces"

# Repository-Internal 3-Tier Skill Storage (Modularized inside Librarian)
QUARANTINE_SKILLS_DIR = STORAGE_DIR / "quarantine"
PKG_QUARANTINE_SKILLS_DIR = QUARANTINE_SKILLS_DIR  # Alias for consistency
PKG_STAGED_SKILLS_DIR = STORAGE_DIR / "staged"
PKG_DYNAMIC_SKILLS_DIR = STORAGE_DIR / "dynamic"

# Charon Logging & Cache State
PROJECT_LOGS_DIR = XDG_STATE_HOME / "charon" / "logs"
LOGS_DIR = PROJECT_LOGS_DIR
MAIN_LOG_FILE = LOGS_DIR / "charond.log"
ERROR_LOG_FILE = LOGS_DIR / "charond.error.log"

# =============================================================================
# 3. External Integration Directories (PartVault & Workspace)
# =============================================================================
# Shared PartVault Data & Datasheet Storage
PARTVAULT_DATA_DIR = XDG_DATA_HOME / "partvault"
PARTVAULT_DB_PATH = PARTVAULT_DATA_DIR / "partvault.db"
QUARTERMASTER_DB_PATH = PARTVAULT_DB_PATH  # Legacy alias for Quartermaster queries
DATASHEETS_DIR = PARTVAULT_DATA_DIR / "datasheets"
DATASHEET_DIR = DATASHEETS_DIR

# User Workspace Roots
PROJECTS_DIR = Path(
    os.getenv("CHARON_PROJECTS_DIR", Path.home() / "Projects")
).resolve()


def ensure_ecosystem_directories() -> None:
    """Ensures all XDG user directories and workspace runtime folders exist."""
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CHARON_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    DYNAMIC_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

    # Internal Package Directories
    DEFINITIONS_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    QUARANTINE_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    PKG_STAGED_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    PKG_DYNAMIC_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    # Logs and External Integrations
    PROJECT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PARTVAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATASHEETS_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def resolve_project_path(target: Union[str, Path]) -> Path:
    """Resolves a path relative to PROJECTS_DIR if not absolute."""
    path = Path(os.path.expanduser(str(target))).resolve()
    if path.exists():
        return path
    return (PROJECTS_DIR / str(target)).resolve()


# Initialize ecosystem directories on module import
ensure_ecosystem_directories()