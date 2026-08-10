"""
charon/cli/librarian/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Package entrypoint for Charon Skill Librarian toolset.
Provides backwards-compatible imports for CLI entrypoints and core handlers.
"""

from charon.cli.librarian.cli import main
from charon.cli.librarian.database import run_audit, run_sync
from charon.cli.librarian.ingestion import run_create, run_edit, run_ingest
from charon.cli.librarian.lifecycle import (
    run_delete_skill,
    run_demote,
    run_promote,
    run_rename,
)
from charon.cli.librarian.manifest import run_check, validate_manifest_file
from charon.cli.librarian.permissions import run_list, run_permission_change

__all__ = [
    "main",
    "run_check",
    "validate_manifest_file",
    "run_sync",
    "run_audit",
    "run_permission_change",
    "run_list",
    "run_promote",
    "run_demote",
    "run_rename",
    "run_delete_skill",
    "run_create",
    "run_ingest",
    "run_edit",
]