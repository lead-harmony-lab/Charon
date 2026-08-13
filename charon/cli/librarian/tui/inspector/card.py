"""Control flow and interaction loops for inspecting skills."""

import sys
from typing import Any, Dict, List
from rich.console import Console
from rich.prompt import Prompt

from charon.cli.librarian.database import run_sync
from charon.cli.librarian.ingestion import run_edit
from charon.cli.librarian.tui.components import display_skill_table
from charon.cli.librarian.tui.inspector.actions import (
    handle_delete,
    handle_grant_permission,
    handle_rename,
    handle_resolve_binaries,
    handle_revoke_permission,
    handle_set_default,
    handle_stage_transition,
)
from charon.cli.librarian.tui.inspector.helpers import hydrate_skill_from_manifest
from charon.cli.librarian.tui.inspector.views import display_plugin_actions_modal, render_skill_card
from charon.core.skills import SkillLibrarian

console = Console()


def inspect_skill_list(
    skills: List[Dict[str, Any]], title: str, agents: List[str], librarian: SkillLibrarian
) -> None:
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
        skill = hydrate_skill_from_manifest(skill)
        missing_reqs, auth_agents = render_skill_card(skill)

        console.print("[bold]Operations:[/bold]")
        console.print("  [1] Grant Agent Permission (SQLite & Manifest)")
        console.print("  [2] Revoke Agent Permission (SQLite & Manifest)")
        console.print("  [3] Set as Default Skill for Agent (SQLite)")

        stage_choice_key = "4"
        if skill.get("stage") == "Staged":
            console.print(f"  [{stage_choice_key}] Promote Staged Skill to Production Dynamic")
        elif skill.get("stage") in ("Dynamic", "User Dynamic"):
            console.print(f"  [{stage_choice_key}] Demote Skill to Quarantine Pathway")

        console.print("  [V] View Root Plugin Action Map")
        console.print("  [E] Edit Manifest in $EDITOR")
        console.print("  [N] Rename Skill ID")

        if missing_reqs:
            console.print("  [bold red][R] ⚠️  Resolve Missing System Binaries (apt install)[/bold red]")

        console.print("  [D] Delete Skill from System")
        console.print("  [B] Back")
        console.print("  [Q] Exit Librarian TUI\n")

        choices = ["1", "2", "3", "4", "v", "V", "e", "E", "n", "N", "d", "D", "b", "B", "q", "Q"]
        if missing_reqs:
            choices.extend(["r", "R"])

        op = Prompt.ask("Select operation", choices=choices, default="B")

        if op.lower() == "q":
            console.print("[bold cyan]Librarian session closed.[/bold cyan]")
            sys.exit(0)
        elif op.lower() == "b":
            break
        elif op.lower() == "v":
            display_plugin_actions_modal(skill)
        elif op.lower() == "e":
            run_edit(skill["skill_id"])
            run_sync()
            was_modified = True
            Prompt.ask("\nPress Enter to refresh skill inspector")
            break
        elif op == "1":
            handle_grant_permission(skill, agents, auth_agents)
        elif op == "2":
            handle_revoke_permission(skill, agents, auth_agents)
        elif op == "3":
            if handle_set_default(skill, auth_agents):
                was_modified = True
        elif op == "4":
            if handle_stage_transition(skill):
                was_modified = True
                break
        elif op.lower() == "n":
            if handle_rename(skill):
                was_modified = True
                break
        elif op.lower() == "r":
            if handle_resolve_binaries(skill, missing_reqs):
                was_modified = True
        elif op.lower() == "d":
            if handle_delete(skill):
                was_modified = True
                break

    return was_modified