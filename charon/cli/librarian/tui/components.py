"""
charon/cli/librarian/tui/components.py
System Version: v0.2.0 | File Revision: 2.1.0
"""

from typing import Any, Dict, List

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table

from charon.cli.librarian.ingestion import (
    get_quarantine_skills_summary,
    get_staged_skills_summary,
)

console = Console()

def render_header(
    skill_count: int,
    agent_count: int,
    broken_deps_count: int,
    orphan_count: int,
    open_gaps: int,
    resolved_gaps: int,
) -> None:
    """
    Renders the main control panel header using a borderless 2x2 Rich grid layout.
    Strictly expects all state metrics to be passed by the calling controller.
    """
    gap_color = "bold red" if open_gaps > 0 else "dim green"
    broken_color = "bold red" if broken_deps_count > 0 else "dim green"

    console.clear()

    grid = Table.grid(expand=True)
    grid.add_column(justify="left")
    grid.add_column(justify="left")

    grid.add_row(
        f"• Registered System Agents: [bold white]{agent_count}[/bold white]",
        f"• Total Skills Index: [bold white]{skill_count}[/bold white]",
    )
    grid.add_row(
        f"• Open Skill Gaps: [{gap_color}]{open_gaps}[/{gap_color}]",
        f"• Broken Dependencies: [{broken_color}]{broken_deps_count}[/{broken_color}]",
    )

    elements = [
        "[bold cyan]🏛️  CHARON SKILL LIBRARIAN CONTROL PANEL[/bold cyan]",
        "[dim]Interactive Governance & Permission Navigator[/dim]\n",
        grid,
    ]

    if resolved_gaps > 0:
        elements.append(
            f"\n[bold yellow]🧹 MAINTENANCE REQUIRED:[/bold yellow] "
            f"[yellow]{resolved_gaps} resolved gap record(s) pending DB purge & vacuum. "
            f"Select [3] Diagnostics Suite from Main Menu.[/yellow]"
        )

    if orphan_count > 0:
        elements.append(
            f"\n[bold yellow]⚠️  ORPHANED SKILLS:[/bold yellow] "
            f"[yellow]{orphan_count} skills in quarantine path. "
            f"Run option [3] (Diagnostics) to resolve.[/yellow]"
        )

    header_content = Group(*elements)
    console.print(Panel(header_content, border_style="cyan", padding=(0, 2), expand=True))


def render_staged_skills_preview() -> List[Dict[str, Any]]:
    """
    Presentation Layer: Retrieves structured staged and quarantine skill summary data,
    renders a formatted Rich table, and returns the list of items for interactive selection.
    """
    staged_items = get_staged_skills_summary() or []
    quarantine_items = get_quarantine_skills_summary() or []

    all_items = staged_items + quarantine_items

    if not all_items:
        console.print(
            "\n[dim yellow]No staged skills, quarantined items, or unmanifested scripts found.[/dim yellow]"
        )
        return []

    table = Table(
        title="📂 Packages Sitting in Staged & Quarantine Storage Pathways",
        show_header=True,
        header_style="bold yellow",
        border_style="cyan",
    )
    # Added Index Column
    table.add_column("#", justify="right", style="dim")
    table.add_column("Identifier / Pathway", style="bold cyan")
    table.add_column("Type", style="dim white")
    table.add_column("Status", style="bold green")

    for idx, item in enumerate(all_items, start=1):
        status = item.get("status", "Unknown")
        if any(term in status for term in ["Quarantine", "Rejected", "Pending", "QUARANTINED"]):
            status = f"[bold yellow]☣️  {status}[/bold yellow]"
        elif "Ready" in status:
            status = f"[bold green]✅ {status}[/bold green]"
        elif "Missing" in status or "Incomplete" in status or "Unmanifested" in status:
            status = f"[bold red]⚠️  {status}[/bold red]"

        # Added idx string to row rendering
        table.add_row(str(idx), item.get("name", "Unknown"), item.get("type", "Unknown"), status)

    console.print("\n", table, "\n")
    return all_items


def display_skill_table(skills: List[Dict[str, Any]], title: str) -> None:
    """Renders a structured data table of skills with color-coded requirement statuses and DB agent permissions."""
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Skill ID", style="bold white")
    table.add_column("Category", style="cyan")
    table.add_column("Stage", style="blue")
    table.add_column("Authorized Agents", style="green")
    table.add_column("Actions", style="magenta")
    table.add_column("Prerequisites", style="yellow")

    for idx, s in enumerate(skills, start=1):
        auth_list = []
        default_for = s.get("default_for_agents", [])

        for agent in s.get("authorized_agents", []):
            if agent in default_for:
                auth_list.append(f"[bold yellow]⭐ {agent}[/bold yellow]")
            else:
                auth_list.append(agent)

        auth_str = ", ".join(auth_list) if auth_list else "[bold red]Unassigned[/bold red]"

        actions = s.get("supported_actions", {})
        if isinstance(actions, dict):
            actions_list = list(actions.keys())
        elif isinstance(actions, list):
            actions_list = [
                a.get("name") if isinstance(a, dict) else str(a)
                for a in actions
            ]
        else:
            actions_list = []
        actions_str = ", ".join(actions_list) if actions_list else "[dim]None[/dim]"

        reqs = []
        missing_reqs = s.get("missing_requirements", [])
        for r in s.get("system_requirements", []):
            if r in missing_reqs:
                reqs.append(f"[bold red]❌ {r}[/bold red]")
            else:
                reqs.append(f"[bold green]✓ {r}[/bold green]")
        reqs_str = ", ".join(reqs) if reqs else "[dim]None[/dim]"

        table.add_row(
            str(idx),
            s.get("skill_id", "N/A"),
            s.get("category", "General"),
            s.get("stage", "Unknown"),
            auth_str,
            actions_str,
            reqs_str,
        )

    console.print(table)