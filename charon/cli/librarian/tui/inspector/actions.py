"""
charon/cli/librarian/tui/inspector/actions.py
System Version: v0.2.0 | File Revision: 3.3.0

Module: Discrete user operation handlers invoked from inspector cards.
"""

import shutil
import sqlite3
import subprocess
import sys
from typing import Any, Dict, List

from rich.console import Console
from rich.prompt import Prompt

from charon.cli.librarian.db import (
    bind_system_action_to_contract,
    get_available_system_contracts,
    grant_agent_permission_db,
    revoke_agent_permission_db,
    run_sync,
    set_agent_default_skill_db,
)
from charon.cli.librarian.lifecycle import (
    run_delete_skill,
    run_demote,
    run_promote,
    run_rename,
)
from charon.cli.librarian.manifest import update_manifest_allowed_agents
from charon.cli.librarian.tui.diagnostics import PACKAGE_MAP
from charon.cli.librarian.tui.inspector.helpers import (
    parse_list,
    parse_supported_actions,
)

console = Console()


def handle_grant_permission(
    skill: Dict[str, Any], agents: List[str], auth_agents: List[str]
) -> None:
    """Handles prompt & execution for granting agent permissions."""
    available_to_grant = [a for a in agents if a not in auth_agents]
    if not available_to_grant:
        console.print(
            "[yellow]All system agents already have permission for this skill.[/yellow]"
        )
        Prompt.ask("Press Enter to continue")
        return

    console.print("\n[bold]Select Agent to Grant Permission:[/bold]")
    for idx, a in enumerate(available_to_grant, start=1):
        console.print(f"  [{idx}] {a}")

    console.print("  [A] Grant to All Agents")
    console.print("  [B] Cancel / Back to Inspector")
    console.print("  [Q] Exit Librarian TUI\n")

    valid_choices = [
        str(i) for i in range(1, len(available_to_grant) + 1)
    ] + ["a", "A", "b", "B", "q", "Q"]
    sel = Prompt.ask("Agent", choices=valid_choices, default="B")

    if sel.lower() == "q":
        console.print("[bold cyan]Librarian session closed.[/bold cyan]")
        sys.exit(0)
    elif sel.lower() == "b":
        return
    elif sel.lower() == "a":
        for target_agent in available_to_grant:
            grant_agent_permission_db(target_agent, skill["skill_id"])
            if target_agent not in auth_agents:
                auth_agents.append(target_agent)

        auth_agents.sort()
        skill["authorized_agents"] = auth_agents
        update_manifest_allowed_agents(skill["manifest_path"], auth_agents)
        run_sync()
        console.print(
            f"[bold green]✓ Granted all remaining agents access to skill '{skill['skill_id']}' in DB & Manifest[/bold green]"
        )
        Prompt.ask("Press Enter to refresh")
    else:
        target_agent = available_to_grant[int(sel) - 1]
        grant_agent_permission_db(target_agent, skill["skill_id"])
        if target_agent not in auth_agents:
            auth_agents.append(target_agent)
        auth_agents.sort()
        skill["authorized_agents"] = auth_agents

        update_manifest_allowed_agents(skill["manifest_path"], auth_agents)
        run_sync()
        console.print(
            f"[bold green]✓ Granted {target_agent} access to skill '{skill['skill_id']}' in DB & Manifest[/bold green]"
        )
        Prompt.ask("Press Enter to refresh")


def handle_revoke_permission(
    skill: Dict[str, Any], agents: List[str], auth_agents: List[str]
) -> None:
    """Handles prompt & execution for revoking agent permissions."""
    if not auth_agents:
        console.print(
            "[yellow]No agents currently granted access in agent_skill_map.[/yellow]"
        )
        Prompt.ask("Press Enter to continue")
        return

    default_for = parse_list(skill.get("default_for_agents"))
    is_full_fleet = len(auth_agents) == len(agents)
    fleet_label = " (Entire Fleet)" if is_full_fleet else ""

    console.print(f"\n[bold]Select Agent to Revoke Permission{fleet_label}:[/bold]")
    for idx, a in enumerate(auth_agents, start=1):
        console.print(f"  [{idx}] {a}")

    console.print("  [A] Revoke All Agents")
    console.print("  [B] Cancel / Back to Inspector")
    console.print("  [Q] Exit Librarian TUI\n")

    valid_choices = [str(i) for i in range(1, len(auth_agents) + 1)] + [
        "a",
        "A",
        "b",
        "B",
        "q",
        "Q",
    ]
    sel = Prompt.ask("Agent", choices=valid_choices, default="B")

    if sel.lower() == "q":
        console.print("[bold cyan]Librarian session closed.[/bold cyan]")
        sys.exit(0)
    elif sel.lower() == "b":
        return

    try:
        if sel.lower() == "a":
            for target_agent in list(auth_agents):
                revoke_agent_permission_db(target_agent, skill["skill_id"])
                if target_agent in auth_agents:
                    auth_agents.remove(target_agent)
                if target_agent in default_for:
                    default_for.remove(target_agent)

            skill["authorized_agents"] = auth_agents
            update_manifest_allowed_agents(skill["manifest_path"], auth_agents)
            run_sync()
            console.print(
                f"[bold green]✓ Revoked all agent access to skill '{skill['skill_id']}' in DB & Manifest[/bold green]"
            )
        else:
            target_agent = auth_agents[int(sel) - 1]
            revoke_agent_permission_db(target_agent, skill["skill_id"])
            if target_agent in auth_agents:
                auth_agents.remove(target_agent)
            if target_agent in default_for:
                default_for.remove(target_agent)

            skill["authorized_agents"] = auth_agents
            update_manifest_allowed_agents(skill["manifest_path"], auth_agents)
            run_sync()
            console.print(
                f"[bold green]✓ Revoked {target_agent} access to skill '{skill['skill_id']}' in DB & Manifest[/bold green]"
            )
    except sqlite3.OperationalError as err:
        console.print(
            f"\n[bold red]❌ Operation Blocked by System Contract Trigger:[/bold red]\n{err}"
        )

    Prompt.ask("Press Enter to refresh")


def handle_set_default(skill: Dict[str, Any], auth_agents: List[str]) -> bool:
    """Handles prompt to assign skill as default for an agent."""
    if not auth_agents:
        console.print(
            "[yellow]No agents are currently authorized for this skill. Grant permission first.[/yellow]"
        )
        Prompt.ask("Press Enter to continue")
        return False

    default_for = parse_list(skill.get("default_for_agents"))

    console.print("\n[bold]Select Agent to Set Default Skill Target:[/bold]")
    for idx, a in enumerate(auth_agents, start=1):
        is_curr_default = " (Already Default)" if a in default_for else ""
        console.print(f"  [{idx}] {a}{is_curr_default}")

    console.print("  [B] Cancel / Back to Inspector")
    console.print("  [Q] Exit Librarian TUI\n")

    valid_choices = [str(i) for i in range(1, len(auth_agents) + 1)] + [
        "b",
        "B",
        "q",
        "Q",
    ]
    sel = Prompt.ask("Agent", choices=valid_choices, default="B")

    if sel.lower() == "q":
        console.print("[bold cyan]Librarian session closed.[/bold cyan]")
        sys.exit(0)
    elif sel.lower() == "b":
        return False

    target_agent = auth_agents[int(sel) - 1]

    set_agent_default_skill_db(target_agent, skill["skill_id"])
    run_sync()

    if target_agent not in default_for:
        default_for.append(target_agent)
    skill["default_for_agents"] = default_for

    console.print(
        f"[bold green]✓ Set '{skill['skill_id']}' as default action for agent '{target_agent}' in SQLite DB[/bold green]"
    )
    Prompt.ask("Press Enter to refresh")
    return True


def handle_stage_transition(skill: Dict[str, Any]) -> bool:
    """Executes lifecycle promotion/demotion transitions."""
    try:
        if skill.get("stage") == "Staged":
            run_promote(skill["skill_id"])
        elif skill.get("stage") in ("Dynamic", "User Dynamic"):
            run_demote(skill["skill_id"])
        Prompt.ask("Press Enter to continue")
        return True
    except sqlite3.OperationalError as err:
        console.print(
            f"\n[bold red]❌ State Transition Aborted by Database Trigger:[/bold red]\n{err}"
        )
        Prompt.ask("Press Enter to continue")
        return False


def handle_rename(skill: Dict[str, Any]) -> bool:
    """Handles renaming a skill ID across system DB and disk."""
    new_id = Prompt.ask("\n[bold cyan]Enter new skill_id[/bold cyan]").strip()
    if new_id and new_id != skill["skill_id"]:
        try:
            run_rename(skill["skill_id"], new_id)
            skill["skill_id"] = new_id
            Prompt.ask("Press Enter to continue")
            return True
        except sqlite3.OperationalError as err:
            console.print(
                f"\n[bold red]❌ Rename Aborted by System Contract Trigger:[/bold red]\n{err}"
            )
            Prompt.ask("Press Enter to continue")
    return False


def handle_resolve_binaries(skill: Dict[str, Any], missing_reqs: List[str]) -> bool:
    """Executes apt dependency auto-resolution."""
    sys_reqs = parse_list(skill.get("system_requirements"))
    apt_pkgs = [PACKAGE_MAP.get(req, req) for req in missing_reqs]
    missing_str = " ".join(apt_pkgs)
    cmd = f"sudo apt-get update && sudo apt-get install -y {missing_str}"

    console.print(f"\n[bold yellow]Executing System Resolver Command:[/bold yellow]\n  {cmd}\n")
    confirm = Prompt.ask("Run command with elevated privileges?", choices=["y", "n"], default="y")

    if confirm.lower() == "y":
        subprocess.run(cmd, shell=True)
        still_missing = [req for req in sys_reqs if not shutil.which(req)]
        skill["missing_requirements"] = still_missing
        skill["health_status"] = "HEALTHY" if not still_missing else "MISSING_PREREQ"
        Prompt.ask("\nPress Enter to refresh health status")
        return True
    return False


def handle_delete(skill: Dict[str, Any]) -> bool:
    """Executes skill removal from system DB and filesystem."""
    confirm = Prompt.ask(
        f"\n[bold red]⚠️ PERMANENT DELETE:[/bold red] Are you sure you want to purge '[bold white]{skill['skill_id']}[/bold white]'?",
        choices=["y", "n"],
        default="n",
    )
    if confirm.lower() == "y":
        try:
            run_delete_skill(skill["skill_id"])
            Prompt.ask("Press Enter to return to catalog")
            return True
        except sqlite3.OperationalError as err:
            console.print(
                f"\n[bold red]❌ Purge Blocked by System Contract Trigger/FK Constraint:[/bold red]\n{err}"
            )
            Prompt.ask("Press Enter to return to Inspector")
    return False


def handle_bind_system_action(
    skill: Dict[str, Any], agent_roles: List[str]
) -> bool:
    """
    Handles prompting and binding a skill's action to a foundational system role contract.
    Filters available contracts by the roles fulfilled by the agents authorized for this skill.
    """
    if not agent_roles:
        console.print(
            "[yellow]The assigned agents do not fulfill any default system roles.[/yellow]"
        )
        Prompt.ask("Press Enter to continue")
        return False

    skill_action_name = skill.get("action_name")
    if not skill_action_name or skill_action_name == "N/A":
        console.print(
            "[bold red]❌ Skill does not have a valid action_name to bind.[/bold red]"
        )
        Prompt.ask("Press Enter to continue")
        return False

    available_contracts = get_available_system_contracts(agent_roles)

    if not available_contracts:
        console.print(
            "[yellow]No system actions are mapped to the roles fulfilled by these agents.[/yellow]"
        )
        Prompt.ask("Press Enter to continue")
        return False

    console.print("\n[bold cyan]Available System Action Contracts:[/bold cyan]")
    for idx, contract in enumerate(available_contracts, start=1):
        r_key, r_role, current_action, desc, is_mand = contract

        mand_flag = "[bold red]*[/bold red]" if is_mand else ""
        if current_action == skill_action_name:
            status = "[bold green](Currently Bound to this Skill)[/bold green]"
        elif current_action:
            status = f"[yellow](Bound to: {current_action})[/yellow]"
        else:
            status = "[dim]Unbound[/dim]"

        console.print(
            f"  [{idx}] {r_key}{mand_flag} [dim]({r_role})[/dim] -> {status}"
        )
        console.print(f"      [dim italic]{desc}[/dim italic]")

    console.print("\n  [B] Cancel / Back to Inspector")
    console.print("  [Q] Exit Librarian TUI\n")

    valid_choices = [str(i) for i in range(1, len(available_contracts) + 1)] + [
        "b",
        "B",
        "q",
        "Q",
    ]
    sel = Prompt.ask(
        "Select System Contract to Bind", choices=valid_choices, default="B"
    )

    if sel.lower() == "q":
        console.print("[bold cyan]Librarian session closed.[/bold cyan]")
        sys.exit(0)
    elif sel.lower() == "b":
        return False

    selected_contract = available_contracts[int(sel) - 1]
    target_reserved_key = selected_contract[0]

    success, message = bind_system_action_to_contract(
        skill_action_name, target_reserved_key
    )

    if success:
        console.print(f"\n[bold green]✓ {message}[/bold green]")
        Prompt.ask("Press Enter to refresh")
        return True
    else:
        console.print(
            f"\n[bold red]❌ Failed to bind system action:[/bold red] {message}"
        )
        Prompt.ask("Press Enter to continue")
        return False