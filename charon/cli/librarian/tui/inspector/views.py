"""
charon/cli/librarian/tui/inspector/views.py
System Version: v0.2.0 | File Revision: 3.3.0

Module: UI views and modal components for skill inspection.
"""

from typing import Any, Dict, List
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from charon.cli.database import get_plugin_actions, get_system_action_contract
from charon.cli.librarian.tui.inspector.helpers import (
    extract_action_desc,
    extract_handler_name,
    hydrate_skill_from_manifest,
    parse_list,
    parse_supported_actions,
)

console = Console()


def display_plugin_actions_modal(skill: Dict[str, Any]) -> None:
    """Displays all action_name and handler_name pairs for the root plugin in a formatted table."""
    console.clear()
    skill = hydrate_skill_from_manifest(skill)

    manifest_path = skill.get("manifest_path", "")
    entry_file = skill.get("entry_file_path", "")
    supported = parse_supported_actions(skill.get("supported_actions"))

    actions_list = get_plugin_actions(manifest_path, entry_file)

    if not actions_list and supported:
        actions_list = []
        for act_name, act_data in supported.items():
            actions_list.append({
                "action_name": act_name,
                "handler_name": extract_handler_name(act_data),
                "description": extract_action_desc(act_data),
            })

    table = Table(
        title=f"Root Plugin Action Map: [bold white]{skill['skill_id']}[/bold white]",
        border_style="cyan",
        header_style="bold magenta",
        expand=True,
    )
    table.add_column("Action Name", style="bold yellow", ratio=2)
    table.add_column("Handler Function", style="bold green", ratio=2)
    table.add_column("System Contract", style="bold magenta", ratio=2)
    table.add_column("Description", style="dim", ratio=3)

    if actions_list:
        for item in actions_list:
            act_name = item.get("action_name") or "N/A"
            contract = get_system_action_contract(act_name)
            contract_str = f"⚙️ {contract['reserved_key']} ({contract['required_role']})" if contract else "None"

            table.add_row(
                act_name,
                item.get("handler_name") or "N/A",
                contract_str,
                item.get("description") or "N/A",
            )
    else:
        table.add_row("N/A", "N/A", "None", "No registered actions found for this plugin.")

    console.print(table)
    console.print(f"\n[bold cyan]Root Entry File:[/bold cyan] {entry_file or 'N/A'}")
    console.print(f"[bold cyan]Manifest Path:[/bold cyan]   {manifest_path or 'N/A'}\n")
    Prompt.ask("Press Enter to return to Inspector")


def render_skill_card(skill: Dict[str, Any]) -> tuple[List[str], List[str]]:
    """Renders skill details panel and returns missing_reqs & auth_agents for operational menus."""
    sys_reqs = parse_list(skill.get("system_requirements"))
    missing_reqs = parse_list(skill.get("missing_requirements"))

    reqs = []
    for r in sys_reqs:
        if r in missing_reqs:
            reqs.append(f"[bold red]► ❌ {r} (MISSING ON OS PATH)[/bold red]")
        else:
            reqs.append(f"[bold green]✓ {r} (INSTALLED)[/bold green]")

    urgent_banner = ""
    if missing_reqs:
        urgent_banner = "\n[bold red]⚠️ URGENT: Skill is broken due to missing OS dependencies! Press [R] to resolve.[/bold red]\n"

    auth_agents = parse_list(skill.get("authorized_agents"))
    default_for = parse_list(skill.get("default_for_agents"))

    auth_display = []
    for a in auth_agents:
        if a in default_for:
            auth_display.append(f"[bold yellow]⭐ {a} (DEFAULT)[/bold yellow]")
        else:
            auth_display.append(a)

    action_name = skill.get("action_name")
    handler_name = skill.get("handler_name")
    entry_file = skill.get("entry_file_path") or "N/A"
    supported_actions = parse_supported_actions(skill.get("supported_actions"))

    if not action_name or action_name == "N/A":
        if supported_actions:
            act_keys = list(supported_actions.keys())
            if len(act_keys) == 1:
                action_name = act_keys[0]
                handler_name = extract_handler_name(supported_actions[action_name])
            elif len(act_keys) > 1:
                action_name = f"{act_keys[0]} (+{len(act_keys) - 1} actions)"
                handler_name = extract_handler_name(supported_actions[act_keys[0]])

    action_name = action_name or "N/A"
    handler_name = handler_name or "N/A"

    raw_action = list(supported_actions.keys())[0] if supported_actions else action_name
    system_contract = get_system_action_contract(raw_action)
    contract_banner = ""
    if system_contract:
        mand_str = "Mandatory" if system_contract["is_mandatory"] else "Optional"
        contract_banner = (
            f"[bold magenta]⚙️ System Contract Binding:[/bold magenta] "
            f"[bold white]{system_contract['reserved_key']}[/bold white] "
            f"(Role: [bold yellow]{system_contract['required_role']}[/bold yellow] | {mand_str})\n"
            f"   [dim]{system_contract['description']}[/dim]\n"
        )

    card = (
        f"[bold cyan]Skill ID:[/bold cyan] {skill['skill_id']} [dim](v{skill.get('version', '1.0.0')})[/dim]\n"
        f"[bold cyan]Action Name:[/bold cyan] [bold yellow]{action_name}[/bold yellow]\n"
        f"[bold cyan]Handler Function:[/bold cyan] [bold green]{handler_name}[/bold green]\n"
        f"[bold cyan]Description:[/bold cyan] [italic]{skill.get('description', 'No description provided.')}[/italic]\n"
        f"[bold cyan]Category:[/bold cyan] {skill.get('category', 'N/A')} | "
        f"[bold cyan]Stage:[/bold cyan] {skill.get('stage', 'N/A')}\n"
        f"[bold cyan]Entry File:[/bold cyan] {entry_file}\n"
        f"[bold cyan]Manifest Path:[/bold cyan] {skill.get('manifest_path', 'N/A')}\n\n"
        f"{contract_banner}"
        f"[bold green]Authorized Agents (DB):[/bold green] {', '.join(auth_display) or 'None'}\n"
        f"[bold yellow]System Binaries:[/bold yellow] {', '.join(reqs) or 'None'}\n"
        f"{urgent_banner}"
    )

    console.print(Panel(card, title=f"Inspector: {skill['skill_id']}", border_style="blue", padding=(0, 2), expand=True))
    return missing_reqs, auth_agents