"""
charon/cli/librarian/tui/inspector.py
System Version: v0.6.5 | File Revision: 1.4.0

Module: Detailed skill card inspector, permission assignments, manifest editing,
dependency auto-resolution, system action contract reflection, and lifecycle state mutation handlers.
"""

import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from charon.cli.librarian.database import (
    get_plugin_actions,
    run_sync,
)
from charon.cli.librarian.ingestion import run_edit
from charon.cli.librarian.lifecycle import (
    run_delete_skill,
    run_demote,
    run_promote,
    run_rename,
)
from charon.cli.librarian.tui.components import display_skill_table
from charon.cli.librarian.tui.diagnostics import PACKAGE_MAP
from charon.cli.librarian.tui.discovery import (
    grant_agent_permission,
    revoke_agent_permission,
    set_agent_default_skill,
)
from charon.config.paths import STATE_DB_PATH
from charon.core.skills import SkillLibrarian

console = Console()


def get_system_action_contract(action_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Queries system_actions table to see if an action_name satisfies a system contract."""
    if not action_name or action_name == "N/A":
        return None

    if not STATE_DB_PATH.exists():
        return None

    try:
        with sqlite3.connect(STATE_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT reserved_key, required_role, is_mandatory, description
                FROM system_actions
                WHERE action_name = ?
                """,
                (action_name,),
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
    except sqlite3.Error:
        pass
    return None


def _parse_list(val: Any) -> List[str]:
    """Safely normalizes raw input (strings, JSON strings, lists) into a list of strings."""
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except Exception:
                pass
        return [x.strip() for x in val.split(",") if x.strip()]
    return []


def _parse_supported_actions(actions_raw: Any) -> Dict[str, Any]:
    """Ensures supported_actions is always a dictionary, deserializing JSON strings if necessary."""
    if isinstance(actions_raw, str):
        try:
            actions_raw = json.loads(actions_raw)
        except Exception:
            return {}
    return actions_raw if isinstance(actions_raw, dict) else {}


def _extract_handler_name(action_info: Any) -> str:
    """Extracts handler function name whether action value is a dict or a direct string."""
    if isinstance(action_info, dict):
        return str(action_info.get("handler") or action_info.get("handler_name") or "N/A")
    elif isinstance(action_info, str):
        return action_info
    return "N/A"


def _extract_action_desc(action_info: Any) -> str:
    """Extracts action description safely if present."""
    if isinstance(action_info, dict):
        return str(action_info.get("description") or "")
    return ""


def _hydrate_skill_from_manifest(skill: Dict[str, Any]) -> Dict[str, Any]:
    """Hydrates skill metadata directly from manifest.json on disk."""
    manifest_path_str = skill.get("manifest_path")
    if not manifest_path_str:
        return skill

    manifest_path = Path(manifest_path_str)
    if not manifest_path.exists():
        return skill

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("skill_id"):
            skill["skill_id"] = data["skill_id"]
        if data.get("category"):
            skill["category"] = data["category"]
        if data.get("description"):
            skill["description"] = data["description"]
        if data.get("version"):
            skill["version"] = data["version"]

        entry_point = data.get("entry_point") or data.get("entry_file") or "plugin.py"
        resolved_entry = (manifest_path.parent / entry_point).resolve()
        if resolved_entry.exists():
            skill["entry_file_path"] = str(resolved_entry)
        elif not skill.get("entry_file_path"):
            skill["entry_file_path"] = str(manifest_path.parent / entry_point)

        if "supported_actions" in data:
            skill["supported_actions"] = _parse_supported_actions(data["supported_actions"])
        if "system_requirements" in data and not skill.get("system_requirements"):
            skill["system_requirements"] = _parse_list(data["system_requirements"])
        if "allowed_agents" in data and not skill.get("authorized_agents"):
            skill["authorized_agents"] = _parse_list(data["allowed_agents"])

    except Exception as e:
        console.print(f"[dim red]Warning: Could not read manifest at {manifest_path}: {e}[/dim red]")

    return skill


def update_manifest_allowed_agents(manifest_path: str, agents: List[str]) -> bool:
    """Persists updated allowed_agents array to manifest.json on disk."""
    p = Path(manifest_path)
    if not p.exists():
        console.print(f"[bold red]❌ Manifest file not found at {manifest_path}[/bold red]")
        return False
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["allowed_agents"] = sorted(list(set(agents)))

        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        return True
    except Exception as e:
        console.print(f"[bold red]❌ Failed to update manifest on disk: {e}[/bold red]")
        return False


def display_plugin_actions_modal(skill: Dict[str, Any]):
    """Displays all action_name and handler_name pairs for the root plugin in a formatted table."""
    console.clear()
    skill = _hydrate_skill_from_manifest(skill)

    manifest_path = skill.get("manifest_path", "")
    entry_file = skill.get("entry_file_path", "")
    supported = _parse_supported_actions(skill.get("supported_actions"))

    actions_list = get_plugin_actions(manifest_path, entry_file)

    if not actions_list and supported:
        actions_list = []
        for act_name, act_data in supported.items():
            actions_list.append({
                "action_name": act_name,
                "handler_name": _extract_handler_name(act_data),
                "description": _extract_action_desc(act_data),
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
        skill = _hydrate_skill_from_manifest(skill)

        sys_reqs = _parse_list(skill.get("system_requirements"))
        missing_reqs = _parse_list(skill.get("missing_requirements"))

        reqs = []
        for r in sys_reqs:
            if r in missing_reqs:
                reqs.append(f"[bold red]► ❌ {r} (MISSING ON OS PATH)[/bold red]")
            else:
                reqs.append(f"[bold green]✓ {r} (INSTALLED)[/bold green]")

        urgent_banner = ""
        if missing_reqs:
            urgent_banner = "\n[bold red]⚠️ URGENT: Skill is broken due to missing OS dependencies! Press [R] to resolve.[/bold red]\n"

        auth_agents = _parse_list(skill.get("authorized_agents"))
        default_for = _parse_list(skill.get("default_for_agents"))

        auth_display = []
        for a in auth_agents:
            if a in default_for:
                auth_display.append(f"[bold yellow]⭐ {a} (DEFAULT)[/bold yellow]")
            else:
                auth_display.append(a)

        action_name = skill.get("action_name")
        handler_name = skill.get("handler_name")
        entry_file = skill.get("entry_file_path") or "N/A"

        supported_actions = _parse_supported_actions(skill.get("supported_actions"))

        if not action_name or action_name == "N/A":
            if supported_actions:
                act_keys = list(supported_actions.keys())
                if len(act_keys) == 1:
                    action_name = act_keys[0]
                    handler_name = _extract_handler_name(supported_actions[action_name])
                elif len(act_keys) > 1:
                    action_name = f"{act_keys[0]} (+{len(act_keys) - 1} actions)"
                    handler_name = _extract_handler_name(supported_actions[act_keys[0]])

        action_name = action_name or "N/A"
        handler_name = handler_name or "N/A"

        # Query System Actions Contract
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

        elif op.lower() == "v":
            display_plugin_actions_modal(skill)

        elif op.lower() == "e":
            run_edit(skill["skill_id"])
            run_sync()
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

            console.print("  [A] Grant to All Agents")
            console.print("  [B] Cancel / Back to Inspector")
            console.print("  [Q] Exit Librarian TUI\n")

            valid_choices = [str(i) for i in range(1, len(available_to_grant) + 1)] + ["a", "A", "b", "B", "q", "Q"]
            sel = Prompt.ask("Agent", choices=valid_choices, default="B")

            if sel.lower() == "q":
                console.print("[bold cyan]Librarian session closed.[/bold cyan]")
                sys.exit(0)
            elif sel.lower() == "b":
                continue
            elif sel.lower() == "a":
                for target_agent in available_to_grant:
                    grant_agent_permission(target_agent, skill["skill_id"])
                    if target_agent not in auth_agents:
                        auth_agents.append(target_agent)

                auth_agents.sort()
                skill["authorized_agents"] = auth_agents
                update_manifest_allowed_agents(skill["manifest_path"], auth_agents)

                run_sync()
                console.print(f"[bold green]✓ Granted all remaining agents access to skill '{skill['skill_id']}' in DB & Manifest[/bold green]")
                Prompt.ask("Press Enter to refresh")
            else:
                target_agent = available_to_grant[int(sel) - 1]
                grant_agent_permission(target_agent, skill["skill_id"])
                if target_agent not in auth_agents:
                    auth_agents.append(target_agent)
                auth_agents.sort()
                skill["authorized_agents"] = auth_agents

                update_manifest_allowed_agents(skill["manifest_path"], auth_agents)

                run_sync()
                console.print(f"[bold green]✓ Granted {target_agent} access to skill '{skill['skill_id']}' in DB & Manifest[/bold green]")
                Prompt.ask("Press Enter to refresh")

        elif op == "2":
            if not auth_agents:
                console.print("[yellow]No agents currently granted access in agent_skill_map.[/yellow]")
                Prompt.ask("Press Enter to continue")
                continue

            is_full_fleet = len(auth_agents) == len(agents)
            fleet_label = " (Entire Fleet)" if is_full_fleet else ""

            console.print(f"\n[bold]Select Agent to Revoke Permission{fleet_label}:[/bold]")
            for idx, a in enumerate(auth_agents, start=1):
                console.print(f"  [{idx}] {a}")

            console.print("  [A] Revoke All Agents")
            console.print("  [B] Cancel / Back to Inspector")
            console.print("  [Q] Exit Librarian TUI\n")

            valid_choices = [str(i) for i in range(1, len(auth_agents) + 1)] + ["a", "A", "b", "B", "q", "Q"]
            sel = Prompt.ask("Agent", choices=valid_choices, default="B")

            if sel.lower() == "q":
                console.print("[bold cyan]Librarian session closed.[/bold cyan]")
                sys.exit(0)
            elif sel.lower() == "b":
                continue

            try:
                if sel.lower() == "a":
                    for target_agent in list(auth_agents):
                        revoke_agent_permission(target_agent, skill["skill_id"])
                        if target_agent in auth_agents:
                            auth_agents.remove(target_agent)
                        if target_agent in default_for:
                            default_for.remove(target_agent)

                    skill["authorized_agents"] = auth_agents
                    update_manifest_allowed_agents(skill["manifest_path"], auth_agents)
                    run_sync()
                    console.print(f"[bold green]✓ Revoked all agent access to skill '{skill['skill_id']}' in DB & Manifest[/bold green]")
                else:
                    target_agent = auth_agents[int(sel) - 1]
                    revoke_agent_permission(target_agent, skill["skill_id"])
                    if target_agent in auth_agents:
                        auth_agents.remove(target_agent)
                    if target_agent in default_for:
                        default_for.remove(target_agent)

                    skill["authorized_agents"] = auth_agents
                    update_manifest_allowed_agents(skill["manifest_path"], auth_agents)
                    run_sync()
                    console.print(f"[bold green]✓ Revoked {target_agent} access to skill '{skill['skill_id']}' in DB & Manifest[/bold green]")
            except sqlite3.OperationalError as err:
                console.print(f"\n[bold red]❌ Operation Blocked by System Contract Trigger:[/bold red]\n{err}")

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

            console.print("  [B] Cancel / Back to Inspector")
            console.print("  [Q] Exit Librarian TUI\n")

            valid_choices = [str(i) for i in range(1, len(auth_agents) + 1)] + ["b", "B", "q", "Q"]
            sel = Prompt.ask("Agent", choices=valid_choices, default="B")

            if sel.lower() == "q":
                console.print("[bold cyan]Librarian session closed.[/bold cyan]")
                sys.exit(0)
            elif sel.lower() == "b":
                continue
            else:
                target_agent = auth_agents[int(sel) - 1]
                action_keys = list(supported_actions.keys())

                if not action_keys:
                    console.print("[red]Error: This skill manifest has no registered actions.[/red]")
                    Prompt.ask("Press Enter to continue")
                    continue

                if len(action_keys) == 1:
                    selected_action = action_keys[0]
                else:
                    console.print(f"\n[bold]Select Default Action for '{skill['skill_id']}':[/bold]")
                    for i, act in enumerate(action_keys, start=1):
                        console.print(f"  [{i}] {act}")
                    console.print("  [B] Cancel / Back\n")

                    act_choices = [str(i) for i in range(1, len(action_keys) + 1)] + ["b", "B"]
                    act_sel = Prompt.ask("Action", choices=act_choices, default="B")

                    if act_sel.lower() == "b":
                        continue

                    selected_action = action_keys[int(act_sel) - 1]

                set_agent_default_skill(target_agent, skill["skill_id"], selected_action)
                run_sync()

                if target_agent not in default_for:
                    default_for.append(target_agent)
                skill["default_for_agents"] = default_for

                was_modified = True
                console.print(f"[bold green]✓ Set '{selected_action}' as default action for agent '{target_agent}' in SQLite DB[/bold green]")
                Prompt.ask("Press Enter to refresh")

        elif op == "4":
            try:
                if skill.get("stage") == "Staged":
                    run_promote(skill["skill_id"])
                elif skill.get("stage") in ("Dynamic", "User Dynamic"):
                    run_demote(skill["skill_id"])
                was_modified = True
            except sqlite3.OperationalError as err:
                console.print(f"\n[bold red]❌ State Transition Aborted by Database Trigger:[/bold red]\n{err}")

            Prompt.ask("Press Enter to continue")
            break

        elif op.lower() == "n":
            new_id = Prompt.ask("\n[bold cyan]Enter new skill_id[/bold cyan]").strip()
            if new_id and new_id != skill["skill_id"]:
                try:
                    run_rename(skill["skill_id"], new_id)
                    skill["skill_id"] = new_id
                    was_modified = True
                except sqlite3.OperationalError as err:
                    console.print(f"\n[bold red]❌ Rename Aborted by System Contract Trigger:[/bold red]\n{err}")
                Prompt.ask("Press Enter to continue")
                break

        elif op.lower() == "r":
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
                was_modified = True
                Prompt.ask("\nPress Enter to refresh health status")

        elif op.lower() == "d":
            confirm = Prompt.ask(
                f"\n[bold red]⚠️ PERMANENT DELETE:[/bold red] Are you sure you want to purge '[bold white]{skill['skill_id']}[/bold white]'?",
                choices=["y", "n"],
                default="n",
            )
            if confirm.lower() == "y":
                try:
                    run_delete_skill(skill["skill_id"])
                    was_modified = True
                    Prompt.ask("Press Enter to return to catalog")
                    break
                except sqlite3.OperationalError as err:
                    console.print(f"\n[bold red]❌ Purge Blocked by System Contract Trigger/FK Constraint:[/bold red]\n{err}")
                    Prompt.ask("Press Enter to return to Inspector")

        elif op.lower() == "b":
            break

    return was_modified