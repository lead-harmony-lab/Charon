"""
charon/cli/librarian/__init__.py
System Version: v0.4.0 | File Revision: 1.1.0

Module: Package entrypoint for Charon Skill Librarian toolset.
Provides backwards-compatible imports for CLI entrypoints, core handlers,
directory constants, and summary providers.
"""

from charon.cli.librarian.cli import main
from charon.cli.librarian.ingestion import (
    SKILLS_DYNAMIC_DIR,
    SKILLS_QUARANTINE_DIR,
    SKILLS_STAGED_DIR,
    SKILLS_TEMPLATES_DIR,
    get_quarantine_skills_summary,
    get_staged_skills_summary,
    run_create,
    run_edit,
    run_ingest,
    run_quarantine_sanitizer,
)
from charon.cli.librarian.lifecycle import (
    run_delete_skill,
    run_demote,
    run_promote,
    run_rename,
)
from charon.cli.librarian.manifest import run_check, validate_manifest_file
from charon.cli.librarian.permissions import run_list, run_permission_change

__all__ = [
    # Core CLI Entrypoint
    "main",
    # Manifest Handlers
    "run_check",
    "validate_manifest_file",
    # Ingestion & Quarantine Operations
    "run_create",
    "run_ingest",
    "run_edit",
    "run_quarantine_sanitizer",
    "get_quarantine_skills_summary",
    "get_staged_skills_summary",
    # Directory Constants
    "SKILLS_QUARANTINE_DIR",
    "SKILLS_STAGED_DIR",
    "SKILLS_DYNAMIC_DIR",
    "SKILLS_TEMPLATES_DIR",
    # Lifecycle Operations
    "run_promote",
    "run_demote",
    "run_rename",
    "run_delete_skill",
    # Permission Handlers
    "run_permission_change",
    "run_list",
]