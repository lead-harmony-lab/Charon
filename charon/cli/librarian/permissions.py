"""
charon/cli/librarian/permissions.py
System Version: v0.2.0 | File Revision: 2.0.0

Module: DB-backed authorization management, default action configuration, and inventory views.
Aligned with Schema V3.
"""

import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.db.connection import get_connection

console = Console()


def find_skill_manifest(
    skill_id: str, stage_filter: Optional[str] = None
) -> Optional[Path]:
    """Locates a skill's manifest.json across staged and dynamic skill directories."""
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
                    if data.get("skill_id") == skill_id:
                        if (
                            stage_filter
                            and data.get("stage", "").lower()
                            != stage_filter.lower()
                        ):
                            continue
                        return manifest_path
            except Exception:
                continue
    return None


def run_permission_change(skill_id: str, agent_id: str, action: str) -> int:
    """Grants or revokes an agent's binding to a skill in agent_skill_map."""
    action_clean = action.lower().strip()
    if action_clean not in ("grant", "revoke"):
        console.print(
            f"[bold red]Error:[/bold red] Invalid permission action '{action}'. Use 'grant' or 'revoke'."
        )
        return 1

    with get_connection(STATE_DB_PATH) as conn:
        cursor = conn.cursor()

        # Validate skill exists in registry
        cursor.execute(
            "SELECT skill_id FROM skill_registry WHERE skill_id = ? LIMIT 1",
            (skill_id,),
        )
        if not cursor.fetchone():
            console.print(
                f"[bold red]Error:[/bold red] Skill ID '{skill_id}' not found in DB."
            )
            return 1

        # Validate agent exists in registry
        cursor.execute(
            "SELECT agent_id FROM agent_registry WHERE agent_id = ? LIMIT 1",
            (agent_id,),
        )
        if not cursor.fetchone():
            console.print(
                f"[bold red]Error:[/bold red] Agent ID '{agent_id}' not found in DB."
            )
            return 1

        if action_clean == "grant":
            cursor.execute(
                """
                INSERT INTO agent_skill_map (agent_id, skill_id)
                VALUES (?, ?)
                ON CONFLICT(agent_id, skill_id) DO NOTHING
                """,
                (agent_id, skill_id),
            )
            console.print(
                f"[bold green]✅ Granted[/bold green] agent '{agent_id}' access to skill '[bold cyan]{skill_id}[/bold cyan]'."
            )

        elif action_clean == "revoke":
            cursor.execute(
                "DELETE FROM agent_skill_map WHERE agent_id = ? AND skill_id = ?",
                (agent_id, skill_id),
            )
            console.print(
                f"[bold green]✅ Revoked[/bold green] agent '{agent_id}' access from skill '[bold cyan]{skill_id}[/bold cyan]'."
            )

        conn.commit()
    return 0


def set_default_action(agent_id: str, action_name: str) -> int:
    """Updates the default_action column in agent_registry for a specific agent."""
    with get_connection(STATE_DB_PATH) as conn:
        cursor = conn.cursor()

        # Ensure action exists in skill_registry and check status
        cursor.execute(
            "SELECT skill_id, status FROM skill_registry WHERE action_name = ? LIMIT 1",
            (action_name,),
        )
        row = cursor.fetchone()
        if not row:
            console.print(
                f"[bold red]Error:[/bold red] Action '{action_name}' does not exist in skill_registry."
            )
            return 1

        if row[1] != "ACTIVE":
            console.print(
                f"[bold yellow]Warning:[/bold yellow] Action '{action_name}' belongs to skill '{row[0]}' which has status '{row[1]}'."
            )

        cursor.execute(
            """
            UPDATE agent_registry
            SET default_action = ?, updated_at = CURRENT_TIMESTAMP
            WHERE agent_id = ?
            """,
            (action_name, agent_id),
        )

        if cursor.rowcount == 0:
            console.print(
                f"[bold red]Error:[/bold red] Agent '{agent_id}' not found in agent_registry."
            )
            return 1

        conn.commit()
        console.print(
            f"[bold green]✅ Set default action for agent '[cyan]{agent_id}[/cyan]' to '[bold yellow]{action_name}[/bold yellow]'."
        )
    return 0


def run_list() -> int:
    """Displays a formatted summary of skill_registry joined with authorized agents."""
    table = Table(title="Charon Skill Registry Inventory (V3 DB State)")
    table.add_column("Skill ID", style="bold white")
    table.add_column("Action Name", style="magenta")
    table.add_column("Status", style="cyan")
    table.add_column("Authorized Agents", style="green")
    table.add_column("Category", style="yellow")

    with get_connection(STATE_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                s.skill_id,
                s.action_name,
                s.status,
                s.category,
                GROUP_CONCAT(DISTINCT asm.agent_id) AS agents
            FROM skill_registry s
            LEFT JOIN agent_skill_map asm ON s.skill_id = asm.skill_id
            GROUP BY s.skill_id, s.action_name, s.status, s.category
            ORDER BY s.skill_id ASC, s.action_name ASC
            """
        )
        rows = cursor.fetchall()
        for row in rows:
            skill_id, action_name, status, category, agents = row
            formatted_agents = agents.replace(",", ", ") if agents else "[dim]None[/dim]"
            table.add_row(
                skill_id,
                action_name,
                status,
                category or "General",
                formatted_agents,
            )

    console.print(table)
    console.print(f"\n[bold]Total Registered Actions:[/bold] {len(rows)}\n")
    return 0