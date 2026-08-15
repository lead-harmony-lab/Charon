"""
charon/cli/librarian/db/utils.py
System Version: v0.2.0 | File Revision: 2.2.0

Module: Database connection helpers and utility functions.
"""

import re
from pathlib import Path
from charon.config.paths import STATE_DB_PATH


def get_db_path() -> Path:
    """Returns canonical path to Charon SQLite database."""
    return STATE_DB_PATH


def _slugify(text: str) -> str:
    """Converts display names/categories to clean snake_case identifiers."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")