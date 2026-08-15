"""
charon/cli/librarian/tui/diagnostics.py
System Version: v0.2.0 | File Revision: 3.1.0

Module: Diagnostic UI View. Handles presentation layer and user prompting.
All business logic is delegated to diagnostics_core.py and charon.cli.librarian.db.
"""

import sys
from typing import Dict, List

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from charon.cli.database import (
    flag_quarantined_orphans,
    perform_state_audit,
    run_sync,
)
from charon.cli.librarian.ingestion import flag_quarantined_orphans as sync_orphans
from charon.cli.librarian.purge_gaps import purge_resolved_gaps
from charon.cli.librarian.tui.discovery import (
    discover_skills,
    get_quarantined_orphans_count,
    get_resolved_gaps_count,
)
from charon.core.skills import SkillLibrarian

from charon.cli.librarian.diagnostics_core import (
    PACKAGE_MAP,
    build_apt_command,
    cleanup_orphaned_agent_mappings,
    delete_quarantined_skill,
    execute_apt_command,
    get_deficient_skills,
    get_quarantined_skills,
    normalize_manifest_action_contracts,
    process_ast_healing,
    repair_quarantined_skill,
)

console = Console()


def run_diagnostics_suite(librarian: SkillLibrarian) -> None:
    """Main interactive entry point for Option [3]: Diagnostics & Maintenance."""
    while True:
        sync_orphans()

        skills = discover_skills()
        broken_skills = [s for s in skills if s.get("missing_requirements")]
        unassigned_skills = [s for s in skills if not s.get("authorized_agents")]
        resolved_gaps = get_resolved_gaps_count()
        quarantine_count = get_quarantined_orphans_count()

        console.clear()

        grid = Table.grid(expand=True)
        grid.add_column(justify="left")
        grid.add_column(justify="left")

        broken_style = "bold red" if broken_skills else "dim green"
        grid.add_row(
            f"• Total Skills Audited: [bold white]{len(skills)}[/bold white]",
            f"• Broken Binary Dependencies: [{broken_style}]{len(broken_skills)}[/{broken_style}]",
        )

        db_status = "NEEDS PURGE" if resolved_gaps > 0 else "OK"
        db_color = "bold yellow" if resolved_gaps > 0 else "bold green"
        unassigned_style = "bold yellow" if unassigned_skills else "dim green"

        grid.add_row(
            f"• Unassigned Skills: [{unassigned_style}]{len(unassigned_skills)}[/{unassigned_style}]",
            f"• Database Registry: [{db_color}]{db_status}[/{db_color}]",
        )

        elements = [
            "[bold cyan]🛠️  CHARON LIBRARIAN DIAGNOSTICS & MAINTENANCE SUITE[/bold cyan]",
            "[dim]System Health Audit & Automated Repair Center[/dim]\n",
            grid,
        ]

        if quarantine_count > 0:
            elements.append(
                f"\n[bold yellow]⚠️  ORPHANED SKILLS:[/bold yellow] "
                f"[yellow]{quarantine_count} skill(s) currently in quarantine. "
                f"Select [5] to review and resolve.[/yellow]"
            )

        if resolved_gaps > 0:
            elements.append(
                f"\n[bold yellow]🧹 MAINTENANCE REQUIRED:[/bold yellow] "
                f"[yellow]{resolved_gaps} resolved gap record(s) pending DB purge & vacuum. "
                f"Select [4] to audit and purge.[/yellow]"
            )

        header = Group(*elements)
        console.print(Panel(header, border_style="cyan", padding=(0, 2), expand=True))

        console.print("\n[bold]Diagnostic Suite Operations:[/bold]")
        console.print("  [1] 🔍 Run System Dependency Audit")

        if broken_skills:
            console.print("  [2] [bold red]⚠️  Batch Resolve All Missing Binaries (apt install)[/bold red]")
        else:
            console.print("  [2] [dim]Batch Resolve Missing Binaries (No broken dependencies detected)[/dim]")

        console.print("  [3] 🔄 Re-index Database & Re-sync Manifests")

        purge_status = f"[bold yellow]({resolved_gaps} pending purge)[/bold yellow]" if resolved_gaps > 0 else "[dim](Clean)[/dim]"
        console.print(f"  [4] 📋 Audit SQLite State Drift & Vacuum DB {purge_status}")

        if quarantine_count > 0:
            console.print(f"  [5] [bold yellow]⚠️  Review & Manage Quarantined Skills ({quarantine_count} Action Required)[/bold yellow]")
        else:
            console.print("  [5] 🔬 Review & Manage Quarantined Skills")

        console.print("  [6] 🩹 Heal Manifest Parameters & Artifacts via AST")
        console.print("  [B] Back to Main Menu")
        console.print("  [Q] Exit Librarian TUI\n")

        choices = ["1", "2", "3", "4", "5", "6", "b", "B", "q", "Q"]
        choice = Prompt.ask("Select operation", choices=choices, default="1")

        if choice.lower() == "q":
            console.print("[bold cyan]Librarian session closed.[/bold cyan]")
            sys.exit(0)
        elif choice.lower() == "b":
            break
        elif choice == "1":
            _render_audit_report(skills)
        elif choice == "2":
            if broken_skills:
                _ui_resolve_dependencies(broken_skills)
            else:
                console.print("\n[bold green]✓ All registered skills have healthy dependencies![/bold green]")
                Prompt.ask("Press Enter to continue")
        elif choice == "3":
            _ui_maintenance_routine(librarian)
            Prompt.ask("\nPress Enter to continue")
        elif choice == "4":
            _ui_drift_audit(resolved_gaps)
        elif choice == "5":
            _ui_review_quarantine()
        elif choice == "6":
            _ui_heal_manifests()


def _render_audit_report(skills: List[Dict]) -> None:
    console.clear()
    table = Table(title="Diagnostic System Audit", show_header=True, header_style="bold cyan")
    table.add_column("Skill ID", style="bold white")
    table.add_column("Stage", style="blue")
    table.add_column("Status", style="bold")
    table.add_column("Missing Binaries", style="yellow")
    table.add_column("APT Package Mapping", style="magenta")

    for s in skills:
        missing = s.get("missing_requirements", [])
        if missing:
            packages = [PACKAGE_MAP.get(m, m) for m in missing]
            table.add_row(
                s.get("skill_id", "N/A"), s.get("stage", "Unknown"),
                "[bold red]CRITICAL[/bold red]", ", ".join(missing), ", ".join(packages)
            )
        else:
            table.add_row(
                s.get("skill_id", "N/A"), s.get("stage", "Unknown"),
                "[bold green]HEALTHY[/bold green]", "[dim]None[/dim]", "[dim]N/A[/dim]"
            )
    console.print(table)
    Prompt.ask("\nPress Enter to return to Diagnostics Menu")


def _ui_resolve_dependencies(broken_skills: List[Dict]) -> None:
    console.clear()
    missing_binaries, pkg_str, cmd = build_apt_command(broken_skills)

    console.print("[bold red]⚠️  DEPENDENCY RESOLUTION TARGETS DETECTED[/bold red]\n")
    console.print(f"  [bold]Missing Binaries ($PATH):[/bold] {', '.join(missing_binaries)}")
    console.print(f"  [bold]Target APT Packages:[/bold]      [cyan]{pkg_str}[/cyan]")
    console.print(f"  [bold]Execution Command:[/bold]        [dim]{cmd}[/dim]\n")

    if Prompt.ask("Execute package installation with elevated privileges?", choices=["y", "n"], default="y").lower() == "y":
        execute_apt_command(cmd)
        Prompt.ask("\nPress Enter to return and refresh diagnostic health state")


def _ui_maintenance_routine(librarian: SkillLibrarian) -> None:
    console.print("\n[bold cyan]🔧 Executing Full Database & Contract Maintenance...[/bold cyan]\n")

    flagged = flag_quarantined_orphans()
    console.print(f"  • Filesystem entry check: [bold yellow]{flagged} flagged[/bold yellow]" if flagged else "  • Filesystem entry check: [green]OK[/green]")

    updated_manifests = normalize_manifest_action_contracts(librarian)
    console.print(f"  • Contract Normalization: [bold green]{updated_manifests} rewritten[/bold green]" if updated_manifests else "  • 3-node action contract formatting: [green]IN SYNC[/green]")

    purged_maps = cleanup_orphaned_agent_mappings()
    console.print(f"  • Agent mapping integrity: [bold yellow]{purged_maps} purged[/bold yellow]" if purged_maps else "  • Agent mapping integrity: [green]OK[/green]")

    sync_result = run_sync()
    console.print(
        f"  • Filesystem re-index: [bold green]COMPLETE[/bold green] "
        f"([bold white]{sync_result['registered_handlers']}[/bold white] handlers active)"
    )

    if hasattr(librarian, "reindex_skills"):
        librarian.reindex_skills()
        console.print("  • SkillLibrarian AST contract re-index: [green]COMPLETE[/green]")

    console.print("\n[bold green]✅ Database and action contract maintenance complete.[/bold green]")


def _render_drift_audit_report(audit_data: Dict) -> None:
    """Renders formatted Rich tables and status text for state drift analysis."""
    skills = audit_data.get("skills", [])
    orphaned_mappings = audit_data.get("orphaned_mappings", [])
    drift_count = audit_data.get("drift_count", 0)

    if not skills and not orphaned_mappings:
        console.print("[yellow]No skills discovered in SQLite or on disk.[/yellow]")
        return

    table = Table(title="Charon Skill Registry vs Filesystem Audit")
    table.add_column("Manifest Skill ID", style="bold white")
    table.add_column("Category", style="cyan")
    table.add_column("Disk Actions", justify="center")
    table.add_column("DB Indexed Actions", justify="center")
    table.add_column("Drift Analysis", style="yellow")

    for item in skills:
        status = item["status"]
        disk_cnt = item["disk_count"]
        db_cnt = item["db_count"]

        if status == "UNINDEXED":
            analysis = "[bold red]Unindexed Skill[/bold red] (Run sync to index)"
        elif status == "PARTIAL":
            analysis = f"[bold yellow]Partial Actions Indexed[/bold yellow] ({item['missing_actions']} missing)"
        else:
            analysis = "[dim green]In Sync[/dim green]"

        table.add_row(item["skill_id"], item["category"], str(disk_cnt), str(db_cnt), analysis)

    console.print(table)

    if orphaned_mappings:
        console.print(f"\n[bold red]⚠️ agent_skill_map Integrity Faults ({len(orphaned_mappings)} found):[/bold red]")
        map_table = Table(title="Orphaned Agent Skill Mappings")
        map_table.add_column("Agent ID", style="bold cyan")
        map_table.add_column("Missing Skill ID", style="bold red")
        for agent_id, skill_id in orphaned_mappings:
            map_table.add_row(agent_id, skill_id)
        console.print(map_table)

    if drift_count > 0:
        console.print(
            f"\n[bold yellow]⚠️ State Drift Detected:[/bold yellow] {drift_count} inconsistency(ies) found. "
            f"Run [cyan]charon librarian sync[/cyan] to align database index with filesystem."
        )
    else:
        console.print("\n[bold green]✅ Database, agent_skill_map, and Filesystem are 100% in sync.[/bold green]")


def _ui_drift_audit(resolved_gaps: int) -> None:
    console.clear()
    console.print("[bold cyan]📋 SQLite vs Filesystem State Drift Audit[/bold cyan]\n")
    flag_quarantined_orphans()

    audit_data = perform_state_audit()
    _render_drift_audit_report(audit_data)

    purged_maps = cleanup_orphaned_agent_mappings()
    if purged_maps > 0:
        console.print(f"[bold yellow]✓ Cleaned {purged_maps} orphaned agent_skill_map row(s).[/bold yellow]")

    if resolved_gaps > 0:
        console.print(f"\n[bold yellow]⚠️ State Drift Detected: {resolved_gaps} resolved gap(s) pending purge.[/bold yellow]")
        if Prompt.ask("Purge resolved gaps and vacuum database?", choices=["y", "n"], default="y").lower() == "y":
            purged = purge_resolved_gaps()
            console.print(f"[bold green]✓ Purged {purged} gap record(s) and vacuumed database.[/bold green]")
    Prompt.ask("\nPress Enter to continue")


def _ui_review_quarantine() -> None:
    orphans = get_quarantined_skills()
    if not orphans:
        console.print("\n[bold green]✅ No quarantined skills found. Everything is clean.[/bold green]")
        Prompt.ask("\nPress Enter to return")
        return

    console.clear()
    console.print(f"[bold yellow]⚠️  Found {len(orphans)} Quarantined Skill(s):[/bold yellow]\n")

    for skill_id, path_str, reason in orphans:
        console.print("-" * 60)
        console.print(f"[bold]Skill ID :[/bold] {skill_id}\n[bold]Path     :[/bold] {path_str}\n[bold]Reason   :[/bold] [red]{reason}[/red]")
        console.print("-" * 60)

        choice = Prompt.ask(
            f"Action for '{skill_id}' ([bold cyan]R[/bold cyan]echeck, [bold red]D[/bold red]elete, [dim]S[/dim]kip, [dim]B[/dim]ack, [dim]Q[/dim]uit)",
            choices=["r", "d", "s", "b", "q"], default="s", show_choices=False, show_default=True,
        ).lower()

        if choice == "q":
            sys.exit(0)
        elif choice == "b":
            return
        elif choice == "d":
            delete_quarantined_skill(skill_id)
            console.print(f"[bold green]🗑️  Deleted '{skill_id}' from registry.[/bold green]\n")
        elif choice == "r":
            if repair_quarantined_skill(skill_id, path_str):
                console.print(f"[bold green]✅ Repaired! '{skill_id}' is now ACTIVE.[/bold green]\n")
            else:
                console.print(f"[bold red]❌ Failed: Files for '{skill_id}' are still missing or invalid.[/bold red]\n")

    Prompt.ask("\nPress Enter to return to Diagnostics Menu")


def _ui_heal_manifests() -> None:
    console.clear()
    console.print("[bold cyan]🩹 Manifest Parameter & Artifact Auto-Healer[/bold cyan]\n")

    deficient_skills = get_deficient_skills()
    if not deficient_skills:
        console.print("[bold green]✅ All skill manifests are fully populated. Audit complete.[/bold green]")
        Prompt.ask("\nPress Enter to return")
        return

    console.print(
        f"Found [bold yellow]{len(deficient_skills)}[/bold yellow] skill action(s) missing metadata in the DB. Starting AST extraction...\n")

    healed, verified, not_found = process_ast_healing(deficient_skills)

    if healed > 0:
        console.print(f"  [bold green]✓ Successfully healed {healed} manifest(s).[/bold green]")
        console.print("  [dim]Note: You should now run a database re-index (Option 3) to sync these changes.[/dim]")

    if verified > 0:
        console.print(
            f"  [bold cyan]ℹ {verified} handler(s) verified as legitimately taking no parameters.[/bold cyan]")

    if not_found > 0:
        console.print(
            f"  [bold yellow]⚠️ {not_found} handler(s) could not be located in their respective Python files.[/bold yellow]")

    if healed == 0 and verified == 0 and not_found == 0:
        console.print("\n[dim]No manifests were updated (signatures might be unparseable).[/dim]")

    Prompt.ask("\nPress Enter to return")