"""
charon/agents/cleaner/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Package initialization gateway for cleaner.
"""

# charon/agents/cleaner/__init__.py

from charon.config.paths import ensure_ecosystem_directories
from .agent import TheCleaner

__all__ = ["TheCleaner", "ensure_ecosystem_directories"]