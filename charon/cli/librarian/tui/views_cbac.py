"""
charon/cli/librarian/tui/views_cbac.py
System Version: v0.2.1 | File Revision: 1.0.0

Module: TUI views and interactive wizards for managing CBAC WorkContract governance policies.
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

from charon.cli.librarian.db.cbac import (
    get_contract_by_id,
    get_contract_inventory_db,
    purge_contract_records,
    register_contract_in_db,
    toggle_contract_status_db,
)
from charon.cli.librarian.validators.cbac import (
    validate_cbac_contract,
    validate_cbac_policy,
)
from charon.core.skills import SkillLibrarian

console = Console()

__all__ = [
    "view_cbac_management_menu",
    "inspect_cbac_contract",
    "wizard_register_cbac_contract",
    "wizard_import_cbac_file",
]


def render_cbac_table(contracts: list) -> Table:
    """Generates a formatted Rich Table display for CBAC WorkContracts."""
    table = Table(
        title="[bold cyan]🔐 CBAC WorkContract Governance Policies[/bold cyan]",
        expand=True,
    )
    table.add_column("Index", style="dim", width=6)
    table.add_column("Contract ID", style="bold yellow")
    table.add_column("Policy Name", style="white")
    table.add_column("Agent ID", style="cyan")
    table.add_column("Skill ID", style="green")
    table.add_column("Status", style="bold")
    table.add_column("Rate Limit", style="magenta")
    table.add_column("Token Boundary", style="blue")

    for idx, c in enumerate(contracts, start=1):
        cid, cname, aid, sid, active, rpm, token_limit = c
        status_str = "[green]ACTIVE[/green]" if active else "[red]DISABLED[/red]"
        table.add_row(
            str(idx),
            cid,
            cname,
            aid,
            sid,
            status_str,
            f"{rpm} RPM" if rpm is not None else "∞",
            f"{token_limit} tokens" if token_limit is not None else "∞",
        )
    return table


def inspect_cbac_contract(contract_id: str) -> None:
    """Displays detailed metadata, scope limits, and management toggles for a policy."""
    while True:
        console.clear()
        details = get_contract_by_id(contract_id)

        if not details:
            console.print(f"[bold red]❌ Contract '{contract_id}' not found in database.[/bold red]")
            Prompt.ask("Press Enter to return")
            return

        scope_json = json.dumps(details.get("scope_limits", {}), indent=2)
        scope_syntax = Syntax(scope_json, "json", theme="monokai", line_numbers=True)

        status_fmt = "[bold green]ACTIVE[/bold green]" if details["is_active"] else "[bold red]DISABLED[/bold red]"
        info_text = (
            f"• [bold white]Contract ID:[/bold white] [bold yellow]{details['contract_id']}[/bold yellow]\n"
            f"• [bold white]Policy Name:[/bold white] {details['contract_name']}\n"
            f"• [bold white]Agent ID:[/bold white] [cyan]{details['agent_id']}[/cyan]\n"
            f"• [bold white]Skill ID:[/bold white] [green]{details['skill_id']}[/green]\n"
            f"• [bold white]Status:[/bold white] {status_fmt}\n"
            f"• [bold white]Rate Limit:[/bold white] {details.get('rate_limit_rpm', 'Unlimited')} RPM\n"
            f"• [bold white]Token Boundary:[/bold white] {details.get('token_boundary', 'Unlimited')} max tokens\n"
            f"• [bold white]Last Updated:[/bold white] [dim]{details.get('updated_at', 'N/A')}[/dim]"
        )

        console.print(Panel(info_text, title=f"📋 Contract Details — {contract_id}", border_style="cyan"))
        console.print(Panel(scope_syntax, title="🔒 Scope Limits & Enforcement Constraints", border_style="magenta"))

        toggle_label = "Disable Policy" if details["is_active"] else "Enable Policy"
        console.print("[bold]Contract Management Options:[/bold]")
        console.print(f"  [1] 🔄 {toggle_label}")
        console.print("  [2] 🗑️  Purge Contract Policy")
        console.print("  [B] ⬅️  Back to CBAC Overview\n")

        choice = Prompt.ask("Select action", choices=["1", "2", "b", "B"], default="B")

        if choice.lower() == "b":
            break
        elif choice == "1":
            new_status = not details["is_active"]
            if toggle_contract_status_db(contract_id, new_status):
                console.print(f"[bold green]✓ Status updated to {'ACTIVE' if new_status else 'DISABLED'}.[/bold green]")
            else:
                console.print("[bold red]❌ Failed to update contract status.[/bold red]")
            Prompt.ask("Press Enter to continue")
        elif choice == "2":
            if Confirm.ask(f"[bold red]Permanently purge contract '{contract_id}'?[/bold red]"):
                if purge_contract_records(contract_id):
                    console.print(f"[bold green]✓ Contract '{contract_id}' purged successfully.[/bold green]")
                    Prompt.ask("Press Enter to return")
                    break
                else:
                    console.print("[bold red]❌ Failed to purge contract record.[/bold red]")
                    Prompt.ask("Press Enter to continue")


def wizard_import_cbac_file() -> None:
    """Interactive wizard to load, validate, and persist a CBAC contract JSON file."""
    console.clear()
    console.print(
        Panel(
            "[bold cyan]📥 IMPORT CBAC CONTRACT FROM JSON FILE[/bold cyan]\n"
            "[dim]Provide a path to a JSON file matching the CBACWorkContract schema[/dim]",
            border_style="cyan",
        )
    )

    path_input = Prompt.ask("Enter JSON file path (or 'b' to cancel)").strip()
    if not path_input or path_input.lower() == "b":
        return

    file_path = Path(path_input).expanduser().resolve()
    is_valid, errors, payload = validate_cbac_policy(file_path)

    if not is_valid:
        console.print(f"\n[bold red]❌ Validation Failed for '{file_path}':[/bold red]")
        for err in errors:
            console.print(f"  • {err}")
        Prompt.ask("\nPress Enter to return")
        return

    success, err_msg = register_contract_in_db(
        contract_id=payload["contract_id"],
        contract_name=payload["contract_name"],
        agent_id=payload["agent_id"],
        skill_id=payload["skill_id"],
        scope_limits=payload.get("scope_limits"),
        rate_limit_rpm=payload.get("rate_limit_rpm", 60),
        token_boundary=payload.get("token_boundary", 4096),
        is_active=payload.get("is_active", True),
    )

    if success:
        console.print(
            f"\n[bold green]✅ Contract '{payload['contract_id']}' registered successfully from file![/bold green]"
        )
    else:
        console.print(f"\n[bold red]❌ Database Registration Error:[/bold red] {err_msg}")

    Prompt.ask("\nPress Enter to return")


def wizard_register_cbac_contract() -> None:
    """Interactive form step-through to build and register a CBAC WorkContract."""
    console.clear()
    console.print(
        Panel(
            "[bold cyan]📝 REGISTER NEW CBAC WORKCONTRACT[/bold cyan]\n"
            "[dim]Define policy metadata, capability scope limits, and rate thresholds[/dim]",
            border_style="cyan",
        )
    )

    contract_id = Prompt.ask("Contract ID (slug)").strip()
    if not contract_id or contract_id.lower() == "b":
        return

    contract_name = Prompt.ask("Contract Name", default=f"{contract_id.title()} Policy").strip()
    agent_id = Prompt.ask("Target Agent ID (or '*' for wildcard)", default="*").strip()
    skill_id = Prompt.ask("Target Skill ID (or '*' for wildcard)", default="*").strip()

    rpm_str = Prompt.ask("Rate Limit RPM (enter 0 or empty for unlimited)", default="60").strip()
    rpm = int(rpm_str) if rpm_str.isdigit() and int(rpm_str) > 0 else None

    token_str = Prompt.ask("Token Limit Boundary (enter 0 or empty for unlimited)", default="4096").strip()
    token_boundary = int(token_str) if token_str.isdigit() and int(token_str) > 0 else None

    payload = {
        "contract_id": contract_id,
        "contract_name": contract_name,
        "agent_id": agent_id,
        "skill_id": skill_id,
        "scope_limits": {
            "allowed_actions": ["*"],
            "network_egress": False,
        },
        "rate_limit_rpm": rpm,
        "token_boundary": token_boundary,
        "is_active": True,
    }

    is_valid, errors = validate_cbac_contract(payload)
    if not is_valid:
        console.print("\n[bold red]❌ Input Policy Validation Error:[/bold red]")
        for err in errors:
            console.print(f"  • {err}")
        Prompt.ask("\nPress Enter to return")
        return

    success, err_msg = register_contract_in_db(
        contract_id=payload["contract_id"],
        contract_name=payload["contract_name"],
        agent_id=payload["agent_id"],
        skill_id=payload["skill_id"],
        scope_limits=payload["scope_limits"],
        rate_limit_rpm=payload["rate_limit_rpm"],
        token_boundary=payload["token_boundary"],
        is_active=payload["is_active"],
    )

    if success:
        console.print(f"\n[bold green]✅ Contract '{contract_id}' created and activated![/bold green]")
    else:
        console.print(f"\n[bold red]❌ Database Persistence Failed:[/bold red] {err_msg}")

    Prompt.ask("\nPress Enter to return")


def view_cbac_management_menu(agents: List[str], librarian: SkillLibrarian) -> None:
    """Main entrypoint loop for the CBAC Contract & Permission Management sub-screen."""
    while True:
        console.clear()
        contracts = get_contract_inventory_db()

        if not contracts:
            console.print(
                Panel(
                    "[yellow]No active CBAC WorkContracts registered in the database.[/yellow]",
                    title="[bold yellow]🔐 CBAC Policy Inventory[/bold yellow]",
                    border_style="yellow",
                )
            )
        else:
            console.print(render_cbac_table(contracts))

        console.print("\n[bold]CBAC Operations:[/bold]")
        console.print("  [1-N] Inspect / Manage Policy by Row Index")
        console.print("  [A]   Add / Scaffold New CBAC Contract (Interactive)")
        console.print("  [I]   Import Contract Policy from JSON File")
        console.print("  [B]   Back to Main Menu")
        console.print("  [Q]   Exit Librarian TUI\n")

        valid_choices = (
            [str(i) for i in range(1, len(contracts) + 1)]
            + ["a", "A", "i", "I", "b", "B", "q", "Q"]
        )
        choice = Prompt.ask("Select action or contract index", choices=valid_choices, default="B")

        if choice.lower() == "q":
            console.print("[bold cyan]Librarian session closed.[/bold cyan]")
            sys.exit(0)
        elif choice.lower() == "b":
            break
        elif choice.lower() == "a":
            wizard_register_cbac_contract()
        elif choice.lower() == "i":
            wizard_import_cbac_file()
        elif choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(contracts):
                target_cid = contracts[idx - 1][0]
                inspect_cbac_contract(target_cid)