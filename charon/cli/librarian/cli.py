"""
charon/cli/librarian/cli.py
System Version: v0.2.0 | File Revision: 2.0.0

Module: CLI subcommands dispatcher and TUI session launcher for Charon Librarian.
Aligned with Schema V3.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from charon.cli.librarian.database import run_audit, run_sync
from charon.cli.librarian.ingestion import run_create, run_edit, run_ingest
from charon.cli.librarian.lifecycle import (
    run_delete_skill,
    run_demote,
    run_promote,
    run_rename,
)
from charon.cli.librarian.manifest import run_check
from charon.cli.librarian.permissions import (
    run_list,
    run_permission_change,
    set_default_action,
)
from charon.cli.librarian.purge_gaps import purge_resolved_gaps


def main(args: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="charon librarian",
        description="Unified skill management interface for Charon Librarian.",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # Inventory & Diagnostics
    subparsers.add_parser("list", help="List all discovered skills and authorization tags.")
    check_p = subparsers.add_parser("check", help="Validate manifest schema integrity.")
    check_p.add_argument("paths", nargs="*", type=Path, help="Target manifest/skill paths.")
    check_p.add_argument("--fix", action="store_true", help="Auto-fix legacy structures.")
    subparsers.add_parser("sync", help="Re-index filesystem manifests into SQLite registry.")
    subparsers.add_parser("audit", help="Audit database registry vs filesystem state drift.")

    # RBAC & Action Management
    grant_p = subparsers.add_parser("grant", help="Grant agent skill authorization.")
    grant_p.add_argument("skill_id", type=str)
    grant_p.add_argument("agent", type=str)

    revoke_p = subparsers.add_parser("revoke", help="Revoke agent skill authorization.")
    revoke_p.add_argument("skill_id", type=str)
    revoke_p.add_argument("agent", type=str)

    default_action_p = subparsers.add_parser(
        "set-default-action", help="Set default execution action for an agent."
    )
    default_action_p.add_argument("agent_id", type=str, help="Target agent ID")
    default_action_p.add_argument("action_name", type=str, help="Default action name")

    # Maintenance
    subparsers.add_parser("purge-gaps", help="Purge resolved skill gaps and vacuum DB.")

    # Ingestion & Editing
    create_p = subparsers.add_parser("create", help="Scaffold a new skill package.")
    create_p.add_argument("skill_id", type=str)
    create_p.add_argument("--category", type=str, default="General")
    create_p.add_argument("--agent", type=str, default=None, help="Target agent_id to equip this skill.")

    ingest_p = subparsers.add_parser("ingest", help="Ingest a script file or directory.")
    ingest_p.add_argument("path", type=Path)
    ingest_p.add_argument("--skill-id", type=str, default=None)
    ingest_p.add_argument("--agent", type=str, default=None, help="Target agent_id to equip this skill.")

    edit_p = subparsers.add_parser("edit", help="Open a skill manifest in $EDITOR.")
    edit_p.add_argument("skill_id", type=str)

    # Lifecycle Operations
    promote_p = subparsers.add_parser("promote", help="Promote staged skill to dynamic.")
    promote_p.add_argument("skill_id", type=str)

    demote_p = subparsers.add_parser("demote", help="Demote dynamic skill to staged quarantine.")
    demote_p.add_argument("skill_id", type=str)

    rename_p = subparsers.add_parser("rename", help="Rename a skill_id across manifest files.")
    rename_p.add_argument("old_skill_id", type=str)
    rename_p.add_argument("new_skill_id", type=str)

    delete_p = subparsers.add_parser("delete", help="Purge skill completely from disk and DB.")
    delete_p.add_argument("skill_id", type=str)

    parsed, unknown = parser.parse_known_args(args)

    if not parsed.subcommand:
        if unknown:
            parser.print_help()
            return 1
        from charon.cli.librarian.tui import LibrarianTUI

        tui = LibrarianTUI()
        tui.start()
        return 0

    if parsed.subcommand == "list":
        return run_list()
    elif parsed.subcommand == "check":
        return run_check(paths=parsed.paths, auto_fix=parsed.fix)
    elif parsed.subcommand == "sync":
        return run_sync()
    elif parsed.subcommand == "audit":
        return run_audit()
    elif parsed.subcommand in ("grant", "revoke"):
        return run_permission_change(
            skill_id=parsed.skill_id,
            agent_id=parsed.agent,
            action=parsed.subcommand,
        )
    elif parsed.subcommand == "set-default-action":
        return set_default_action(
            agent_id=parsed.agent_id,
            action_name=parsed.action_name,
        )
    elif parsed.subcommand == "purge-gaps":
        purge_resolved_gaps()
        return 0
    elif parsed.subcommand == "create":
        return run_create(
            skill_id=parsed.skill_id,
            category=parsed.category,
            target_agent=parsed.agent,
        )
    elif parsed.subcommand == "ingest":
        return run_ingest(
            source_path=parsed.path,
            skill_id=parsed.skill_id,
            target_agent=parsed.agent,
        )
    elif parsed.subcommand == "edit":
        return run_edit(skill_id=parsed.skill_id)
    elif parsed.subcommand == "promote":
        return run_promote(skill_id=parsed.skill_id)
    elif parsed.subcommand == "demote":
        return run_demote(skill_id=parsed.skill_id)
    elif parsed.subcommand == "rename":
        return run_rename(
            old_skill_id=parsed.old_skill_id,
            new_skill_id=parsed.new_skill_id,
        )
    elif parsed.subcommand == "delete":
        return run_delete_skill(skill_id=parsed.skill_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())