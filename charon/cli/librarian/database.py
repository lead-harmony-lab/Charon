"""
charon/cli/librarian/database.py
System Version: v0.3.0 | File Revision: 1.3.1

Module: SQLite registry synchronization, agent_skill_map verification, and drift auditing.
"""

import json
import logging
from typing import Any, Dict, List, Tuple
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


def run_sync() -> int:
    """Re-indexes filesystem manifests into the SQLite skill_registry table."""
    console.print(
        "[bold blue]Syncing filesystem skill manifests into SQLite registry...[/bold blue]"
    )
    librarian = SkillLibrarian.get_instance()
    librarian.reindex_skills()

    count = 0
    if STATE_DB_PATH.exists():
        try:
            with get_connection(STATE_DB_PATH, read_only=True) as conn:
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
    """Identifies orphaned records in agent_skill_map referencing missing actions/skills."""
    cursor = conn.cursor()
    # Check if agent_skill_map exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_skill_map'"
    )
    if not cursor.fetchone():
        return []

    cursor.execute("""
        SELECT asm.agent_id, asm.action_name
        FROM agent_skill_map asm
        LEFT JOIN skill_registry sr ON asm.action_name = sr.action_name
        WHERE sr.action_name IS NULL
    """)
    return cursor.fetchall()


def run_audit() -> int:
    """Audits SQLite registry state against disk manifests and validates agent_skill_map integrity."""
    console.print(
        "[bold blue]🔍 Auditing SQLite Skill Registry & agent_skill_map vs Filesystem...[/bold blue]\n"
    )

    db_skills: Dict[str, int] = {}
    orphaned_mappings: List[Tuple[str, str]] = []

    if STATE_DB_PATH.exists():
        try:
            with get_connection(STATE_DB_PATH, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT skill_id, COUNT(action_name) 
                    FROM skill_registry 
                    GROUP BY skill_id
                """)
                db_skills = {row[0]: row[1] for row in cursor.fetchall()}

                # Audit agent_skill_map for integrity faults
                orphaned_mappings = _audit_agent_skill_map(conn)

        except Exception as e:
            console.print(
                f"[bold red]DB Error:[/bold red] Failed to query SQLite state: {e}"
            )
            return 1

    disk_skills: Dict[str, Dict[str, Any]] = {}
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
                        actions = data.get("supported_actions", {})
                        action_count = (
                            len(actions) if isinstance(actions, dict) else 0
                        )
                        disk_skills[sid] = {
                            "path": manifest_path,
                            "action_count": action_count,
                            "stage": data.get("stage", "Unknown"),
                        }
            except Exception as e:
                logger.warning(f"Failed to read manifest at {manifest_path}: {e}")
                continue

    all_skill_ids = sorted(
        list(set(db_skills.keys()) | set(disk_skills.keys()))
    )

    if not all_skill_ids:
        console.print(
            "[yellow]No skills discovered in SQLite or on disk.[/yellow]"
        )
        return 0

    table = Table(title="Charon Skill Registry vs Filesystem Audit")
    table.add_column("Skill ID", style="bold white")
    table.add_column("Disk Status", justify="center")
    table.add_column("DB Status", justify="center")
    table.add_column("Action Handlers (Disk / DB)", justify="center")
    table.add_column("Drift Analysis", style="yellow")

    drift_count = 0

    for sid in all_skill_ids:
        in_disk = sid in disk_skills
        in_db = sid in db_skills

        disk_actions = disk_skills[sid]["action_count"] if in_disk else 0
        db_actions = db_skills.get(sid, 0)

        disk_str = (
            "[green]EXISTS[/green]" if in_disk else "[red]MISSING[/red]"
        )
        db_str = (
            "[green]INDEXED[/green]" if in_db else "[red]NOT INDEXED[/red]"
        )
        action_str = f"{disk_actions} / {db_actions}"

        if in_disk and not in_db:
            analysis = "[bold red]Unindexed Skill[/bold red] (Run sync to add)"
            drift_count += 1
        elif in_db and not in_disk:
            analysis = (
                "[bold red]Orphaned DB Record[/bold red] (Run sync to purge)"
            )
            drift_count += 1
        elif disk_actions != db_actions:
            analysis = (
                "[bold yellow]Action Mismatch[/bold yellow] (Run sync to update)"
            )
            drift_count += 1
        else:
            analysis = "[dim green]In Sync[/dim green]"

        table.add_row(sid, disk_str, db_str, action_str, analysis)

    console.print(table)

    # Report orphaned agent_skill_map entries if found
    if orphaned_mappings:
        drift_count += len(orphaned_mappings)
        console.print(
            f"\n[bold red]⚠️ agent_skill_map Integrity Faults ({len(orphaned_mappings)} found):[/bold red]"
        )
        map_table = Table(title="Orphaned Agent Skill Mappings")
        map_table.add_column("Agent ID", style="bold cyan")
        map_table.add_column("Missing Action Name", style="bold red")
        for agent_id, action_name in orphaned_mappings:
            map_table.add_row(agent_id, action_name)
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