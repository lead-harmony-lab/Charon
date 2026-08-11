"""
charon/cli/librarian/tui/prompts.py
System Version: v0.2.0 | File Revision: 1.0.0

Module: Interactive TUI selection helpers and prompt utilities.
"""

from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Prompt

from charon.cli.librarian.ingestion import SKILLS_QUARANTINE_DIR

console = Console()


def prompt_quarantine_selection() -> Optional[Path]:
    """
    Interactive TUI Helper: Scans quarantine directory and presents a selection prompt.
    Returns chosen Path object or None if cancelled or empty.
    """
    if not SKILLS_QUARANTINE_DIR.exists():
        console.print("\n[dim yellow]⚠️ Quarantine directory does not exist.[/dim yellow]")
        return None

    quarantine_items = sorted([
        p for p in SKILLS_QUARANTINE_DIR.iterdir()
        if not p.name.startswith(".") and p.name != ".gitkeep"
    ], key=lambda x: (not x.is_dir(), x.name))

    if not quarantine_items:
        console.print("\n[dim yellow]⚠️ No items currently found in quarantine directory.[/dim yellow]")
        Prompt.ask("Press Enter to return")
        return None

    console.print("\n[bold cyan]📂 Quarantined Items Found:[/bold cyan]")
    for idx, item in enumerate(quarantine_items, start=1):
        item_type = "Directory Package" if item.is_dir() else "Standalone Script"
        console.print(f"  [{idx}] {item.name} [dim]({item_type})[/dim]")
    console.print("  [B] Cancel / Back\n")

    choices = [str(i) for i in range(1, len(quarantine_items) + 1)] + ["b", "B"]
    sel = Prompt.ask("Select item to ingest", choices=choices, default="B")

    if sel.lower() == "b":
        return None

    return quarantine_items[int(sel) - 1]