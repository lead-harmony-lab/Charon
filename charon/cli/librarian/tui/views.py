"""
charon/cli/librarian/tui/views.py
System Version: v0.2.0 | File Revision: 3.3.0

Module:
"""

import sys
from typing import List, Optional

from rich.console import Console
from rich.prompt import Prompt

from charon.cli.database import run_sync
from charon.cli.librarian.tui.components import (
    display_skill_table,
    render_header,
    render_staged_skills_preview,
)
from charon.cli.librarian.tui.discovery import (
    discover_skills,
    get_quarantined_orphans_count,
    get_open_gaps_count,
    get_resolved_gaps_count,
)
from charon.cli.librarian.tui.inspector import inspect_skill_list
from charon.core.skills import SkillLibrarian

console = Console()

__all__ = [
    "render_header",
    "render_staged_skills_preview",
    "display_skill_table",
    "view_catalog",
]


def view_catalog(agents: List[str], librarian: SkillLibrarian, initial_filter: Optional[str] = None):
    """Displays interactive catalog navigation menu and handles filtered views."""
    while True:
        run_sync()
        skills = discover_skills()

        broken_deps_count = sum(1 for s in skills if s.get("missing_requirements"))
        quarantined_count = get_quarantined_orphans_count()
        open_gaps = get_open_gaps_count()
        resolved_gaps = get_resolved_gaps_count()

        render_header(
            skill_count=len(skills),
            agent_count=len(agents),
            broken_deps_count=broken_deps_count,
            orphan_count=quarantined_count,
            open_gaps=open_gaps,
            resolved_gaps=resolved_gaps
        )

        if initial_filter == "agent":
            choice = "3"
            initial_filter = None
        else:
            console.print("\n[bold]Catalog Navigation Filters:[/bold]")
            console.print("  [1] Show All Skills")
            console.print("  [2] Filter by Category")
            console.print("  [3] Filter by Agent Permission")
            console.print("  [4] Show Unassigned Skills")
            console.print("  [5] Preview Staged & Quarantined Storage Pathways")
            console.print("  [B] Back to Main Menu")
            console.print("  [Q] Exit Librarian TUI\n")

            choice = Prompt.ask(
                "Select view", choices=["1", "2", "3", "4", "5", "b", "B", "q", "Q"], default="1"
            )

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

        elif choice == "5":
            # Modified to receive the list and trigger an interactive selection loop
            staged_items = render_staged_skills_preview()

            if not staged_items:
                Prompt.ask("Press Enter to return to catalog menu")
                continue

            console.print("  [B] Back to Catalog Menu\n")
            sel_choices = [str(i) for i in range(1, len(staged_items) + 1)] + ["b", "B"]
            sel = Prompt.ask("Select a package to inspect", choices=sel_choices, default="B")

            if sel.lower() == "b":
                continue

            selected_item = staged_items[int(sel) - 1]
            target_name = selected_item.get("name", "Unknown")

            # First, check if discover_skills() managed to pull a partial record for it
            matched_skill = next((s for s in skills if s.get("skill_id") == target_name), None)

            if matched_skill:
                inspect_skill_list([matched_skill], f"Inspecting Staged Package: {target_name}", agents, librarian)
            else:
                # If it's completely unindexed, we synthesize a shell dictionary
                # so the inspector menu doesn't blow up trying to read non-existent keys.
                synthetic_skill = {
                    "skill_id": target_name,
                    "category": "Unindexed / Staged",
                    "stage": selected_item.get("status", "UNINDEXED"),
                    "authorized_agents": [],
                    "supported_actions": {},
                    "system_requirements": [],
                    "missing_requirements": []
                }
                inspect_skill_list([synthetic_skill], f"Previewing Unindexed Package: {target_name}", agents, librarian)

            continue # Bypass the bottom catch-all inspector

        elif choice.lower() == "b":
            break

        inspect_skill_list(filtered, title, agents, librarian)