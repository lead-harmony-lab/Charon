"""
charon/cli/librarian/tui/views.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Rich visual rendering components, main menu header, and interactive catalog/inspector views.
Includes support for Schema V3 agent-to-skill default action bindings.
"""

import json
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from charon.cli.librarian.database import run_sync
from charon.cli.librarian.ingestion import run_edit
from charon.cli.librarian.lifecycle import (
    run_delete_skill,
    run_demote,
    run_promote,
    run_rename,
)
from charon.cli.librarian.tui.diagnostics import PACKAGE_MAP
from charon.cli.librarian.tui.discovery import (
    discover_skills,
    get_open_gaps_count,
    get_resolved_gaps_count,
    grant_agent_permission,
    revoke_agent_permission,
    set_agent_default_skill,
)
from charon.core.skills import SkillLibrarian

console = Console()


def render_header(skill_count: int, agent_count: int, broken_deps_count: Optional[int] = None):
    """
    Renders the main control panel header using a borderless 2x2 Rich grid layout
    with integrated database maintenance status notifications.
    """
    if broken_deps_count is None:
        skills = discover_skills()
        broken_deps_count = sum(1 for s in skills if s.get("missing_requirements"))
        skill_count = len(skills)

    open_gaps = get_open_gaps_count()
    resolved_gaps = get_resolved_gaps_count()

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
            f"[yellow]{resolved_gaps} resolved gap record(s) pending DB purge & vacuum. Select [3] Diagnostics Suite from Main Menu.[/yellow]"
        )

    header_content = Group(*elements)
    console.print(Panel(header_content, border_style="cyan", padding=(0, 2), expand=True))


def display_skill_table(skills: List[Dict[str, Any]], title: str):
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
            actions_list = [str(a) for a in actions]
        else:
            actions_list = []
        actions_str = ", ".join(actions_list) if actions_list else "[dim]None[/dim]"

        reqs = []
        for r in s.get("system_requirements", []):
            if r in s.get("missing_requirements", []):
                reqs.append(f"[bold red]❌ {r}[/bold red]")
            else:
                reqs.append(f"[bold green]✓ {r}[/bold green]")
        reqs_str = ", ".join(reqs) if reqs else "[dim]None[/dim]"

        table.add_row(str(idx), s["skill_id"], s["category"], s["stage"], auth_str, actions_str, reqs_str)

    console.print(table)


def view_catalog(agents: List[str], librarian: SkillLibrarian, initial_filter: Optional[str] = None):
    """Displays interactive catalog navigation menu and handles filtered views."""
    while True:
        skills = discover_skills()
        broken_deps_count = sum(1 for s in skills if s.get("missing_requirements"))
        render_header(len(skills), len(agents), broken_deps_count)

        if initial_filter == "agent":
            choice = "3"
            initial_filter = None
        else:
            console.print("\n[bold]Catalog Navigation Filters:[/bold]")
            console.print("  [1] Show All Skills")
            console.print("  [2] Filter by Category")
            console.print("  [3] Filter by Agent Permission")
            console.print("  [4] Show Unassigned Skills")
            console.print("  [B] Back to Main Menu")
            console.print("  [Q] Exit Librarian TUI\n")

            choice = Prompt.ask("Select view", choices=["1", "2", "3", "4", "b", "B", "q", "Q"], default="1")

        if choice.lower() == "q":
            console.print("[bold cyan]Librarian session closed.[/bold cyan]")
            sys.exit(0)

        filtered = []
        title = ""

        if choice == "1":
            filtered = skills
            title = "Complete Skill Library Catalog"

        elif choice == "2":
            categories = sorted(list({s["category"] for s in skills}))
            if not categories:
                console.print("\n[yellow]No categorized skills available.[/yellow]")
                Prompt.ask("Press Enter to return")
                continue
            console.print("\n[bold cyan]Available Categories:[/bold cyan]")
            for idx, cat in enumerate(categories, start=1):
                console.print(f"  [{idx}] {cat}")
            console.print("  [B] Back to Catalog Menu")
            console.print("  [Q] Exit Librarian TUI\n")

            cat_choices = [str(i) for i in range(1, len(categories) + 1)] + ["b", "B", "q", "Q"]
            cat_sel = Prompt.ask("Select category", choices=cat_choices, default="B")

            if cat_sel.lower() == "q":
                sys.exit(0)
            elif cat_sel.lower() == "b":
                continue

            target_cat = categories[int(cat_sel) - 1]
            filtered = [s for s in skills if s["category"] == target_cat]
            title = f"Skills in Category: {target_cat}"

        elif choice == "3":
            console.print("\n[bold cyan]Fleet Agents:[/bold cyan]")
            for idx, agent in enumerate(agents, start=1):
                console.print(f"  [{idx}] {agent}")
            console.print("  [B] Back to Catalog Menu")
            console.print("  [Q] Exit Librarian TUI\n")

            agent_choices = [str(i) for i in range(1, len(agents) + 1)] + ["b", "B", "q", "Q"]
            agent_sel = Prompt.ask("Select agent", choices=agent_choices, default="B")

            if agent_sel.lower() == "q":
                sys.exit(0)
            elif agent_sel.lower() == "b":
                continue

            target_agent = agents[int(agent_sel) - 1]
            filtered = [
                s for s in skills if target_agent in s.get("authorized_agents", []) or "*" in s.get("authorized_agents", [])
            ]
            title = f"Skills Authorized for: {target_agent}"

        elif choice == "4":
            filtered = [s for s in skills if not s.get("authorized_agents")]
            title = "Unassigned Skills (No Agent Permissions in DB)"

        elif choice.lower() == "b":
            break

        inspect_skill_list(filtered, title, agents, librarian)


def inspect_skill_list(
    skills: List[Dict[str, Any]], title: str, agents: List[str], librarian: SkillLibrarian
):
    """Loops over a list of skills allowing item selection for detail inspection."""
    if not skills:
        console.print("\n[yellow]No skills match the selected filter.[/yellow]")
        Prompt.ask("\nPress Enter to return")
        return

    while True:
        console.clear()
        display_skill_table(skills, title)
        console.print("\n[bold]Actions:[/bold] Enter item number [#] to inspect/edit, [B] to return, or [Q] to quit.")

        valid_choices = [str(i) for i in range(1, len(skills) + 1)] + ["b", "B", "q", "Q"]
        choice = Prompt.ask("Action", choices=valid_choices, default="B")

        if choice.lower() == "q":
            console.print("[bold cyan]Librarian session closed.[/bold cyan]")
            sys.exit(0)
        elif choice.lower() == "b":
            break
        elif choice.isdigit():
            target_skill = skills[int(choice) - 1]
            was_modified = inspect_skill_card(target_skill, agents, librarian)
            if was_modified:
                break


def inspect_skill_card(skill: Dict[str, Any], agents: List[str], librarian: SkillLibrarian) -> bool:
    """Displays detailed inspector card for a skill. Returns True if structural state changed."""
    was_modified = False
    while True:
        console.clear()
        reqs = []
        for r in skill.get("system_requirements", []):
            if r in skill.get("missing_requirements", []):
                reqs.append(f"[bold red]► ❌ {r} (MISSING ON OS PATH)[/bold red]")
            else:
                reqs.append(f"[bold green]✓ {r} (INSTALLED)[/bold green]")

        urgent_banner = ""
        if skill.get("missing_requirements"):
            urgent_banner = "\n[bold red]⚠️  URGENT: Skill is broken due to missing OS dependencies! Press [R] to resolve.[/bold red]\n"

        auth_agents = skill.get("authorized_agents", [])
        default_for = skill.get("default_for_agents", [])

        auth_display = []
        for a in auth_agents:
            if a in default_for:
                auth_display.append(f"[bold yellow]⭐ {a} (DEFAULT)[/bold yellow]")
            else:
                auth_display.append(a)

        card = (
            f"[bold cyan]Skill ID:[/bold cyan] {skill['skill_id']} [dim](v{skill.get('version', '1.0.0')})[/dim]\n"
            f"[bold cyan]Description:[/bold cyan] [italic]{skill.get('description', 'No description provided.')}[/italic]\n"
            f"[bold cyan]Category:[/bold cyan] {skill['category']} | "
            f"[bold cyan]Stage:[/bold cyan] {skill['stage']}\n"
            f"[bold cyan]Manifest Path:[/bold cyan] {skill['manifest_path']}\n\n"
            f"[bold green]Authorized Agents (DB):[/bold green] {', '.join(auth_display) or 'None'}\n"
            f"[bold yellow]System Binaries:[/bold yellow] {', '.join(reqs) or 'None'}\n"
            f"[bold magenta]Actions Handled:[/bold magenta] {json.dumps(skill.get('supported_actions', {}))}\n"
            f"{urgent_banner}"
        )

        console.print(Panel(card, title=f"Inspector: {skill['skill_id']}", border_style="blue", padding=(0, 2), expand=True))
        console.print("[bold]Operations:[/bold]")
        console.print("  [1] Grant Agent Permission (SQLite)")
        console.print("  [2] Revoke Agent Permission (SQLite)")
        console.print("  [3] Set as Default Skill for Agent (SQLite)")

        stage_choice_key = "4"
        if skill["stage"] == "Staged":
            console.print(f"  [{stage_choice_key}] Promote Staged Skill to Production Dynamic")
        elif skill["stage"] in ("Dynamic", "User Dynamic"):
            console.print(f"  [{stage_choice_key}] Demote Skill to Staged (Quarantine)")

        console.print("  [E] Edit Manifest in $EDITOR")
        console.print("  [N] Rename Skill ID")

        if skill.get("missing_requirements"):
            console.print("  [bold red][R] ⚠️  Resolve Missing System Binaries (apt install)[/bold red]")

        console.print("  [D] Delete Skill from System")
        console.print("  [B] Back")
        console.print("  [Q] Exit Librarian TUI\n")

        choices = ["1", "2", "3", "4", "e", "E", "n", "N", "d", "D", "b", "B", "q", "Q"]

        if skill.get("missing_requirements"):
            choices.extend(["r", "R"])

        op = Prompt.ask("Select operation", choices=choices, default="B")

        if op.lower() == "q":
            console.print("[bold cyan]Librarian session closed.[/bold cyan]")
            sys.exit(0)

        elif op.lower() == "e":
            run_edit(skill["skill_id"])
            run_sync()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()
            was_modified = True
            Prompt.ask("\nPress Enter to refresh skill inspector")
            break

        elif op == "1":
            available_to_grant = [a for a in agents if a not in auth_agents]
            if not available_to_grant:
                console.print("[yellow]All system agents already have permission for this skill.[/yellow]")
                Prompt.ask("Press Enter to continue")
                continue
            console.print("\n[bold]Select Agent to Grant Permission:[/bold]")
            for idx, a in enumerate(available_to_grant, start=1):
                console.print(f"  [{idx}] {a}")
            sel = (
                int(Prompt.ask("Agent", choices=[str(i) for i in range(1, len(available_to_grant) + 1)])) - 1
            )
            target_agent = available_to_grant[sel]

            grant_agent_permission(target_agent, skill["skill_id"])
            run_sync()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()

            skill.setdefault("authorized_agents", []).append(target_agent)
            skill["authorized_agents"].sort()
            console.print(f"[bold green]✓ Granted {target_agent} access to skill '{skill['skill_id']}' in SQLite DB[/bold green]")
            Prompt.ask("Press Enter to refresh")

        elif op == "2":
            if not auth_agents:
                console.print("[yellow]No agents currently granted access in agent_skill_map.[/yellow]")
                Prompt.ask("Press Enter to continue")
                continue
            console.print("\n[bold]Select Agent to Revoke Permission:[/bold]")
            for idx, a in enumerate(auth_agents, start=1):
                console.print(f"  [{idx}] {a}")
            sel = int(Prompt.ask("Agent", choices=[str(i) for i in range(1, len(auth_agents) + 1)])) - 1
            target_agent = auth_agents[sel]

            revoke_agent_permission(target_agent, skill["skill_id"])
            run_sync()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()

            skill["authorized_agents"].remove(target_agent)
            if target_agent in default_for:
                default_for.remove(target_agent)

            console.print(f"[bold green]✓ Revoked {target_agent} access to skill '{skill['skill_id']}' in SQLite DB[/bold green]")
            Prompt.ask("Press Enter to refresh")

        elif op == "3":
            if not auth_agents:
                console.print("[yellow]No agents are currently authorized for this skill. Grant permission first.[/yellow]")
                Prompt.ask("Press Enter to continue")
                continue

            console.print("\n[bold]Select Agent to Set Default Skill Target:[/bold]")
            for idx, a in enumerate(auth_agents, start=1):
                is_curr_default = " (Already Default)" if a in default_for else ""
                console.print(f"  [{idx}] {a}{is_curr_default}")

            sel = int(Prompt.ask("Agent", choices=[str(i) for i in range(1, len(auth_agents) + 1)])) - 1
            target_agent = auth_agents[sel]

            set_agent_default_skill(target_agent, skill["skill_id"])
            run_sync()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()

            if "default_for_agents" not in skill:
                skill["default_for_agents"] = []
            if target_agent not in skill["default_for_agents"]:
                skill["default_for_agents"].append(target_agent)

            was_modified = True
            console.print(f"[bold green]✓ Set '{skill['skill_id']}' as default skill for agent '{target_agent}' in SQLite DB[/bold green]")
            Prompt.ask("Press Enter to refresh")

        elif op == "4":
            if skill["stage"] == "Staged":
                run_promote(skill["skill_id"])
            elif skill["stage"] in ("Dynamic", "User Dynamic"):
                run_demote(skill["skill_id"])

            run_sync()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()
            was_modified = True
            Prompt.ask("Press Enter to continue")
            break

        elif op.lower() == "n":
            new_id = Prompt.ask("\n[bold cyan]Enter new skill_id[/bold cyan]").strip()
            if new_id and new_id != skill["skill_id"]:
                run_rename(skill["skill_id"], new_id)
                run_sync()
                if hasattr(librarian, "reindex_skills"):
                    librarian.reindex_skills()
                skill["skill_id"] = new_id
                was_modified = True
                Prompt.ask("Press Enter to continue")
                break

        elif op.lower() == "r":
            apt_pkgs = [PACKAGE_MAP.get(req, req) for req in skill.get("missing_requirements", [])]
            missing_str = " ".join(apt_pkgs)
            cmd = f"sudo apt-get update && sudo apt-get install -y {missing_str}"
            console.print(f"\n[bold yellow]Executing System Resolver Command:[/bold yellow]\n  {cmd}\n")
            confirm = Prompt.ask("Run command with elevated privileges?", choices=["y", "n"], default="y")

            if confirm.lower() == "y":
                subprocess.run(cmd, shell=True)
                skill["missing_requirements"] = [
                    req for req in skill.get("system_requirements", []) if not shutil.which(req)
                ]
                skill["health_status"] = "HEALTHY" if not skill["missing_requirements"] else "MISSING_PREREQ"
                was_modified = True
                Prompt.ask("\nPress Enter to refresh health status")

        elif op.lower() == "d":
            confirm = Prompt.ask(
                f"\n[bold red]⚠️ PERMANENT DELETE:[/bold red] Are you sure you want to purge '[bold white]{skill['skill_id']}[/bold white]'?",
                choices=["y", "n"],
                default="n",
            )
            if confirm.lower() == "y":
                run_delete_skill(skill["skill_id"])
                run_sync()
                if hasattr(librarian, "reindex_skills"):
                    librarian.reindex_skills()
                was_modified = True
                Prompt.ask("Press Enter to return to catalog")
                break

        elif op.lower() == "b":
            break

    return was_modified