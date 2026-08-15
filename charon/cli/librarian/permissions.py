"""
charon/cli/librarian/permissions.py
System Version: v0.2.0 | File Revision: 2.2.0

Module: CLI permissions controller, default action configuration, inventory views,
and agent registry display commands. Aligned with Schema V3.
"""

import json
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.table import Table

from charon.cli.librarian.db import (
    get_registered_agents,
    get_skill_inventory_db,
    grant_agent_permission_db,
    revoke_agent_permission_db,
    set_agent_default_skill_db,
)
from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
)

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

    if action_clean == "grant":
        success, err_msg = grant_agent_permission_db(skill_id, agent_id)
    else:
        success, err_msg = revoke_agent_permission_db(skill_id, agent_id)

    if not success:
        console.print(f"[bold red]Error:[/bold red] {err_msg}")
        return 1

    if action_clean == "grant":
        console.print(
            f"[bold green]✅ Granted[/bold green] agent '{agent_id}' access to skill '[bold cyan]{skill_id}[/bold cyan]'."
        )
    else:
        console.print(
            f"[bold green]✅ Revoked[/bold green] agent '{agent_id}' access from skill '[bold cyan]{skill_id}[/bold cyan]'."
        )

    return 0


def set_default_action(agent_id: str, action_name: str) -> int:
    """Updates the default_action column in agent_registry for a specific agent."""
    success, err_msg, warning_msg = set_agent_default_skill_db(
        agent_id, action_name
    )

    if warning_msg:
        console.print(f"[bold yellow]Warning:[/bold yellow] {warning_msg}")

    if not success:
        console.print(f"[bold red]Error:[/bold red] {err_msg}")
        return 1

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

    rows = get_skill_inventory_db()
    for row in rows:
        skill_id, action_name, status, category, agents = row
        formatted_agents = (
            agents.replace(",", ", ") if agents else "[dim]None[/dim]"
        )
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