"""
charon/cli/librarian/tui/app.py
System Version: v0.2.0 | File Revision: 2.4.0

Module: LibrarianTUI application orchestrator and main menu navigation loop.
Refactored to trigger startup orphan quarantine auto-sweeps prior to database sync,
integrating interactive quarantine selection prompts and detailed outcome summaries.
"""

from pathlib import Path
import sys
from typing import Any, Dict, List

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax

from charon.cli.database import run_sync
from charon.cli.librarian.forge import main as run_forge
from charon.cli.librarian.ingestion import (
    SKILLS_QUARANTINE_DIR,
    SKILLS_TEMPLATES_DIR,
    flag_quarantined_orphans,
    run_create,
    run_ingest,
)
from charon.cli.librarian.tui.components import render_header
from charon.cli.librarian.tui.diagnostics import run_diagnostics_suite
from charon.cli.librarian.tui.discovery import (
    discover_skills,
    get_active_db_agent_ids,
    get_quarantined_orphans_count,
    get_open_gaps_count,      # <-- Added import
    get_resolved_gaps_count   # <-- Added import
)
from charon.cli.librarian.tui.prompts import prompt_quarantine_selection
from charon.cli.librarian.tui.views import view_catalog
from charon.core.skills import SkillLibrarian

console = Console()


class LibrarianTUI:
    def __init__(self):
        self.librarian = SkillLibrarian.get_instance()
        self.agents = self._fetch_registered_agents()

    def _fetch_registered_agents(self) -> List[str]:
        """Dynamically pulls active agent IDs from AgentRepository or SQLite fallback."""
        try:
            if hasattr(self.librarian, "agent_repo") and self.librarian.agent_repo:
                agents = self.librarian.agent_repo.get_all_agents()
                active_agents = [
                    a.agent_id if hasattr(a, "agent_id") else str(a)
                    for a in agents
                    if getattr(a, "is_active", True)
                ]
                if active_agents:
                    return sorted(active_agents)
        except Exception:
            pass

        return sorted(list(get_active_db_agent_ids()))

    def run_diagnostics_suite(self):
        """Delegates to the interactive diagnostics and dependency resolution engine."""
        run_diagnostics_suite(self.librarian)

    def _load_template_file(self, filename: str) -> str:
        """Dynamically loads template files directly from charon/skills/templates/."""
        template_path = SKILLS_TEMPLATES_DIR / filename
        if template_path.exists():
            try:
                return template_path.read_text(encoding="utf-8")
            except Exception as e:
                return f"// Error reading template '{filename}': {e}"

        return f"// Template file '{filename}' missing at {template_path}"

    def _render_ingestion_summary(self, result: Dict[str, Any]):
        """Renders a structured, high-visibility outcome panel after scaffolding or ingestion."""
        if not result or not result.get("success", True):
            console.print(
                Panel(
                    f"[bold red]❌ INGESTION FAILED OR CANCELLED[/bold red]\n\n"
                    f"[white]{result.get('error', 'Operation was aborted or invalid source provided.')}[/white]",
                    title="[bold red]Ingestion Report[/bold red]",
                    border_style="red",
                    expand=True,
                )
            )
            return

        skill_id = result.get("skill_id", "Unknown")
        source = result.get("source_path", "N/A")
        dest = result.get("staged_path", f"skills/staged/{skill_id}")
        manifest_status = "[bold green]✓ Created from Template[/bold green]" if result.get("manifest_created") else "[dim green]✓ Verified Existing[/dim green]"
        plugin_status = "[bold green]✓ Normalized / Created[/bold green]" if result.get("plugin_created") else "[dim green]✓ Verified Existing[/dim green]"

        summary_text = (
            f"[bold green]✅ SKILL INGESTED SUCCESSFULLY[/bold green]\n\n"
            f"• [bold white]Assigned Skill ID:[/bold white] [bold cyan]{skill_id}[/bold cyan]\n"
            f"• [bold white]Source Pathway:[/bold white] [dim]{source}[/dim]\n"
            f"• [bold white]Staged Target Path:[/bold white] [yellow]{dest}[/yellow]\n\n"
            f"[bold magenta]Package Structure Verification:[/bold magenta]\n"
            f"  ├── manifest.json: {manifest_status}\n"
            f"  └── plugin.py:     {plugin_status}\n\n"
            f"[dim italic]Tip: Browse Catalog [1] -> Inspector to edit manifest or promote to Dynamic Stage.[/dim italic]"
        )

        console.print(
            Panel(
                summary_text,
                title=f"[bold green]📥 Ingestion Summary Report — {skill_id}[/bold green]",
                border_style="green",
                padding=(0, 2),
                expand=True,
            )
        )

    def _show_ingestion_docs(self):
        """Interactive multi-page documentation viewer for skill ingestion specs."""
        page = "1"
        while True:
            console.clear()
            console.print(
                Panel(
                    "[bold yellow]📖 SKILL INGESTION DOCUMENTATION & TEMPLATE SPECS[/bold yellow]\n"
                    "[dim]Navigate pages to review package structure, quarantine pathway, and templates[/dim]",
                    border_style="yellow",
                )
            )

            if page == "1":
                doc_markdown = (
                    "### 🏛️ Ingestion Architecture & Quarantine Pathways\n\n"
                    "All Charon skills must be formatted into staged package folders prior to dynamic promotion:\n\n"
                    "    skills/staged/<skill_id>/\n"
                    "    ├── manifest.json    (Schema metadata: ID, actions, requirements)\n"
                    "    └── plugin.py        (Python entrypoint module handling action callbacks)\n\n"
                    "#### ☣️ Quarantine & Ingestion Rules\n"
                    f"* **Quarantine Directory**: Isolated files sitting in `{SKILLS_QUARANTINE_DIR}` are automatically evaluated during ingestion.\n"
                    "* **Interactive Resolution**: User is prompted to confirm or customize the `skill_id` slug upon import.\n"
                    "* **Standalone `.py` File**: Copied as `plugin.py` into `skills/staged/<skill_id>/`; boilerplate `manifest.json` generated from template.\n"
                    "* **Directory without Manifest**: Copied to staged area, entrypoint normalized to `plugin.py`, and `manifest.json` generated from template.\n"
                    "* **Staged Sanitization**: Pre-existing folders in `staged/` and demoted files in `quarantine/` are auto-slugified and synced during DB maintenance checks.\n\n"
                    "*Documentation Reference:* `https://docs.charon.internal/skills/ingestion`"
                )
                console.print(
                    Panel(
                        Markdown(doc_markdown),
                        title="[bold cyan]Page 1: Overview, Staging & Quarantine Pathways[/bold cyan]",
                        border_style="cyan",
                    )
                )

            elif page == "2":
                raw_manifest = self._load_template_file("manifest.json")
                syntax = Syntax(raw_manifest, "json", theme="monokai", line_numbers=True)
                console.print(
                    Panel(
                        syntax,
                        title="[bold cyan]Page 2: manifest.json Template Structure[/bold cyan]",
                        border_style="cyan",
                    )
                )
                console.print(
                    "[dim]Defines skill identity, required system binaries, and action metadata mappings.[/dim]\n"
                )

            elif page == "3":
                raw_plugin = self._load_template_file("plugin.py")
                syntax = Syntax(raw_plugin, "python", theme="monokai", line_numbers=True)
                console.print(
                    Panel(
                        syntax,
                        title="[bold cyan]Page 3: plugin.py Template Entrypoint[/bold cyan]",
                        border_style="cyan",
                    )
                )
                console.print("[dim]Implements execution logic for action routes defined in manifest.json.[/dim]\n")

            console.print("[bold]Page Selector:[/bold]")
            console.print("  [1] Overview & Guidelines")
            console.print("  [2] View manifest.json Template")
            console.print("  [3] View plugin.py Template")
            console.print("  [B] Back to Ingestion Wizard")
            console.print("  [Q] Exit Librarian TUI\n")

            choice = Prompt.ask("Select page or action", choices=["1", "2", "3", "b", "B", "q", "Q"], default=page)

            if choice.lower() == "q":
                console.print("[bold cyan]Librarian session closed.[/bold cyan]")
                sys.exit(0)
            elif choice.lower() == "b":
                break
            else:
                page = choice

    def run_ingestion_wizard(self):
        """Interactive workflow for scaffolding, ingesting files from local/quarantine paths, and reading specs."""
        while True:
            console.clear()
            console.print(
                Panel(
                    "[bold cyan]📥 SKILL INGESTION & SCAFFOLDING WIZARD[/bold cyan]\n"
                    "[dim]Scaffold new templates or import external/quarantined code into staged storage[/dim]",
                    border_style="cyan",
                )
            )
            console.print("  [1] 🛠️  Scaffold New Skill Template")
            console.print("  [2] ☣️  Select from Quarantine Storage Pathway")
            console.print("  [3] 📂 Ingest from Custom File or Directory Path")
            console.print("  [H] 📖 Ingestion Specs & Help Docs (Multi-Page Viewer)")
            console.print("  [B] Back to Main Menu")
            console.print("  [Q] Exit Librarian TUI\n")

            choice = Prompt.ask("Select option", choices=["1", "2", "3", "h", "H", "b", "B", "q", "Q"], default="1")

            if choice.lower() == "q":
                console.print("[bold cyan]Librarian session closed.[/bold cyan]")
                sys.exit(0)
            elif choice.lower() == "b":
                break
            elif choice.lower() == "h":
                self._show_ingestion_docs()

            elif choice == "1":
                console.print("\n[dim]Target location: skills/staged/<skill_id>/[/dim]")
                sid = Prompt.ask("Enter new skill_id (or 'b' to cancel)").strip()

                if not sid or sid.lower() == "b":
                    continue
                if sid.lower() == "q":
                    console.print("[bold cyan]Librarian session closed.[/bold cyan]")
                    sys.exit(0)

                category = Prompt.ask("Category", default="General").strip()
                res = run_create(skill_id=sid, category=category)

                if isinstance(res, dict):
                    self._render_ingestion_summary(res)
                else:
                    self._render_ingestion_summary({
                        "success": True,
                        "skill_id": sid,
                        "source_path": "Built-in Scaffold Template",
                        "staged_path": f"skills/staged/{sid}",
                        "manifest_created": True,
                        "plugin_created": True,
                    })
                Prompt.ask("\nPress Enter to return")

            elif choice == "2":
                selected_path = prompt_quarantine_selection()
                if selected_path:
                    res = run_ingest(source_path=selected_path)

                    if isinstance(res, dict):
                        self._render_ingestion_summary(res)
                    else:
                        staged_target = Path("skills/staged") / selected_path.stem
                        self._render_ingestion_summary({
                            "success": True,
                            "skill_id": selected_path.stem,
                            "source_path": str(selected_path),
                            "staged_path": str(staged_target),
                            "manifest_created": (staged_target / "manifest.json").exists(),
                            "plugin_created": (staged_target / "plugin.py").exists(),
                        })
                    Prompt.ask("\nPress Enter to return")

            elif choice == "3":
                path_input = Prompt.ask("Enter source path (or 'b' to cancel)").strip()

                if not path_input or path_input.lower() == "b":
                    continue
                if path_input.lower() == "q":
                    console.print("[bold cyan]Librarian session closed.[/bold cyan]")
                    sys.exit(0)

                source_path = Path(path_input).expanduser().resolve()
                if not source_path.exists():
                    console.print(f"\n[bold red]❌ Error:[/bold red] Source path '{source_path}' does not exist.")
                    Prompt.ask("Press Enter to try again")
                    continue

                res = run_ingest(source_path=source_path)

                if isinstance(res, dict):
                    self._render_ingestion_summary(res)
                else:
                    staged_target = Path("skills/staged") / source_path.stem
                    self._render_ingestion_summary({
                        "success": True,
                        "skill_id": source_path.stem,
                        "source_path": str(source_path),
                        "staged_path": str(staged_target),
                        "manifest_created": (staged_target / "manifest.json").exists(),
                        "plugin_created": (staged_target / "plugin.py").exists(),
                    })
                Prompt.ask("\nPress Enter to return")

    def start(self):
        # 1. Sweep disk/DB for quarantined orphans on boot
        flag_quarantined_orphans()

        # 2. Synchronize DB and staged/quarantine folders
        run_sync()

        while True:
            skills = discover_skills()
            self.agents = self._fetch_registered_agents()

            # Calculate metrics for the header natively in the main loop
            broken_deps_count = sum(1 for s in skills if s.get("missing_requirements"))
            quarantined_count = get_quarantined_orphans_count()
            open_gaps = get_open_gaps_count()             # <-- Added fetching
            resolved_gaps = get_resolved_gaps_count()     # <-- Added fetching

            # Wire the metrics into the main menu render
            render_header(
                skill_count=len(skills),
                agent_count=len(self.agents),
                broken_deps_count=broken_deps_count,
                orphan_count=quarantined_count,
                open_gaps=open_gaps,                      # <-- Passed to component
                resolved_gaps=resolved_gaps               # <-- Passed to component
            )

            console.print("\n[bold white]Main Menu:[/bold white]")
            console.print("  [1] 📚 Browse Skill Catalog (Interactive Views)")
            console.print("  [2] 👤 Manage Agent Permission Matrix")
            console.print("  [3] 🛠️  Run Diagnostics & Manifest Maintenance Suite")
            console.print("  [4] ⚡ Inspect Open Skill Gaps (Forge Shortcut)")
            console.print("  [5] 📥 Ingest or Scaffold Skill Package")
            console.print("  [Q] Exit Librarian TUI\n")

            choice = Prompt.ask("Select option", choices=["1", "2", "3", "4", "5", "q", "Q"], default="1")

            if choice == "1":
                view_catalog(self.agents, self.librarian)
            elif choice == "2":
                view_catalog(self.agents, self.librarian, initial_filter="agent")
            elif choice == "3":
                self.run_diagnostics_suite()
            elif choice == "4":
                try:
                    run_forge(["list"])
                except Exception as e:
                    console.print(f"[bold red]Could not trigger Forge CLI:[/bold red] {e}")
                Prompt.ask("\nPress Enter to return to Librarian")
            elif choice == "5":
                self.run_ingestion_wizard()
            elif choice.lower() == "q":
                console.print("[bold cyan]Librarian session closed.[/bold cyan]")
                break

if __name__ == "__main__":
    try:
        app = LibrarianTUI()
        app.start()
    except KeyboardInterrupt:
        console.print("\n[bold cyan]Librarian session forcefully closed.[/bold cyan]")
        sys.exit(0)