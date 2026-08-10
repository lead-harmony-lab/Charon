"""
charon/cli/librarian/tui/app.py
System Version: v0.1.0 | File Revision: 1.4.0

Module: LibrarianTUI application orchestrator and main menu navigation loop.
"""

from pathlib import Path
import sys
from typing import List

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax

from charon.cli.librarian.forge import main as run_forge
from charon.cli.librarian.ingestion import SKILLS_TEMPLATES_DIR, run_create, run_ingest
from charon.cli.librarian.tui.diagnostics import run_diagnostics_suite
from charon.cli.librarian.tui.discovery import discover_skills, get_active_db_agent_ids
from charon.cli.librarian.tui.views import render_header, view_catalog
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
                return [
                    a.agent_id if hasattr(a, "agent_id") else str(a) for a in agents
                ]
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

    def _show_ingestion_docs(self):
        """Interactive multi-page documentation viewer for skill ingestion specs."""
        page = "1"
        while True:
            console.clear()
            console.print(
                Panel(
                    "[bold yellow]📖 SKILL INGESTION DOCUMENTATION & TEMPLATE SPECS[/bold yellow]\n"
                    "[dim]Navigate pages to review package structure and template files[/dim]",
                    border_style="yellow",
                )
            )

            if page == "1":
                doc_markdown = (
                    "### 🏛️ Ingestion Architecture & Workflow\n\n"
                    "All Charon skills must be formatted into staged package folders prior to dynamic promotion:\n\n"
                    "    skills/staged/<skill_id>/\n"
                    "    ├── manifest.json    (Schema metadata: ID, actions, requirements)\n"
                    "    └── plugin.py        (Python entrypoint module handling action callbacks)\n\n"
                    "#### 💡 Ingestion Rules & Automated Normalization\n"
                    "* **Standalone `.py` File**: Copied as `plugin.py` into `skills/staged/<skill_id>/`; boilerplate `manifest.json` generated from template.\n"
                    "* **Directory without Manifest**: Copied to staged area, entrypoint normalized to `plugin.py`, and `manifest.json` generated from template.\n"
                    "* **Full Package Directory**: Validated against `SkillManifest` Pydantic schema and indexed into SQLite.\n\n"
                    "*Documentation Reference:* `https://docs.charon.internal/skills/ingestion`"
                )
                console.print(
                    Panel(
                        Markdown(doc_markdown),
                        title="[bold cyan]Page 1: Overview & Guidelines[/bold cyan]",
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
        """Interactive workflow for scaffolding, ingesting files, and reading specs."""
        while True:
            console.clear()
            console.print(
                Panel(
                    "[bold cyan]📥 SKILL INGESTION & SCAFFOLDING WIZARD[/bold cyan]\n"
                    "[dim]Scaffold new templates or import external code into staged storage[/dim]",
                    border_style="cyan",
                )
            )
            console.print("  [1] 🛠️  Scaffold New Skill Template")
            console.print("  [2] 📂 Ingest External File or Directory")
            console.print("  [H] 📖 Ingestion Specs & Help Docs (Multi-Page Viewer)")
            console.print("  [B] Back to Main Menu")
            console.print("  [Q] Exit Librarian TUI\n")

            choice = Prompt.ask("Select option", choices=["1", "2", "h", "H", "b", "B", "q", "Q"], default="1")

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
                run_create(skill_id=sid, category=category)
                Prompt.ask("\nPress Enter to return")

            elif choice == "2":
                console.print(
                    "\n[dim]Provide path to a standalone .py file or folder (e.g., ~/my_script.py or ./my_skill_pkg/)[/dim]"
                )
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

                inferred_id = source_path.stem.lower().replace("-", "_").replace(" ", "_")
                sid_input = Prompt.ask("Custom skill_id", default=inferred_id).strip()

                if sid_input.lower() == "b":
                    continue
                if sid_input.lower() == "q":
                    console.print("[bold cyan]Librarian session closed.[/bold cyan]")
                    sys.exit(0)

                run_ingest(source_path=source_path, skill_id=sid_input)
                Prompt.ask("\nPress Enter to return")

    def start(self):
        while True:
            skills = discover_skills()
            self.agents = self._fetch_registered_agents()
            render_header(len(skills), len(self.agents))

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