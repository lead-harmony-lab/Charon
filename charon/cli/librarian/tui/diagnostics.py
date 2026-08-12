"""
charon/cli/librarian/tui/diagnostics.py
System Version: v0.2.0 | File Revision: 1.8.0

Module: Diagnostic health audits, dependency resolutions, state drift checks,
registry maintenance interface, and quarantine management.
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from charon.cli.librarian.database import get_connection, STATE_DB_PATH, run_audit, run_sync
from charon.cli.librarian.ingestion import flag_quarantined_orphans
from charon.cli.librarian.purge_gaps import purge_resolved_gaps
from charon.cli.librarian.tui.discovery import (
    discover_skills,
    get_resolved_gaps_count,
    get_quarantined_orphans_count
)
from charon.core.skills import SkillLibrarian

console = Console()

PACKAGE_MAP = {
    "tesseract": "tesseract-ocr",
    "kicad-cli": "kicad",
    "node": "nodejs",
    "python": "python3",
    "ffmpeg": "ffmpeg",
    "pdftoppm": "poppler-utils",
}


def run_diagnostics_suite(librarian: SkillLibrarian) -> None:
    """Main interactive entry point for Option [3]: Diagnostics & Maintenance."""
    while True:
        # Re-check and flag orphaned skills in DB prior to discovery
        flag_quarantined_orphans()

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

        purge_status = (
            f"[bold yellow]({resolved_gaps} pending purge)[/bold yellow]"
            if resolved_gaps > 0
            else "[dim](Clean)[/dim]"
        )
        console.print(f"  [4] 📋 Audit SQLite State Drift & Vacuum DB {purge_status}")

        if quarantine_count > 0:
            console.print(f"  [5] [bold yellow]⚠️  Review & Manage Quarantined Skills ({quarantine_count} Action Required)[/bold yellow]")
        else:
            console.print("  [5] 🔬 Review & Manage Quarantined Skills")

        console.print("  [B] Back to Main Menu")
        console.print("  [Q] Exit Librarian TUI\n")

        choices = ["1", "2", "3", "4", "5", "b", "B", "q", "Q"]
        choice = Prompt.ask("Select operation", choices=choices, default="1")

        if choice.lower() == "q":
            console.print("[bold cyan]Librarian session closed.[/bold cyan]")
            sys.exit(0)
        elif choice.lower() == "b":
            break
        elif choice == "1":
            audit_report(skills)
        elif choice == "2":
            if broken_skills:
                resolve_all_dependencies(broken_skills)
            else:
                console.print("\n[bold green]✓ All registered skills have healthy dependencies![/bold green]")
                Prompt.ask("Press Enter to continue")
        elif choice == "3":
            console.print("\n[bold cyan]Syncing SQLite database with filesystem manifests...[/bold cyan]")
            flag_quarantined_orphans()
            run_sync()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()
            console.print("[bold green]✓ Re-index and synchronization complete.[/bold green]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == "4":
            console.clear()
            console.print("[bold cyan]📋 SQLite vs Filesystem State Drift Audit[/bold cyan]\n")
            flag_quarantined_orphans()
            run_audit()

            if resolved_gaps > 0:
                console.print(
                    f"\n[bold yellow]⚠️ State Drift Detected: {resolved_gaps} resolved gap(s) pending purge.[/bold yellow]"
                )
                confirm = Prompt.ask("Purge resolved gaps and vacuum database?", choices=["y", "n"], default="y")
                if confirm.lower() == "y":
                    purged = purge_resolved_gaps()
                    console.print(f"[bold green]✓ Purged {purged} record(s).[/bold green]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == "5":
            review_quarantined_skills()


def audit_report(skills: List[Dict]) -> None:
    """Displays a detailed diagnostic health matrix across all skills."""
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
            status = "[bold red]CRITICAL[/bold red]"
            packages = [PACKAGE_MAP.get(m, m) for m in missing]
            table.add_row(
                s.get("skill_id", "N/A"),
                s.get("stage", "Unknown"),
                status,
                ", ".join(missing),
                ", ".join(packages),
            )
        else:
            table.add_row(
                s.get("skill_id", "N/A"),
                s.get("stage", "Unknown"),
                "[bold green]HEALTHY[/bold green]",
                "[dim]None[/dim]",
                "[dim]N/A[/dim]",
            )

    console.print(table)
    Prompt.ask("\nPress Enter to return to Diagnostics Menu")


def resolve_all_dependencies(broken_skills: List[Dict]) -> None:
    """Collects missing requirements, applies package mapping, and triggers apt-get."""
    console.clear()

    missing_binaries = set()
    for s in broken_skills:
        missing_binaries.update(s.get("missing_requirements", []))

    apt_packages = [PACKAGE_MAP.get(b, b) for b in missing_binaries]
    pkg_str = " ".join(apt_packages)

    cmd = f"sudo apt-get update && sudo apt-get install -y {pkg_str}"

    console.print("[bold red]⚠️  DEPENDENCY RESOLUTION TARGETS DETECTED[/bold red]\n")
    console.print(f"  [bold]Missing Binaries ($PATH):[/bold] {', '.join(missing_binaries)}")
    console.print(f"  [bold]Target APT Packages:[/bold]      [cyan]{pkg_str}[/cyan]")
    console.print(f"  [bold]Execution Command:[/bold]        [dim]{cmd}[/dim]\n")

    confirm = Prompt.ask("Execute package installation with elevated privileges?", choices=["y", "n"], default="y")

    if confirm.lower() == "y":
        subprocess.run(cmd, shell=True)
        Prompt.ask("\nPress Enter to return and refresh diagnostic health state")


def review_quarantined_skills() -> None:
    """Interactive prompt to review, recheck, or delete quarantined skills."""
    if not STATE_DB_PATH.exists():
        console.print("[bold red]Database not found.[/bold red]")
        Prompt.ask("\nPress Enter to return")
        return

    with get_connection(STATE_DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT skill_id, entry_file_path, quarantine_reason 
            FROM skill_registry 
            WHERE status = 'QUARANTINED'
            """
        )
        orphans = cursor.fetchall()

        if not orphans:
            console.print("\n[bold green]✅ No quarantined skills found. Everything is clean.[/bold green]")
            Prompt.ask("\nPress Enter to return")
            return

        console.clear()
        console.print(f"[bold yellow]⚠️  Found {len(orphans)} Quarantined Skill(s):[/bold yellow]\n")

        for skill_id, path_str, reason in orphans:
            console.print("-" * 60)
            console.print(f"[bold]Skill ID :[/bold] {skill_id}")
            console.print(f"[bold]Path     :[/bold] {path_str}")
            console.print(f"[bold]Reason   :[/bold] [red]{reason}[/red]")
            console.print("-" * 60)

            choice = Prompt.ask(
                f"Action for '{skill_id}' ([bold cyan]R[/bold cyan]echeck, [bold red]D[/bold red]elete, [dim]S[/dim]kip, [dim]B[/dim]ack, [dim]Q[/dim]uit)",
                choices=["r", "d", "s", "b", "q"],
                default="s",
                show_choices=False,
                show_default=True
            ).lower()

            if choice == 'q':
                console.print("[bold cyan]Librarian session closed.[/bold cyan]")
                sys.exit(0)

            elif choice == 'b':
                console.print("[dim]Aborting review. Returning to Diagnostics Menu...[/dim]\n")
                return  # Breaks out of the function entirely

            elif choice == 's':
                console.print(f"[dim]Skipping {skill_id}...[/dim]\n")

            elif choice == 'd':
                cursor.execute("DELETE FROM skill_registry WHERE skill_id = ?", (skill_id,))
                conn.commit()
                console.print(f"[bold green]🗑️  Deleted '{skill_id}' from registry.[/bold green]\n")

            elif choice == 'r':
                entry_path = Path(path_str) if path_str else None
                if entry_path and entry_path.exists():
                    cursor.execute(
                        """
                        UPDATE skill_registry 
                        SET status = 'ACTIVE', 
                            quarantine_reason = NULL,
                            updated_at = CURRENT_TIMESTAMP 
                        WHERE skill_id = ?
                        """,
                        (skill_id,)
                    )
                    conn.commit()
                    console.print(f"[bold green]✅ Repaired! '{skill_id}' is now ACTIVE.[/bold green]\n")
                else:
                    console.print(
                        f"[bold red]❌ Failed: Files for '{skill_id}' are still missing or invalid.[/bold red]\n")

        Prompt.ask("\nPress Enter to return to Diagnostics Menu")