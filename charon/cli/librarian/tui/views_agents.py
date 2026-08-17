"""
charon/cli/librarian/tui/views_agents.py
System Version: v0.2.1 | File Revision: 1.0.0

Module: Interactive Agent & Capability-Based Access Control (CBAC) TUI view.
Renders agent matrices, detail inspectors, and capability modification loops.
"""

import sys
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

console = Console()


def render_agent_matrix(agents: List[str], librarian: Any) -> Table:
    """Builds a styled Rich Table displaying active agents and permission posture."""
    table = Table(
        title="[bold cyan]🤖 Registered Agent Permission Matrix[/bold cyan]",
        expand=True,
        border_style="cyan",
        header_style="bold magenta",
    )
    table.add_column("Agent ID", style="bold white", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Allowed Skills", justify="center", style="yellow")
    table.add_column("Access Tier", style="dim green")
    table.add_column("CBAC Policy", style="dim cyan")

    repo = getattr(librarian, "agent_repo", None)

    for agent_id in agents:
        status = "[bold green]Active[/bold green]"
        allowed_skills_count = "All (*)"
        tier = "Standard"
        policy_mode = "Enforced"

        if repo and hasattr(repo, "get_agent"):
            agent_obj = repo.get_agent(agent_id)
            if agent_obj:
                is_active = getattr(agent_obj, "is_active", True)
                status = "[bold green]Active[/bold green]" if is_active else "[bold red]Disabled[/bold red]"
                skills = getattr(agent_obj, "allowed_skills", None)
                allowed_skills_count = str(len(skills)) if isinstance(skills, list) else "All (*)"
                tier = getattr(agent_obj, "tier", "Standard")
                policy_mode = getattr(agent_obj, "policy_mode", "Enforced")

        table.add_row(agent_id, status, allowed_skills_count, tier, policy_mode)

    return table


def inspect_agent_detail(agent_id: str, librarian: Any) -> None:
    """Displays detailed metadata, assigned capabilities, and raw CBAC policy JSON."""
    repo = getattr(librarian, "agent_repo", None)
    agent_data: Dict[str, Any] = {"agent_id": agent_id, "status": "active", "tier": "Standard", "allowed_skills": ["*"]}

    if repo and hasattr(repo, "get_agent"):
        obj = repo.get_agent(agent_id)
        if obj and hasattr(obj, "to_dict"):
            agent_data = obj.to_dict()

    console.clear()
    console.print(
        Panel(
            f"[bold cyan]🔍 Agent Inspector — {agent_id}[/bold cyan]\n"
            f"[dim]Review active capabilities, isolation scope, and CBAC policy settings[/dim]",
            border_style="cyan",
        )
    )

    info_text = (
        f"• [bold white]Agent Identifier:[/bold white] [bold cyan]{agent_id}[/bold cyan]\n"
        f"• [bold white]Status:[/bold white] {agent_data.get('status', 'Active')}\n"
        f"• [bold white]Access Tier:[/bold white] [green]{agent_data.get('tier', 'Standard')}[/green]\n"
        f"• [bold white]Allowed Skill Scope:[/bold white] [yellow]{agent_data.get('allowed_skills', ['*'])}[/yellow]\n"
    )

    console.print(Panel(info_text, title="[bold white]Overview[/bold white]", border_style="dim cyan"))

    # Render contract JSON
    raw_policy = agent_data.get("cbac_policy", {"version": "1.0", "default_action": "DENY", "agent_id": agent_id})
    import json
    policy_str = json.dumps(raw_policy, indent=2)
    syntax = Syntax(policy_str, "json", theme="monokai", line_numbers=True)

    console.print(Panel(syntax, title="[bold cyan]CBAC Policy Definition[/bold cyan]", border_style="cyan"))
    Prompt.ask("\nPress Enter to return to Agent Matrix")


def modify_agent_permissions(agent_id: str, librarian: Any) -> None:
    """Interactive loop to assign/revoke skill execution rights for an agent."""
    repo = getattr(librarian, "agent_repo", None)

    console.print(f"\n[bold yellow]Modifying Capability Policy for agent:[/bold yellow] [bold white]{agent_id}[/bold white]")
    new_skill = Prompt.ask("Enter skill_id to grant (or '*' for full access, 'b' to cancel)").strip()

    if not new_skill or new_skill.lower() == "b":
        return

    if repo and hasattr(repo, "grant_skill"):
        try:
            repo.grant_skill(agent_id, new_skill)
            console.print(f"[bold green]✓ Successfully granted skill '{new_skill}' to {agent_id}[/bold green]")
        except Exception as e:
            console.print(f"[bold red]❌ Failed to update agent repo:[/bold red] {e}")
    else:
        console.print(f"[dim yellow]ℹ️ Mock Mode: Granted '{new_skill}' permission to {agent_id}[/dim yellow]")

    Prompt.ask("\nPress Enter to continue")


def view_agents_management_menu(agents: List[str], librarian: Any) -> None:
    """Main interactive management menu loop for Agent Administration and CBAC."""
    while True:
        console.clear()
        matrix_table = render_agent_matrix(agents, librarian)
        console.print(matrix_table)

        console.print("\n[bold white]Agent Actions:[/bold white]")
        console.print("  [1] 🔍 Inspect Agent CBAC Policy & Details")
        console.print("  [2] 🔐 Grant/Revoke Skill Permissions")
        console.print("  [3] ➕ Register New Agent ID")
        console.print("  [B] Back to Main Menu")
        console.print("  [Q] Exit Librarian TUI\n")

        choice = Prompt.ask("Select option", choices=["1", "2", "3", "b", "B", "q", "Q"], default="1")

        if choice.lower() == "q":
            console.print("[bold cyan]Librarian session closed.[/bold cyan]")
            sys.exit(0)
        elif choice.lower() == "b":
            break

        elif choice == "1":
            target_agent = Prompt.ask("Enter Agent ID to inspect", choices=agents, default=agents[0] if agents else "")
            if target_agent:
                inspect_agent_detail(target_agent, librarian)

        elif choice == "2":
            target_agent = Prompt.ask("Enter Agent ID to edit", choices=agents, default=agents[0] if agents else "")
            if target_agent:
                modify_agent_permissions(target_agent, librarian)

        elif choice == "3":
            new_id = Prompt.ask("Enter new Agent ID (e.g., 'agent-code-assistant')").strip()
            if new_id and new_id not in agents:
                agents.append(new_id)
                agents.sort()
                console.print(f"[bold green]✓ Agent '{new_id}' registered successfully.[/bold green]")
                Prompt.ask("Press Enter to continue")
            elif new_id in agents:
                console.print(f"[bold red]❌ Agent '{new_id}' already exists.[/bold red]")
                Prompt.ask("Press Enter to try again")