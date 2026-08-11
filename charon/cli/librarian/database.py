"""
charon/cli/librarian/database.py
System Version: v0.3.1 | File Revision: 2.1.0

Module: SQLite registry synchronization, agent_skill_map verification, and drift auditing.
Updated to support flexible db_path parameters across sync and audit entrypoints.
"""

import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from rich.console import Console
from rich.table import Table

from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.core.skills import SkillLibrarian
from charon.db.connection import get_connection

console = Console()
logger = logging.getLogger("charon.cli.librarian.database")


def _slugify(text: str) -> str:
    """Converts display names/categories to clean snake_case identifiers."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")


def run_sync(db_path: Optional[Union[str, Path]] = None) -> int:
    """Re-indexes filesystem manifests into the SQLite skill_registry table."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH

    console.print(
        "[bold blue]Syncing filesystem skill manifests into SQLite registry...[/bold blue]"
    )
    librarian = SkillLibrarian.get_instance(db_path=target_db) if hasattr(SkillLibrarian.get_instance, "__code__") and "db_path" in SkillLibrarian.get_instance.__code__.co_varnames else SkillLibrarian.get_instance()

    if hasattr(librarian, "reindex_skills"):
        librarian.reindex_skills()

    count = 0
    if target_db.exists():
        try:
            with get_connection(target_db, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM skill_registry")
                row = cursor.fetchone()
                count = row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to fetch skill count from SQLite: {e}")

    console.print(
        f"[bold green]✅ Sync complete.[/bold green] Total registered action handlers: [bold white]{count}[/bold white]"
    )
    return 0


def _audit_agent_skill_map(conn) -> List[Tuple[str, str]]:
    """Identifies orphaned records in agent_skill_map referencing missing skill_ids."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_skill_map'"
    )
    if not cursor.fetchone():
        return []

    # Joined on skill_id to match agent_skill_map foreign key schema
    cursor.execute("""
        SELECT asm.agent_id, asm.skill_id
        FROM agent_skill_map asm
        LEFT JOIN skill_registry sr ON asm.skill_id = sr.skill_id
        WHERE sr.skill_id IS NULL
    """)
    return cursor.fetchall()


def run_audit(db_path: Optional[Union[str, Path]] = None) -> int:
    """Audits SQLite registry state against disk manifests and validates agent_skill_map integrity."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH

    console.print(
        "[bold blue]🔍 Auditing SQLite Skill Registry & agent_skill_map vs Filesystem...[/bold blue]\n"
    )

    db_registered_actions: Set[str] = set()
    db_registered_skills: Set[str] = set()
    orphaned_mappings: List[Tuple[str, str]] = []

    if target_db.exists():
        try:
            with get_connection(target_db, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT skill_id, action_name FROM skill_registry")
                for row in cursor.fetchall():
                    db_registered_skills.add(row[0])
                    db_registered_actions.add(row[1])

                orphaned_mappings = _audit_agent_skill_map(conn)

        except Exception as e:
            console.print(
                f"[bold red]DB Error:[/bold red] Failed to query SQLite state: {e}"
            )
            return 1

    disk_manifests: Dict[str, Dict[str, Any]] = {}
    search_dirs = [
        PKG_STAGED_SKILLS_DIR,
        PKG_DYNAMIC_SKILLS_DIR,
        DYNAMIC_SKILLS_DIR,
    ]

    for root in search_dirs:
        if not root.exists():
            continue
        for manifest_path in root.rglob("manifest.json"):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sid = data.get("skill_id")
                    if sid:
                        category = data.get("category", "General")
                        category_slug = _slugify(category)
                        actions = data.get("supported_actions", {})

                        expected_actions = []
                        if isinstance(actions, dict):
                            for action_key in actions.keys():
                                expected_actions.append(f"{category_slug}:{action_key}")

                        disk_manifests[sid] = {
                            "path": manifest_path,
                            "category": category,
                            "expected_actions": expected_actions,
                        }
            except Exception as e:
                logger.warning(f"Failed to read manifest at {manifest_path}: {e}")
                continue

    if not disk_manifests and not db_registered_skills:
        console.print(
            "[yellow]No skills discovered in SQLite or on disk.[/yellow]"
        )
        return 0

    table = Table(title="Charon Skill Registry vs Filesystem Audit")
    table.add_column("Manifest Skill ID", style="bold white")
    table.add_column("Category", style="cyan")
    table.add_column("Disk Actions", justify="center")
    table.add_column("DB Indexed Actions", justify="center")
    table.add_column("Drift Analysis", style="yellow")

    drift_count = 0

    for sid, meta in disk_manifests.items():
        expected_actions = meta["expected_actions"]
        indexed_actions = [
            act for act in expected_actions if act in db_registered_actions
        ]

        disk_count = len(expected_actions)
        db_count = len(indexed_actions)

        if db_count == 0:
            analysis = "[bold red]Unindexed Skill[/bold red] (Run sync to index)"
            drift_count += 1
        elif db_count < disk_count:
            analysis = f"[bold yellow]Partial Actions Indexed[/bold yellow] ({disk_count - db_count} missing)"
            drift_count += 1
        else:
            analysis = "[dim green]In Sync[/dim green]"

        table.add_row(sid, meta["category"], str(disk_count), str(db_count), analysis)

    console.print(table)

    # Report orphaned agent_skill_map entries if found
    if orphaned_mappings:
        drift_count += len(orphaned_mappings)
        console.print(
            f"\n[bold red]⚠️ agent_skill_map Integrity Faults ({len(orphaned_mappings)} found):[/bold red]"
        )
        map_table = Table(title="Orphaned Agent Skill Mappings")
        map_table.add_column("Agent ID", style="bold cyan")
        map_table.add_column("Missing Skill ID", style="bold red")
        for agent_id, skill_id in orphaned_mappings:
            map_table.add_row(agent_id, skill_id)
        console.print(map_table)

    if drift_count > 0:
        console.print(
            f"\n[bold yellow]⚠️ State Drift Detected:[/bold yellow] {drift_count} inconsistency(ies) found. "
            f"Run [cyan]charon librarian sync[/cyan] to align database index with filesystem."
        )
        return 1

    console.print(
        "\n[bold green]✅ Database, agent_skill_map, and Filesystem are 100% in sync.[/bold green]"
    )
    return 0


if __name__ == "__main__":
    run_audit()