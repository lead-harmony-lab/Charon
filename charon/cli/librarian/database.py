"""
charon/cli/librarian/database.py
System Version: v0.4.6 | File Revision: 3.6.0

Module: SQLite registry synchronization, agent_skill_map verification, drift auditing,
direct DDL skill registration, system action contract queries, single skill lookups,
skill ID migration, and plugin action queries. Serves as the canonical data layer.
"""

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from rich.console import Console
from rich.table import Table

from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
    SYSTEM_ACTIONS_FILE,
)
from charon.db.connection import get_connection

console = Console()
logger = logging.getLogger("charon.cli.librarian.database")


def get_db_path() -> Path:
    """Returns canonical path to Charon SQLite database."""
    return STATE_DB_PATH


def _slugify(text: str) -> str:
    """Converts display names/categories to clean snake_case identifiers."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")


def get_skill_by_id(
    skill_id: str,
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Queries skill_registry for a specific skill_id.
    Returns a dictionary with full skill metadata or None if not found.
    """
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return None

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT skill_id, action_name, version, category, description,
                       parameters, system_requirements, consumed_artifacts,
                       produced_artifacts, entry_file_path, handler_name,
                       status, quarantine_reason, is_global, updated_at
                FROM skill_registry
                WHERE skill_id = ?
                """,
                (skill_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "skill_id": row[0],
                    "action_name": row[1],
                    "version": row[2],
                    "category": row[3],
                    "description": row[4],
                    "parameters": json.loads(row[5]) if row[5] else {},
                    "system_requirements": json.loads(row[6]) if row[6] else [],
                    "consumed_artifacts": json.loads(row[7]) if row[7] else [],
                    "produced_artifacts": json.loads(row[8]) if row[8] else [],
                    "entry_file_path": row[9],
                    "handler_name": row[10],
                    "status": row[11],
                    "quarantine_reason": row[12],
                    "is_global": bool(row[13]),
                    "updated_at": row[14],
                }
    except Exception as e:
        logger.warning(f"Failed to query skill '{skill_id}' from DB: {e}")

    return None


def migrate_skill_id_in_db(
    old_skill_id: str,
    new_skill_id: str,
    db_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """
    Atomically renames a skill_id across skill_registry and agent_skill_map,
    updating entry file paths and preserving agent permissions.
    """
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return False, f"Database file not found at {target_db}"

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()

            # Temporarily disable FK checks to allow cascade PK update
            cursor.execute("PRAGMA foreign_keys = OFF;")

            # 1. Verify old record exists
            cursor.execute(
                "SELECT entry_file_path FROM skill_registry WHERE skill_id = ?",
                (old_skill_id,),
            )
            row = cursor.fetchone()
            if not row:
                cursor.execute("PRAGMA foreign_keys = ON;")
                return False, f"Record '{old_skill_id}' not found in skill_registry."

            old_path = row[0] or ""
            new_path = old_path.replace(old_skill_id, new_skill_id)

            # 2. Update Primary Key & Entry Path in skill_registry
            cursor.execute(
                """
                UPDATE skill_registry
                SET skill_id = ?,
                    entry_file_path = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE skill_id = ?
                """,
                (new_skill_id, new_path, old_skill_id),
            )

            # 3. Update Foreign Key references in agent_skill_map
            cursor.execute(
                """
                UPDATE agent_skill_map
                SET skill_id = ?
                WHERE skill_id = ?
                """,
                (new_skill_id, old_skill_id),
            )

            conn.commit()
            cursor.execute("PRAGMA foreign_keys = ON;")

        return True, f"Migrated '{old_skill_id}' -> '{new_skill_id}' across SQLite tables."
    except Exception as e:
        logger.error(f"Failed to migrate skill ID in DB: {e}")
        return False, f"Database error during migration: {str(e)}"


def get_system_action_contract(
    action_name: Optional[str],
    db_path: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Queries the system_actions table to check if an action_name satisfies
    a registered system contract. Returns contract metadata dict if present.
    """
    if not action_name or action_name == "N/A":
        return None

    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return None

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT reserved_key, required_role, is_mandatory, description
                FROM system_actions
                WHERE action_name = ?
                """,
                (action_name,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "reserved_key": row[0],
                    "required_role": row[1],
                    "is_mandatory": bool(row[2]),
                    "description": row[3] or "",
                }
    except sqlite3.Error as e:
        logger.debug(f"Failed to query system action contract for '{action_name}': {e}")
    except Exception as e:
        logger.warning(f"Unexpected error querying system_actions table: {e}")

    return None


def get_plugin_actions(
    manifest_path: str,
    entry_file_path: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, str]]:
    """
    Queries skill_registry for all action_name, handler_name, and description entries
    associated with a specific root plugin/manifest or entry_file_path.
    """
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    actions: List[Dict[str, str]] = []

    if not target_db.exists():
        return actions

    extracted_skill_id: Optional[str] = None
    if manifest_path:
        m_path = Path(manifest_path)
        if m_path.exists():
            try:
                with open(m_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    extracted_skill_id = data.get("skill_id")
            except Exception as e:
                logger.debug(f"Could not parse manifest at {manifest_path}: {e}")

        if not extracted_skill_id and m_path.parent:
            extracted_skill_id = m_path.parent.name

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT action_name, handler_name, description
                FROM skill_registry
                WHERE skill_id = ? OR (entry_file_path IS NOT NULL AND entry_file_path = ?)
                """,
                (extracted_skill_id or "", entry_file_path or ""),
            )
            for row in cursor.fetchall():
                actions.append({
                    "action_name": row[0] or "N/A",
                    "handler_name": row[1] or "N/A",
                    "description": row[2] or "",
                })
    except Exception as e:
        logger.warning(f"Failed to query plugin actions from DB: {e}")

    return actions


def flag_quarantined_orphans(db_path: Optional[Union[str, Path]] = None) -> int:
    """
    Scans skill_registry for records whose entry_file_path no longer exists
    on disk and marks their status as 'QUARANTINED' with an explicit reason.
    Returns the count of newly flagged skills.
    """
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT skill_id, entry_file_path, status FROM skill_registry")
            rows = cursor.fetchall()

            flagged_count = 0
            for sid, entry_path_str, status in rows:
                if entry_path_str:
                    entry_path = Path(entry_path_str)
                    if not entry_path.exists() and (status or "").upper() != "QUARANTINED":
                        cursor.execute(
                            """
                            UPDATE skill_registry
                            SET status = 'QUARANTINED',
                                quarantine_reason = 'MISSING_ENTRY_FILE: Path on disk not found',
                                updated_at = CURRENT_TIMESTAMP
                            WHERE skill_id = ?
                            """,
                            (sid,),
                        )
                        flagged_count += 1

            if flagged_count > 0:
                conn.commit()

        return flagged_count
    except Exception as e:
        logger.warning(f"Failed to flag quarantine orphans in SQLite: {e}")
        return 0


def register_skill_in_db(
    skill_id: str,
    action_name: str,
    version: str,
    category: str,
    description: str,
    parameters: dict,
    system_requirements: list,
    consumed_artifacts: list,
    produced_artifacts: list,
    entry_file_path: Path,
    handler_name: str = "execute_action",
    is_global: int = 0,
    status: str = "STAGED",
    quarantine_reason: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """
    Directly registers or updates a skill in skill_registry using
    explicit database DDL column mappings.
    """
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    abs_entry_path = str(entry_file_path.resolve())

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT skill_id FROM skill_registry WHERE action_name = ? AND skill_id != ?",
                (action_name, skill_id),
            )
            collision = cursor.fetchone()
            if collision:
                return False, f"Action name collision: '{action_name}' is already assigned to skill '{collision[0]}'."

            cursor.execute(
                """
                INSERT INTO skill_registry (
                    skill_id, action_name, version, category, description,
                    parameters, system_requirements, consumed_artifacts, produced_artifacts,
                    entry_file_path, handler_name, status, quarantine_reason, is_global, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(skill_id) DO UPDATE SET
                    action_name = excluded.action_name,
                    version = excluded.version,
                    category = excluded.category,
                    description = excluded.description,
                    parameters = excluded.parameters,
                    system_requirements = excluded.system_requirements,
                    consumed_artifacts = excluded.consumed_artifacts,
                    produced_artifacts = excluded.produced_artifacts,
                    entry_file_path = excluded.entry_file_path,
                    handler_name = excluded.handler_name,
                    status = excluded.status,
                    quarantine_reason = excluded.quarantine_reason,
                    is_global = excluded.is_global,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    skill_id,
                    action_name,
                    version,
                    category,
                    description,
                    json.dumps(parameters),
                    json.dumps(system_requirements),
                    json.dumps(consumed_artifacts),
                    json.dumps(produced_artifacts),
                    abs_entry_path,
                    handler_name,
                    status,
                    quarantine_reason,
                    is_global,
                ),
            )
            conn.commit()
        return True, ""
    except Exception as e:
        return False, f"Database Registration Error: {str(e)}"


def sync_system_actions(db_path: Optional[Union[str, Path]] = None) -> None:
    """Synchronizes system_actions.json foundational blueprint into SQLite."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not SYSTEM_ACTIONS_FILE.exists():
        console.print("[yellow]Warning: system_actions.json not found. Skipping sync.[/yellow]")
        return

    try:
        with open(SYSTEM_ACTIONS_FILE, "r", encoding="utf-8") as f:
            actions_manifest = json.load(f)

        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            for action in actions_manifest:
                cursor.execute(
                    """
                    INSERT INTO system_actions (
                        reserved_key, action_name, required_role, is_mandatory, description
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(reserved_key) DO UPDATE SET
                        action_name = excluded.action_name,
                        required_role = excluded.required_role,
                        is_mandatory = excluded.is_mandatory,
                        description = excluded.description,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        action.get("reserved_key"),
                        action.get("action_name"),
                        action.get("required_role"),
                        action.get("is_mandatory", 1),
                        action.get("description", ""),
                    ),
                )
            conn.commit()
        console.print("[dim green]System actions blueprint synced successfully.[/dim green]")
    except Exception as e:
        logger.error(f"Failed to sync system_actions.json: {e}")
        console.print(f"[bold red]Error syncing system actions:[/bold red] {e}")


def run_sync(db_path: Optional[Union[str, Path]] = None) -> int:
    """Re-indexes filesystem manifests into the SQLite skill_registry table."""
    target_db = Path(db_path) if db_path else STATE_DB_PATH

    console.print(
        "[bold blue]Syncing filesystem skill manifests into SQLite registry...[/bold blue]"
    )
    from charon.core.skills import SkillLibrarian
    librarian = (
        SkillLibrarian.get_instance(db_path=target_db)
        if hasattr(SkillLibrarian.get_instance, "__code__")
        and "db_path" in SkillLibrarian.get_instance.__code__.co_varnames
        else SkillLibrarian.get_instance()
    )

    if hasattr(librarian, "reindex_skills"):
        librarian.reindex_skills()

    # Synchronize the foundational system actions
    sync_system_actions(target_db)

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

    db_skill_action_counts: Dict[str, int] = {}
    orphaned_mappings: List[Tuple[str, str]] = []

    if target_db.exists():
        try:
            with get_connection(target_db, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT skill_id, COUNT(action_name) FROM skill_registry GROUP BY skill_id"
                )
                for row in cursor.fetchall():
                    db_skill_action_counts[row[0]] = row[1]

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
                        actions = data.get("supported_actions", {})
                        action_count = len(actions) if isinstance(actions, dict) else 0

                        disk_manifests[sid] = {
                            "path": manifest_path,
                            "category": category,
                            "disk_action_count": action_count,
                        }
            except Exception as e:
                logger.warning(f"Failed to read manifest at {manifest_path}: {e}")
                continue

    if not disk_manifests and not db_skill_action_counts:
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
        disk_count = meta["disk_action_count"]
        db_count = db_skill_action_counts.get(sid, 0)

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

def get_available_system_contracts(
    agent_roles: List[str],
    db_path: Optional[Union[str, Path]] = None,
) -> List[Tuple[Any, ...]]:
    """
    Queries system_actions for contracts matching the provided agent roles.
    Returns a list of tuples: (reserved_key, required_role, action_name, description, is_mandatory).
    """
    if not agent_roles:
        return []

    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return []

    try:
        with get_connection(target_db, read_only=True) as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in agent_roles)
            cursor.execute(
                f"""
                SELECT reserved_key, required_role, action_name, description, is_mandatory
                FROM system_actions
                WHERE required_role IN ({placeholders})
                """,
                tuple(agent_roles)
            )
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to query system_actions for roles {agent_roles}: {e}")
        return []

def bind_system_action_to_contract(
    skill_action_name: str,
    target_reserved_key: str,
    db_path: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str]:
    """
    Binds a specific skill action_name to a foundational system role contract.
    Returns a tuple of (Success: bool, Message: str).
    """
    target_db = Path(db_path) if db_path else STATE_DB_PATH
    if not target_db.exists():
        return False, "Database not found."

    try:
        with get_connection(target_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE system_actions
                SET action_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE reserved_key = ?
                """,
                (skill_action_name, target_reserved_key)
            )
            conn.commit()
        return True, f"Successfully bound system contract '{target_reserved_key}' to action '{skill_action_name}'."
    except Exception as e:
        logger.error(f"Failed to bind system action '{skill_action_name}' to '{target_reserved_key}': {e}")
        return False, f"Database error: {str(e)}"

if __name__ == "__main__":
    run_audit()