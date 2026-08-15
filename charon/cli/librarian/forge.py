"""
charon/cli/librarian/forge.py
System Version: v0.2.0 | File Revision: 3.2.0

Module: Charon Skill Forge utility integrated within Librarian.
Handles querying open skill gaps, forging candidate dynamic skill scaffolds,
indexing dynamic skills, and resolving gaps in Schema V3.
Decoupled DB state interactions to charon.cli.librarian.db.
"""

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from charon.cli.librarian.db import (
    get_open_gaps,
    resolve_gap_db,
    run_sync,
)
from charon.config.paths import (
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.core.skills import SkillLibrarian

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] [FORGE] %(message)s")
logger = logging.getLogger("charon.cli.librarian.forge")


def fetch_open_gaps(db_path: Path = STATE_DB_PATH) -> List[Dict[str, Any]]:
    """Fetches all open skill gaps from the state database via db package."""
    return get_open_gaps(db_path=db_path)


def forge_skill_scaffold(
    action_name: str,
    target_agent: str,
    output_dir: Optional[Path] = None,
    system_requirements: Optional[List[str]] = None,
) -> Path:
    """Synthesizes a skill blueprint scaffold on disk (manifest.json + plugin.py) aligned with V3 schema."""
    skill_id = f"{action_name}_skill"
    base_dir = output_dir or (PKG_STAGED_SKILLS_DIR / skill_id)
    base_dir.mkdir(parents=True, exist_ok=True)

    manifest_data = {
        "skill_id": skill_id,
        "version": "0.1.0",
        "stage": "Staged",
        "category": "Dynamic",
        "description": f"Dynamic skill handler for action '{action_name}'",
        "allowed_agents": [target_agent],
        "supported_actions": {
            action_name: {
                "description": f"Executes '{action_name}'",
                "handler_name": "execute",
                "parameters": {},
            }
        },
        "system_requirements": system_requirements or [],
        "consumed_artifacts": [],
        "produced_artifacts": [],
    }

    manifest_path = base_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    plugin_code = f'''"""
Dynamic skill plugin for action '{action_name}'.
Synthesized by Charon Skill Forge.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("charon.skills.{skill_id}")


def execute(agent_name: str, parameters: Dict[str, Any], raw_prompt: str = "") -> Dict[str, Any]:
    logger.info(f"[FORGED-SKILL] Executing {action_name} for agent '{{agent_name}}'")
    return {{
        "status": "success",
        "action": "{action_name}",
        "executed_by": agent_name,
        "parameters": parameters,
        "message": "Successfully executed forged skill handler.",
    }}
'''
    plugin_path = base_dir / "plugin.py"
    with open(plugin_path, "w", encoding="utf-8") as f:
        f.write(plugin_code)

    logger.info(f"✅ Successfully forged skill blueprint at: {base_dir}")
    return base_dir


def sync_db(db_path: Path = STATE_DB_PATH) -> int:
    """Ensures schema consistency and re-indexes all disk skills into the registry."""
    sync_results = run_sync(db_path=db_path)
    return sync_results.get("registered_handlers", 0)


def promote_and_resolve_gap(
    gap_id: int,
    skill_dir: Path,
    db_path: Path = STATE_DB_PATH,
) -> bool:
    """Indexes newly forged skill via SkillLibrarian/run_sync and marks gap as resolved."""
    indexed_count = 0
    try:
        librarian = SkillLibrarian.get_instance()
        if hasattr(librarian, "index_skill_directory"):
            indexed_count = librarian.index_skill_directory(skill_dir)
        elif hasattr(librarian, "scan_and_index"):
            indexed_count = librarian.scan_and_index(skill_dir)
    except Exception as exc:
        logger.debug(f"Librarian instance lookup fallback: {exc}")

    if indexed_count == 0:
        logger.info("Re-running V3 service sync fallback...")
        indexed_count = sync_db(db_path)

    if resolve_gap_db(gap_id, db_path=db_path):
        logger.info(f"✅ Marked Gap ID {gap_id} as 'resolved' in state database.")
        return True
    else:
        logger.error(f"Failed to resolve gap ID {gap_id} in database.")
        return False


def build_parser() -> argparse.ArgumentParser:
    """Builds parser for charon-forge and charon forge CLI execution."""
    parser = argparse.ArgumentParser(
        prog="charon-forge",
        description="Charon Skill Forge: Inspect skill gaps, forge plugins, and manage skill indexing.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Forge Subcommands")

    list_p = subparsers.add_parser("list", help="List all open skill gaps logged in charon_state.db")
    list_p.add_argument("--db", type=Path, default=STATE_DB_PATH, help="Path to charon_state.db")

    scaffold_p = subparsers.add_parser("scaffold", help="Synthesize plugin scaffold on disk")
    scaffold_p.add_argument("--action", required=True, help="Target action name")
    scaffold_p.add_argument("--agent", required=True, help="Target requesting agent")
    scaffold_p.add_argument("--out", type=Path, default=None, help="Output directory path")
    scaffold_p.add_argument("--reqs", nargs="*", default=[], help="System requirements/binaries")

    resolve_p = subparsers.add_parser("resolve", help="Forge, index skill, and close gap ID")
    resolve_p.add_argument("--gap-id", type=int, required=True, help="Gap ID in skill_gaps table")
    resolve_p.add_argument("--action", required=True, help="Action name to forge and index")
    resolve_p.add_argument("--agent", required=True, help="Requesting agent name")
    resolve_p.add_argument("--db", type=Path, default=STATE_DB_PATH, help="Path to charon_state.db")

    sync_p = subparsers.add_parser("sync", help="Synchronize database schema and re-index disk skills")
    sync_p.add_argument("--db", type=Path, default=STATE_DB_PATH, help="Path to charon_state.db")

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point supporting direct or programmatically passed arguments."""
    parser = build_parser()
    parsed_args = parser.parse_args(args)

    if not parsed_args.command or parsed_args.command == "list":
        db_path = getattr(parsed_args, "db", STATE_DB_PATH)
        gaps = fetch_open_gaps(db_path=db_path)
        print(f"\n=================== Open Skill Gaps ({len(gaps)}) ===================")
        if not gaps:
            print(" No open skill gaps currently logged.")
        else:
            for g in gaps:
                prereqs = f" (Missing: {g['missing_prerequisites']})" if g.get('missing_prerequisites') else ""
                print(f" • [ID {g['gap_id']}] Action: '{g['action_name']}' | Agent: {g['requesting_agent']}{prereqs}")
        print("=================================================================\n")
        return 0

    elif parsed_args.command == "scaffold":
        staged_dir = forge_skill_scaffold(
            action_name=parsed_args.action,
            target_agent=parsed_args.agent,
            output_dir=parsed_args.out,
            system_requirements=parsed_args.reqs,
        )
        print(f"Skill scaffold generated at: {staged_dir}")
        return 0

    elif parsed_args.command == "resolve":
        db_path = getattr(parsed_args, "db", STATE_DB_PATH)
        staged_dir = forge_skill_scaffold(
            action_name=parsed_args.action,
            target_agent=parsed_args.agent,
        )
        success = promote_and_resolve_gap(
            gap_id=parsed_args.gap_id,
            skill_dir=staged_dir,
            db_path=db_path,
        )
        return 0 if success else 1

    elif parsed_args.command == "sync":
        db_path = getattr(parsed_args, "db", STATE_DB_PATH)
        logger.info(f"Syncing DB and re-indexing skills for {db_path}...")
        indexed_count = sync_db(db_path)
        logger.info(f"Database sync complete. Indexed {indexed_count} skills.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())