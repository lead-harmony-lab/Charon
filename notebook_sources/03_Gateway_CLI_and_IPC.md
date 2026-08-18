# Subsystem Domain Context: 03_Gateway_CLI_and_IPC
> **Generated:** 2026-08-11 06:46 UTC  
> **Charon Core Version:** v8.0  
> **Git Branch:** `Streamline-Dynamic-Routing` | **Commit:** `c416670`

---

## Target File: `charon/__version__.py`

```python
"""
charon/__version.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Single Source of Truth for Charon Version.
"""

__version__ = "0.1.0"

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/__init__.py`

```python
"""
charon/cli/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Charon CLI Subpackage - The Continental Interactive Interface.
"""

from charon.cli.main import main

__all__ = ["main"]

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/__main__.py`

```python
"""
charon/cli/__main__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Direct package invocation entrypoint (`python3 -m charon.cli`).
"""

from charon.cli.main import main

if __name__ == "__main__":
    main()

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/client.py`

```python
"""
charon/cli/client.py
System Version: v0.1.0 | File Revision: 1.2.1

Module: Daemon integration client managing HTTP REST and WebSocket streaming.
"""

import json
import sys
import uuid
from typing import Optional, Set, Tuple

import httpx
import websockets
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.panel import Panel

from charon.cli.ui import CharonSpinner, console, render_response


class CharonClient:
    """Async Client managing REST calls and WebSocket streams with charond."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        ws_base = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.ws_url = f"{ws_base}/v1/ws"
        self.api_key = api_key
        self.client_id = f"cli_{uuid.uuid4().hex[:8]}"
        self.spinner = CharonSpinner()
        self._rendered_proposals: Set[str] = set()

    @property
    def headers(self) -> dict:
        return {"X-API-Key": self.api_key}

    async def ping_daemon(self) -> bool:
        """Checks if the Charon REST endpoint is healthy."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/v1/health")
                return res.status_code == 200
        except Exception:
            return False

    async def submit_and_stream(
        self,
        prompt: str,
        session: PromptSession,
        agent_override: Optional[str] = None,
        non_interactive: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """Establishes WebSocket stream, submits task, and listens for events."""
        self.spinner.start("Tending to the arrangements...")
        self._rendered_proposals.clear()
        success = True
        staged_prompt: Optional[str] = None
        streamed_any_chunk = False

        ws_uri = f"{self.ws_url}?client_id={self.client_id}&api_key={self.api_key}"

        try:
            async with websockets.connect(
                ws_uri,
                additional_headers={"x-api-key": self.api_key},
                ping_interval=10,
                ping_timeout=10,
            ) as ws:
                # 1. Post Task via REST API
                async with httpx.AsyncClient(headers=self.headers, timeout=30.0) as http_client:
                    payload = {
                        "prompt": prompt,
                        "client_id": self.client_id,
                        "agent_override": agent_override,
                    }
                    resp = await http_client.post(f"{self.base_url}/v1/task", json=payload)
                    if resp.status_code != 200:
                        self.spinner.stop()
                        console.print(
                            f"\n[bold red][System Error]: Task submission failed ({resp.status_code}: {resp.text})[/bold red]"
                        )
                        return False, None

                    task_id = resp.json().get("task_id")

                # 2. Consume WebSocket Event Stream
                while True:
                    raw_msg = await ws.recv()
                    event = json.loads(raw_msg)

                    event_type = event.get("event_type") or event.get("type")
                    event_task_id = event.get("task_id")
                    data = event.get("data", {}) if "data" in event else event

                    if (
                        event_task_id
                        and task_id
                        and event_task_id != task_id
                        and event_type not in ["system_alert", "overseer_report"]
                    ):
                        continue

                    # Dynamic Task Heartbeat / Dynamic Sub-step updates
                    if event_type in [
                        "task_heartbeat",
                        "task_progress",
                        "agent_status",
                        "agent_action",
                        "status",
                        "telemetry",
                        "step",
                    ]:
                        step_msg = (
                            data.get("step")
                            or data.get("status_message")
                            or data.get("message")
                            or data.get("status")
                            or data.get("action")
                        )
                        agent = data.get("active_agent") or data.get("agent")
                        elapsed = data.get("elapsed_seconds")

                        if step_msg:
                            display_text = f"[{agent}] {step_msg}" if agent else str(step_msg)
                            self.spinner.update(display_text)
                        elif elapsed is not None:
                            agent_label = agent or "Orchestrator"
                            self.spinner.update(
                                f"[{agent_label}] Tending to the arrangements... ({elapsed}s)"
                            )

                    # Stream Chunks / Agent Logs
                    elif event_type in ["agent_log", "task_stream", "content_chunk"]:
                        # If the log carries an explicit step label, update spinner instead of raw streaming
                        if data.get("is_step") or data.get("step"):
                            step_text = data.get("step") or data.get("message", "")
                            agent = data.get("active_agent") or data.get("agent")
                            if step_text:
                                display_text = f"[{agent}] {step_text}" if agent else str(step_text)
                                self.spinner.update(display_text)
                        else:
                            chunk = data.get("message") or data.get("content", "")
                            if chunk:
                                # Only set streamed_any_chunk for actual response streaming events
                                if event_type in ["content_chunk", "task_stream"]:
                                    streamed_any_chunk = True
                                if self.spinner.running:
                                    self.spinner.stop()
                                sys.stdout.write(chunk)
                                sys.stdout.flush()

                    # Gatekeeper Intercepts
                    elif event_type == "gatekeeper_intercept":
                        self.spinner.stop()
                        manifest = data.get("manifest", "")
                        action = data.get("action", "Destructive action requested")
                        approval_id = data.get("approval_id")

                        if manifest:
                            console.print(manifest)
                        else:
                            console.print("\n[bold yellow]🛡️ GATEKEEPER INTERCEPT:[/bold yellow]")
                            panel_msg = (
                                f"Management requires physical authorization before executing:\n"
                                f"[bold red]{action}[/bold red]\n\n"
                                f"Please reply with '[bold green]proceed[/bold green]' to authorize, or '[bold red]cancel[/bold red]' to abort."
                            )
                            console.print(
                                Panel(
                                    panel_msg,
                                    border_style="yellow",
                                    title="Authorization Required",
                                )
                            )

                        decision = await session.prompt_async(
                            HTML("<ansiyellow><b>Authorization [proceed/cancel] > </b></ansiyellow>")
                        )
                        decision_str = decision.strip().lower()

                        async with httpx.AsyncClient(
                            headers=self.headers, timeout=10.0
                        ) as http_client:
                            await http_client.post(
                                f"{self.base_url}/v1/gatekeeper/respond",
                                json={
                                    "approval_id": approval_id,
                                    "decision": decision_str,
                                    "client_id": self.client_id,
                                },
                            )
                        self.spinner.start("Resuming task execution...")

                    # Concierge Proposals
                    elif event_type in ["concierge_suggestion", "concierge_proposal", "proposal"]:
                        if self.spinner.running:
                            self.spinner.stop()

                        phrase = (
                            data.get("phrase")
                            or data.get("recommendation")
                            or data.get("next_step")
                        )
                        proposed_cmd = (
                            data.get("suggested_prompt")
                            or data.get("proposed_command")
                            or data.get("next_step")
                        )
                        proposal_key = f"{phrase}:{proposed_cmd}"

                        if phrase and proposal_key not in self._rendered_proposals:
                            self._rendered_proposals.add(proposal_key)
                            staged_prompt = proposed_cmd

                            panel_body = (
                                f"[bold italic cyan]\"{phrase}\"[/bold italic cyan]\n\n"
                                f"[dim]Use [bold white]↑/↓[/bold white] arrows to select, press [bold white]Enter[/bold white] to confirm:[/dim]"
                            )
                            console.print()
                            console.print(
                                Panel(
                                    panel_body,
                                    title="[bold blue]🛎️ Concierge Proposal[/bold blue]",
                                    border_style="blue",
                                    expand=False,
                                )
                            )

                    # System Alerts
                    elif event_type == "system_alert":
                        severity = data.get("severity", "INFO")
                        title = data.get("title", "System Alert")
                        msg = data.get("message", "")
                        style = "bold red" if severity == "CRITICAL" else "bold yellow"
                        console.print(
                            Panel(
                                msg,
                                title=f"[{style}]{title}[/{style}]",
                                border_style="red" if severity == "CRITICAL" else "yellow",
                            )
                        )

                    # Task Completion
                    elif event_type == "task_complete":
                        self.spinner.stop()
                        summary = (
                            data.get("summary")
                            or data.get("result")
                            or data.get("output")
                            or data.get("content", "")
                        )

                        if summary and not streamed_any_chunk:
                            console.print("\n[bold cyan]🛎️ CHARON:[/bold cyan] ", end="")
                            render_response(summary)
                        else:
                            console.print()
                        break

                    # Task Errors
                    elif event_type in ["task_error", "error"]:
                        self.spinner.stop()
                        error_msg = data.get("error") or data.get("message", "An unknown error occurred.")
                        console.print(f"\n[bold red][System Error]: {error_msg}[/bold red]")
                        success = False
                        break

        except httpx.RequestError as e:
            self.spinner.stop()
            console.print(
                f"\n[bold red]Connection Error:[/bold red] Unable to reach daemon at {self.base_url} ({e})"
            )
            return False, None
        except websockets.exceptions.ConnectionClosed:
            self.spinner.stop()
            console.print("\n[dim][System]: Event stream disconnected.[/dim]")
        except Exception as e:
            self.spinner.stop()
            console.print(f"\n[bold red][System Error]: Stream error ({e})[/bold red]")
            success = False

        return success, staged_prompt
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/interactive.py`

```python
"""
charon/cli/interactive.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Interactive terminal UI widgets and choice prompts for Charon CLI.
"""

from typing import Optional
from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style

from charon.cli.ui import console


async def prompt_concierge_choice(
    proposed_cmd: str, session: Optional[PromptSession] = None
) -> Optional[str]:
    """Presents an interactive selection menu for Concierge proposals with custom entry support."""
    options = [
        ("accept", f"Accept: {proposed_cmd}"),
        ("custom", "Other... (Enter custom prompt)"),
        ("dismiss", "Dismiss proposal"),
        ("exit", "That will be all (Exit)"),
    ]
    selected_index = 0

    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        nonlocal selected_index
        selected_index = (selected_index - 1) % len(options)

    @kb.add("down")
    def _(event):
        nonlocal selected_index
        selected_index = (selected_index + 1) % len(options)

    @kb.add("1")
    def _(event):
        event.app.exit(result=options[0][0])

    @kb.add("2")
    def _(event):
        event.app.exit(result=options[1][0])

    @kb.add("3")
    def _(event):
        event.app.exit(result=options[2][0])

    @kb.add("4")
    def _(event):
        event.app.exit(result=options[3][0])

    @kb.add("enter")
    def _(event):
        event.app.exit(result=options[selected_index][0])

    @kb.add("c-c")
    @kb.add("escape")
    def _(event):
        event.app.exit(result="dismiss")

    def get_formatted_text():
        tokens = []
        for i, (action_type, text) in enumerate(options):
            if i == selected_index:
                tokens.append(("class:selected", f" ❯ [{i+1}] {text}\n"))
            else:
                tokens.append(("class:unselected", f"   [{i+1}] {text}\n"))
        return tokens

    style = Style.from_dict({
        "selected": "fg:ansigreen bold",
        "unselected": "fg:ansigray dim",
    })

    layout = Layout(HSplit([Window(content=FormattedTextControl(get_formatted_text))]))

    app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=False,
    )

    choice = await app.run_async()

    if choice == "accept":
        return proposed_cmd
    elif choice == "custom":
        if session:
            custom_input = await session.prompt_async(
                HTML("<ansigreen><b>Custom Prompt > </b></ansigreen>")
            )
        else:
            custom_input = input("Custom Prompt > ")
        return custom_input.strip() if custom_input else None
    elif choice == "dismiss":
        return None
    elif choice == "exit":
        return "That will be all"

    return None

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/__init__.py`

```python
"""
charon/cli/librarian/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Package entrypoint for Charon Skill Librarian toolset.
Provides backwards-compatible imports for CLI entrypoints and core handlers.
"""

from charon.cli.librarian.cli import main
from charon.cli.database import run_audit, run_sync
from charon.cli.librarian.ingestion import run_create, run_edit, run_ingest
from charon.cli.librarian.lifecycle import (
    run_delete_skill,
    run_demote,
    run_promote,
    run_rename,
)
from charon.cli.librarian.manifest import run_check, validate_manifest_file
from charon.cli.librarian.permissions import run_list, run_permission_change

__all__ = [
    "main",
    "run_check",
    "validate_manifest_file",
    "run_sync",
    "run_audit",
    "run_permission_change",
    "run_list",
    "run_promote",
    "run_demote",
    "run_rename",
    "run_delete_skill",
    "run_create",
    "run_ingest",
    "run_edit",
]
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/cli.py`

```python
"""
charon/cli/librarian/cli.py
System Version: v0.2.0 | File Revision: 2.0.0

Module: CLI subcommands dispatcher and TUI session launcher for Charon Librarian.
Aligned with Schema V3.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from charon.cli.database import run_audit, run_sync
from charon.cli.librarian.ingestion import run_create, run_edit, run_ingest
from charon.cli.librarian.lifecycle import (
    run_delete_skill,
    run_demote,
    run_promote,
    run_rename,
)
from charon.cli.librarian.manifest import run_check
from charon.cli.librarian.permissions import (
    run_list,
    run_permission_change,
    set_default_action,
)
from charon.cli.librarian.purge_gaps import purge_resolved_gaps


def main(args: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="charon librarian",
        description="Unified skill management interface for Charon Librarian.",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # Inventory & Diagnostics
    subparsers.add_parser("list", help="List all discovered skills and authorization tags.")
    check_p = subparsers.add_parser("check", help="Validate manifest schema integrity.")
    check_p.add_argument("paths", nargs="*", type=Path, help="Target manifest/skill paths.")
    check_p.add_argument("--fix", action="store_true", help="Auto-fix legacy structures.")
    subparsers.add_parser("sync", help="Re-index filesystem manifests into SQLite registry.")
    subparsers.add_parser("audit", help="Audit database registry vs filesystem state drift.")

    # RBAC & Action Management
    grant_p = subparsers.add_parser("grant", help="Grant agent skill authorization.")
    grant_p.add_argument("skill_id", type=str)
    grant_p.add_argument("agent", type=str)

    revoke_p = subparsers.add_parser("revoke", help="Revoke agent skill authorization.")
    revoke_p.add_argument("skill_id", type=str)
    revoke_p.add_argument("agent", type=str)

    default_action_p = subparsers.add_parser(
        "set-default-action", help="Set default execution action for an agent."
    )
    default_action_p.add_argument("agent_id", type=str, help="Target agent ID")
    default_action_p.add_argument("action_name", type=str, help="Default action name")

    # Maintenance
    subparsers.add_parser("purge-gaps", help="Purge resolved skill gaps and vacuum DB.")

    # Ingestion & Editing
    create_p = subparsers.add_parser("create", help="Scaffold a new skill package.")
    create_p.add_argument("skill_id", type=str)
    create_p.add_argument("--category", type=str, default="General")
    create_p.add_argument("--agent", type=str, default=None, help="Target agent_id to equip this skill.")

    ingest_p = subparsers.add_parser("ingest", help="Ingest a script file or directory.")
    ingest_p.add_argument("path", type=Path)
    ingest_p.add_argument("--skill-id", type=str, default=None)
    ingest_p.add_argument("--agent", type=str, default=None, help="Target agent_id to equip this skill.")

    edit_p = subparsers.add_parser("edit", help="Open a skill manifest in $EDITOR.")
    edit_p.add_argument("skill_id", type=str)

    # Lifecycle Operations
    promote_p = subparsers.add_parser("promote", help="Promote staged skill to dynamic.")
    promote_p.add_argument("skill_id", type=str)

    demote_p = subparsers.add_parser("demote", help="Demote dynamic skill to staged quarantine.")
    demote_p.add_argument("skill_id", type=str)

    rename_p = subparsers.add_parser("rename", help="Rename a skill_id across manifest files.")
    rename_p.add_argument("old_skill_id", type=str)
    rename_p.add_argument("new_skill_id", type=str)

    delete_p = subparsers.add_parser("delete", help="Purge skill completely from disk and DB.")
    delete_p.add_argument("skill_id", type=str)

    parsed, unknown = parser.parse_known_args(args)

    if not parsed.subcommand:
        if unknown:
            parser.print_help()
            return 1
        from charon.cli.librarian.tui import LibrarianTUI

        tui = LibrarianTUI()
        tui.start()
        return 0

    if parsed.subcommand == "list":
        return run_list()
    elif parsed.subcommand == "check":
        return run_check(paths=parsed.paths, auto_fix=parsed.fix)
    elif parsed.subcommand == "sync":
        return run_sync()
    elif parsed.subcommand == "audit":
        return run_audit()
    elif parsed.subcommand in ("grant", "revoke"):
        return run_permission_change(
            skill_id=parsed.skill_id,
            agent_id=parsed.agent,
            action=parsed.subcommand,
        )
    elif parsed.subcommand == "set-default-action":
        return set_default_action(
            agent_id=parsed.agent_id,
            action_name=parsed.action_name,
        )
    elif parsed.subcommand == "purge-gaps":
        purge_resolved_gaps()
        return 0
    elif parsed.subcommand == "create":
        return run_create(
            skill_id=parsed.skill_id,
            category=parsed.category,
            target_agent=parsed.agent,
        )
    elif parsed.subcommand == "ingest":
        return run_ingest(
            source_path=parsed.path,
            skill_id=parsed.skill_id,
            target_agent=parsed.agent,
        )
    elif parsed.subcommand == "edit":
        return run_edit(skill_id=parsed.skill_id)
    elif parsed.subcommand == "promote":
        return run_promote(skill_id=parsed.skill_id)
    elif parsed.subcommand == "demote":
        return run_demote(skill_id=parsed.skill_id)
    elif parsed.subcommand == "rename":
        return run_rename(
            old_skill_id=parsed.old_skill_id,
            new_skill_id=parsed.new_skill_id,
        )
    elif parsed.subcommand == "delete":
        return run_delete_skill(skill_id=parsed.skill_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `../charon/cli/database.py`

```python
"""
charon/cli/librarian/database.py
System Version: v0.3.0 | File Revision: 2.0.0

Module: SQLite registry synchronization, agent_skill_map verification, and drift auditing.
Updated to support namespaced action unrolling and accurate FK schema alignment.
"""

import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Set, Tuple

from rich.console import Console
from rich.table import Table

from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.core.skills import SkillLibrarian
from charon.db.connection import get_connection

console = Console()
logger = logging.getLogger("charon.cli.librarian.database")


def _slugify(text: str) -> str:
    """Converts display names/categories to clean snake_case identifiers."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")


def run_sync() -> int:
    """Re-indexes filesystem manifests into the SQLite skill_registry table."""
    console.print(
        "[bold blue]Syncing filesystem skill manifests into SQLite registry...[/bold blue]"
    )
    librarian = SkillLibrarian.get_instance()
    librarian.reindex_skills()

    count = 0
    if STATE_DB_PATH.exists():
        try:
            with get_connection(STATE_DB_PATH, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM skill_registry")
                row = cursor.fetchone()
                count = row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to fetch skill count from SQLite: {e}")

    console.print(
        f"[bold green]✅ Sync complete.[/bold green] Total registered action handlers: [bold white]{count}[/bold white]"
    )
    return 0


def _audit_agent_skill_map(conn) -> List[Tuple[str, str]]:
    """Identifies orphaned records in agent_skill_map referencing missing skill_ids."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_skill_map'"
    )
    if not cursor.fetchone():
        return []

    # Joined on skill_id to match agent_skill_map foreign key schema
    cursor.execute("""
        SELECT asm.agent_id, asm.skill_id
        FROM agent_skill_map asm
        LEFT JOIN skill_registry sr ON asm.skill_id = sr.skill_id
        WHERE sr.skill_id IS NULL
    """)
    return cursor.fetchall()


def run_audit() -> int:
    """Audits SQLite registry state against disk manifests and validates agent_skill_map integrity."""
    console.print(
        "[bold blue]🔍 Auditing SQLite Skill Registry & agent_skill_map vs Filesystem...[/bold blue]\n"
    )

    db_registered_actions: Set[str] = set()
    db_registered_skills: Set[str] = set()
    orphaned_mappings: List[Tuple[str, str]] = []

    if STATE_DB_PATH.exists():
        try:
            with get_connection(STATE_DB_PATH, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT skill_id, action_name FROM skill_registry")
                for row in cursor.fetchall():
                    db_registered_skills.add(row[0])
                    db_registered_actions.add(row[1])

                orphaned_mappings = _audit_agent_skill_map(conn)

        except Exception as e:
            console.print(
                f"[bold red]DB Error:[/bold red] Failed to query SQLite state: {e}"
            )
            return 1

    disk_manifests: Dict[str, Dict[str, Any]] = {}
    search_dirs = [
        PKG_STAGED_SKILLS_DIR,
        PKG_DYNAMIC_SKILLS_DIR,
        DYNAMIC_SKILLS_DIR,
    ]

    for root in search_dirs:
        if not root.exists():
            continue
        for manifest_path in root.rglob("manifest.json"):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sid = data.get("skill_id")
                    if sid:
                        category = data.get("category", "General")
                        category_slug = _slugify(category)
                        actions = data.get("supported_actions", {})

                        expected_actions = []
                        if isinstance(actions, dict):
                            for action_key in actions.keys():
                                expected_actions.append(f"{category_slug}:{action_key}")

                        disk_manifests[sid] = {
                            "path": manifest_path,
                            "category": category,
                            "expected_actions": expected_actions,
                        }
            except Exception as e:
                logger.warning(f"Failed to read manifest at {manifest_path}: {e}")
                continue

    if not disk_manifests and not db_registered_skills:
        console.print(
            "[yellow]No skills discovered in SQLite or on disk.[/yellow]"
        )
        return 0

    table = Table(title="Charon Skill Registry vs Filesystem Audit")
    table.add_column("Manifest Skill ID", style="bold white")
    table.add_column("Category", style="cyan")
    table.add_column("Disk Actions", justify="center")
    table.add_column("DB Indexed Actions", justify="center")
    table.add_column("Drift Analysis", style="yellow")

    drift_count = 0

    for sid, meta in disk_manifests.items():
        expected_actions = meta["expected_actions"]
        indexed_actions = [
            act for act in expected_actions if act in db_registered_actions
        ]

        disk_count = len(expected_actions)
        db_count = len(indexed_actions)

        action_str = f"{disk_count} / {db_count}"

        if db_count == 0:
            analysis = "[bold red]Unindexed Skill[/bold red] (Run sync to index)"
            drift_count += 1
        elif db_count < disk_count:
            analysis = f"[bold yellow]Partial Actions Indexed[/bold yellow] ({disk_count - db_count} missing)"
            drift_count += 1
        else:
            analysis = "[dim green]In Sync[/dim green]"

        table.add_row(sid, meta["category"], str(disk_count), str(db_count), analysis)

    console.print(table)

    # Report orphaned agent_skill_map entries if found
    if orphaned_mappings:
        drift_count += len(orphaned_mappings)
        console.print(
            f"\n[bold red]⚠️ agent_skill_map Integrity Faults ({len(orphaned_mappings)} found):[/bold red]"
        )
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
        return 1

    console.print(
        "\n[bold green]✅ Database, agent_skill_map, and Filesystem are 100% in sync.[/bold green]"
    )
    return 0


if __name__ == "__main__":
    run_audit()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/forge.py`

```python
"""
charon/cli/librarian/forge.py
System Version: v0.2.0 | File Revision: 3.1.0

Module: Charon Skill Forge utility integrated within Librarian.
Handles querying open skill gaps, forging candidate dynamic skill scaffolds,
indexing dynamic skills, and resolving gaps in Schema V3.
"""

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from charon.cli.librarian.service import register_and_bind_skill
from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.core.skills import SkillLibrarian
from charon.db.repositories import SkillGapRepository, SkillRepository

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] [FORGE] %(message)s")
logger = logging.getLogger("charon.cli.librarian.forge")


def fetch_open_gaps(db_path: Path = STATE_DB_PATH) -> List[Dict[str, Any]]:
    """Fetches all open skill gaps from the state database via repository layer."""
    if not Path(db_path).exists():
        logger.warning(f"Database not found at {db_path}")
        return []

    try:
        repo = SkillGapRepository(db_path)
        return repo.get_open_gaps()
    except Exception as e:
        logger.error(f"Error querying skill_gaps table: {e}")
        return []


def forge_skill_scaffold(
    action_name: str,
    target_agent: str,
    output_dir: Optional[Path] = None,
    system_requirements: Optional[List[str]] = None,
) -> Path:
    """Synthesizes a skill blueprint scaffold on disk (manifest.json + plugin.py) aligned with V3 schema."""
    skill_id = f"{action_name}_skill"
    base_dir = output_dir or (PKG_STAGED_SKILLS_DIR / skill_id)
    base_dir.mkdir(parents=True, exist_ok=True)

    manifest_data = {
        "skill_id": skill_id,
        "version": "0.1.0",
        "stage": "Staged",
        "category": "Dynamic",
        "description": f"Dynamic skill handler for action '{action_name}'",
        "allowed_agents": [target_agent],
        "supported_actions": {
            action_name: {
                "description": f"Executes '{action_name}'",
                "handler_name": "execute",
                "parameters": {},
            }
        },
        "system_requirements": system_requirements or [],
        "consumed_artifacts": [],
        "produced_artifacts": [],
    }

    manifest_path = base_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    plugin_code = f'''"""
Dynamic skill plugin for action '{action_name}'.
Synthesized by Charon Skill Forge.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("charon.skills.{skill_id}")


def execute(agent_name: str, parameters: Dict[str, Any], raw_prompt: str = "") -> Dict[str, Any]:
    logger.info(f"[FORGED-SKILL] Executing {action_name} for agent '{{agent_name}}'")
    return {{
        "status": "success",
        "action": "{action_name}",
        "executed_by": agent_name,
        "parameters": parameters,
        "message": "Successfully executed forged skill handler.",
    }}
'''
    plugin_path = base_dir / "plugin.py"
    with open(plugin_path, "w", encoding="utf-8") as f:
        f.write(plugin_code)

    logger.info(f"✅ Successfully forged skill blueprint at: {base_dir}")
    return base_dir


def register_disk_skills(db_path: Path = STATE_DB_PATH) -> int:
    """Scans search paths, parses manifest.json files, and populates Schema V3 DB tables."""
    search_paths = [PKG_DYNAMIC_SKILLS_DIR, PKG_STAGED_SKILLS_DIR, DYNAMIC_SKILLS_DIR]
    count = 0

    for search_path in search_paths:
        expanded = Path(search_path).expanduser().resolve()
        if not expanded.exists() or not expanded.is_dir():
            continue
        for manifest_path in expanded.rglob("manifest.json"):
            try:
                manifest_content = manifest_path.read_text(encoding="utf-8")
                manifest_data = json.loads(manifest_content)
                plugin_entry = manifest_path.parent / "plugin.py"

                if not plugin_entry.exists():
                    logger.warning(
                        f"Skipping {manifest_data.get('skill_id', manifest_path.parent.name)}: missing plugin.py at {plugin_entry}"
                    )
                    continue

                # Delegate directly to the V3 registration service
                register_and_bind_skill(
                    skill_manifest=manifest_data,
                    entry_file_path=plugin_entry,
                    db_path=db_path,
                )
                count += 1
                logger.info(
                    f"Indexed dynamic action(s) for '{manifest_data.get('skill_id')}' from {manifest_path}"
                )
            except Exception as exc:
                logger.error(f"Error processing {manifest_path}: {exc}")

    return count


def sync_db(db_path: Path = STATE_DB_PATH) -> int:
    """Ensures schema consistency and re-indexes all disk skills into the registry."""
    try:
        repo = SkillRepository(str(db_path))
        if hasattr(repo, "ensure_schema"):
            repo.ensure_schema()
    except Exception as exc:
        logger.warning(f"Could not execute SkillRepository schema verification: {exc}")

    return register_disk_skills(db_path)


def promote_and_resolve_gap(
    gap_id: int,
    skill_dir: Path,
    db_path: Path = STATE_DB_PATH,
) -> bool:
    """Indexes newly forged skill via SkillLibrarian/register_disk_skills and marks gap as resolved."""
    indexed_count = 0
    try:
        librarian = SkillLibrarian.get_instance()
        if hasattr(librarian, "index_skill_directory"):
            indexed_count = librarian.index_skill_directory(skill_dir)
        elif hasattr(librarian, "scan_and_index"):
            indexed_count = librarian.scan_and_index(skill_dir)
    except Exception as exc:
        logger.debug(f"Librarian instance lookup fallback: {exc}")

    if indexed_count == 0:
        logger.info("Re-running V3 service sync fallback...")
        indexed_count = register_disk_skills(db_path)

    try:
        repo = SkillGapRepository(db_path)
        repo.resolve_gap(gap_id)
        logger.info(f"✅ Marked Gap ID {gap_id} as 'resolved' in state database.")
    except Exception as e:
        logger.error(f"Failed to resolve gap ID {gap_id} in database: {e}")
        return False

    return True


def build_parser() -> argparse.ArgumentParser:
    """Builds parser for charon-forge and charon forge CLI execution."""
    parser = argparse.ArgumentParser(
        prog="charon-forge",
        description="Charon Skill Forge: Inspect skill gaps, forge plugins, and manage skill indexing.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Forge Subcommands")

    list_p = subparsers.add_parser("list", help="List all open skill gaps logged in charon_state.db")
    list_p.add_argument("--db", type=Path, default=STATE_DB_PATH, help="Path to charon_state.db")

    scaffold_p = subparsers.add_parser("scaffold", help="Synthesize plugin scaffold on disk")
    scaffold_p.add_argument("--action", required=True, help="Target action name")
    scaffold_p.add_argument("--agent", required=True, help="Target requesting agent")
    scaffold_p.add_argument("--out", type=Path, default=None, help="Output directory path")
    scaffold_p.add_argument("--reqs", nargs="*", default=[], help="System requirements/binaries")

    resolve_p = subparsers.add_parser("resolve", help="Forge, index skill, and close gap ID")
    resolve_p.add_argument("--gap-id", type=int, required=True, help="Gap ID in skill_gaps table")
    resolve_p.add_argument("--action", required=True, help="Action name to forge and index")
    resolve_p.add_argument("--agent", required=True, help="Requesting agent name")
    resolve_p.add_argument("--db", type=Path, default=STATE_DB_PATH, help="Path to charon_state.db")

    sync_p = subparsers.add_parser("sync", help="Synchronize database schema and re-index disk skills")
    sync_p.add_argument("--db", type=Path, default=STATE_DB_PATH, help="Path to charon_state.db")

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point supporting direct or programmatically passed arguments."""
    parser = build_parser()
    parsed_args = parser.parse_args(args)

    if not parsed_args.command or parsed_args.command == "list":
        db_path = getattr(parsed_args, "db", STATE_DB_PATH)
        gaps = fetch_open_gaps(db_path=db_path)
        print(f"\n=================== Open Skill Gaps ({len(gaps)}) ===================")
        if not gaps:
            print(" No open skill gaps currently logged.")
        else:
            for g in gaps:
                prereqs = f" (Missing: {g['missing_prerequisites']})" if g.get('missing_prerequisites') else ""
                print(f" • [ID {g['gap_id']}] Action: '{g['action_name']}' | Agent: {g['requesting_agent']}{prereqs}")
        print("=================================================================\n")
        return 0

    elif parsed_args.command == "scaffold":
        staged_dir = forge_skill_scaffold(
            action_name=parsed_args.action,
            target_agent=parsed_args.agent,
            output_dir=parsed_args.out,
            system_requirements=parsed_args.reqs,
        )
        print(f"Skill scaffold generated at: {staged_dir}")
        return 0

    elif parsed_args.command == "resolve":
        db_path = getattr(parsed_args, "db", STATE_DB_PATH)
        staged_dir = forge_skill_scaffold(
            action_name=parsed_args.action,
            target_agent=parsed_args.agent,
        )
        success = promote_and_resolve_gap(
            gap_id=parsed_args.gap_id,
            skill_dir=staged_dir,
            db_path=db_path,
        )
        return 0 if success else 1

    elif parsed_args.command == "sync":
        db_path = getattr(parsed_args, "db", STATE_DB_PATH)
        logger.info(f"Syncing DB and re-indexing skills for {db_path}...")
        indexed_count = sync_db(db_path)
        logger.info(f"Database sync complete. Indexed {indexed_count} skills.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/ingestion.py`

```python
"""
charon/cli/librarian/ingestion.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Dynamic skill creation, file ingestion, and interactive $EDITOR editing launcher.
Templates are dynamically loaded from charon/skills/templates/ rather than hardcoded.
Refactored with AST pre-validation, schema compliance checks, transaction safety,
and interactive skill identifier resolution with collision prevention.
"""

import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Optional, Tuple

from rich.console import Console
from rich.prompt import Confirm, Prompt

from charon.cli.database import run_sync
from charon.cli.librarian.manifest import validate_manifest_file
from charon.cli.librarian.permissions import find_skill_manifest
from charon.cli.librarian.service import register_and_bind_skill
from charon.config.paths import PKG_DYNAMIC_SKILLS_DIR, PKG_STAGED_SKILLS_DIR

console = Console()

SKILLS_TEMPLATES_DIR = (
        Path(__file__).resolve().parents[2] / "skills" / "templates"
)


def _slugify(text: str) -> str:
    """Normalizes raw input strings into clean snake_case identifiers."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")


def is_skill_id_taken(skill_id: str) -> bool:
    """Checks if a skill identifier already exists in staged or dynamic registries."""
    staged_path = PKG_STAGED_SKILLS_DIR / skill_id
    dynamic_path = PKG_DYNAMIC_SKILLS_DIR / skill_id
    return staged_path.exists() or dynamic_path.exists()


def resolve_ingestion_skill_id(
        source_path: Path, explicit_id: Optional[str] = None
) -> Optional[str]:
    """Interactively resolves and validates a non-colliding skill identifier with the user."""
    manifest_id = None

    # Pre-read manifest skill_id if source is a directory with a manifest
    if source_path.is_dir():
        manifest_file = source_path / "manifest.json"
        if manifest_file.exists():
            try:
                data = json.loads(manifest_file.read_text(encoding="utf-8"))
                manifest_id = data.get("skill_id")
            except Exception:
                pass

    raw_proposed = explicit_id or manifest_id or source_path.stem
    proposed_id = _slugify(raw_proposed)

    console.print("\n[bold cyan]📦 Skill Ingestion Setup[/bold cyan]")
    console.print(f"Target Source: [dim]{source_path}[/dim]")
    console.print(f"Proposed Skill ID: [bold yellow]{proposed_id}[/bold yellow]")

    # Check for collision on proposed name
    if is_skill_id_taken(proposed_id):
        console.print(
            f"[bold red]⚠️ Collision Alert:[/bold red] Skill ID '[cyan]{proposed_id}[/cyan]' already exists in staged or dynamic registries."
        )
        use_proposed = False
    else:
        use_proposed = Confirm.ask(
            f"Ingest skill using identifier '[bold green]{proposed_id}[/bold green]'?",
            default=True,
        )

    if use_proposed:
        return proposed_id

    # Interactive prompt loop for custom identifier
    while True:
        custom_input = Prompt.ask(
            "\n[bold cyan]Enter custom skill identifier[/bold cyan] (or 'cancel' to abort)"
        ).strip()

        if custom_input.lower() == "cancel" or not custom_input:
            console.print("[yellow]Ingestion cancelled by user.[/yellow]")
            return None

        clean_id = _slugify(custom_input)

        if not clean_id:
            console.print(
                "[bold red]Error:[/bold red] Invalid identifier. Must contain alphanumeric characters."
            )
            continue

        if is_skill_id_taken(clean_id):
            console.print(
                f"[bold red]Error:[/bold red] Skill ID '[cyan]{clean_id}[/cyan]' is already taken. Please choose another."
            )
            continue

        console.print(f"[bold green]✓ Approved identifier:[/bold green] {clean_id}")
        return clean_id


def get_template_content(
        filename: str, replacements: Optional[dict] = None
) -> str:
    """Reads a template file from charon/skills/templates and replaces double-curly placeholders."""
    template_path = SKILLS_TEMPLATES_DIR / filename
    if not template_path.exists():
        raise FileNotFoundError(
            f"Required template file missing at: {template_path}"
        )

    content = template_path.read_text(encoding="utf-8")
    if replacements:
        for key, value in replacements.items():
            content = content.replace(f"{{{{{key}}}}}", str(value))
    return content


def verify_plugin_entrypoint(plugin_path: Path) -> Tuple[bool, str]:
    """Uses AST parsing to verify that plugin.py is syntactically valid and exposes a handler."""
    if not plugin_path.exists():
        return False, f"Plugin file missing at: {plugin_path}"

    try:
        tree = ast.parse(plugin_path.read_text(encoding="utf-8"), filename=str(plugin_path))
        declared_functions = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }

        # Plugin must define execute_action OR at least one handle_* function
        if "execute_action" not in declared_functions and not any(
                f.startswith("handle_") for f in declared_functions
        ):
            return (
                False,
                "Plugin must define 'execute_action' router or at least one 'handle_<action>' function.",
            )

        return True, ""
    except SyntaxError as e:
        return False, f"Syntax error in plugin file '{plugin_path.name}': {e}"


def run_create(skill_id: str, category: str = "General", target_agent: Optional[str] = None) -> int:
    """Scaffolds a new skill template package driven by charon/skills/templates/."""
    clean_skill_id = _slugify(skill_id)

    if is_skill_id_taken(clean_skill_id):
        console.print(
            f"[bold red]Error:[/bold red] Skill ID '[cyan]{clean_skill_id}[/cyan]' already exists in staged or dynamic registries."
        )
        return 1

    target_dir = PKG_STAGED_SKILLS_DIR / clean_skill_id
    target_dir.mkdir(parents=True, exist_ok=True)
    replacements = {"SKILL_ID": clean_skill_id, "CATEGORY": category}

    try:
        manifest_content = get_template_content("manifest.json", replacements)
        plugin_content = get_template_content("plugin.py", replacements)

        manifest_path = target_dir / "manifest.json"
        plugin_path = target_dir / "plugin.py"

        manifest_path.write_text(manifest_content, encoding="utf-8")
        plugin_path.write_text(plugin_content, encoding="utf-8")

        # 1. AST Static Verification
        valid_ast, ast_err = verify_plugin_entrypoint(plugin_path)
        if not valid_ast:
            console.print(f"[bold red]AST Validation Error:[/bold red] {ast_err}")
            shutil.rmtree(target_dir)
            return 1

        manifest_data = json.loads(manifest_content)

        # 2. Atomic Registration & Binding
        register_and_bind_skill(
            skill_manifest=manifest_data,
            entry_file_path=plugin_path,
            target_agent_id=target_agent,
        )

        console.print(
            f"[bold green]✅ Scaffolded and bound new skill '[cyan]{clean_skill_id}[/cyan]' at:[/bold green] {target_dir}"
        )
        return run_sync()

    except Exception as e:
        console.print(f"[bold red]Error creating skill scaffold:[/bold red] {e}")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        return 1


def run_ingest(source_path: Path, skill_id: Optional[str] = None, target_agent: Optional[str] = None) -> int:
    """Ingests external standalone Python files or folders into staged skills using templates for fallbacks."""
    source_path = source_path.expanduser().resolve()
    if not source_path.exists():
        console.print(f"[bold red]Error:[/bold red] Source path '{source_path}' does not exist.")
        return 1

    sid = resolve_ingestion_skill_id(source_path, explicit_id=skill_id)
    if not sid:
        return 1

    target_dir = PKG_STAGED_SKILLS_DIR / sid

    if target_dir.exists():
        console.print(
            f"[bold red]Error:[/bold red] Staged directory '[cyan]{sid}[/cyan]' already exists at {target_dir}"
        )
        return 1

    target_dir.mkdir(parents=True, exist_ok=True)
    replacements = {"SKILL_ID": sid, "CATEGORY": "Ingested"}

    try:
        if source_path.is_file():
            shutil.copy(source_path, target_dir / "plugin.py")
            manifest_content = get_template_content("manifest.json", replacements)
            (target_dir / "manifest.json").write_text(manifest_content, encoding="utf-8")

        elif source_path.is_dir():
            shutil.copytree(source_path, target_dir, dirs_exist_ok=True)

            if not (target_dir / "plugin.py").exists():
                py_files = list(target_dir.glob("*.py"))
                if len(py_files) == 1:
                    py_files[0].rename(target_dir / "plugin.py")
                elif not py_files:
                    plugin_content = get_template_content("plugin.py", replacements)
                    (target_dir / "plugin.py").write_text(plugin_content, encoding="utf-8")

            if not (target_dir / "manifest.json").exists():
                console.print(
                    "[yellow]No manifest.json found in directory. Generating schema scaffold from template...[/yellow]"
                )
                manifest_content = get_template_content("manifest.json", replacements)
                (target_dir / "manifest.json").write_text(manifest_content, encoding="utf-8")

        manifest_path = target_dir / "manifest.json"
        plugin_path = target_dir / "plugin.py"

        # Force manifest skill_id parity with approved folder identifier
        if manifest_path.exists():
            try:
                mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
                mdata["skill_id"] = sid
                manifest_path.write_text(json.dumps(mdata, indent=2), encoding="utf-8")
            except Exception as e:
                console.print(f"[yellow]Warning: Could not update manifest skill_id field: {e}[/yellow]")

        # 1. AST Entrypoint Verification
        valid_ast, ast_err = verify_plugin_entrypoint(plugin_path)
        if not valid_ast:
            console.print(f"[bold red]AST Validation Error:[/bold red] {ast_err}")
            shutil.rmtree(target_dir)
            return 1

        # 2. Schema Integrity Check
        is_valid, errors, _ = validate_manifest_file(manifest_path, auto_fix=True)
        if not is_valid:
            console.print(
                "[bold red]❌ Manifest failed schema validation:[/bold red]\n"
                + "\n".join(errors)
            )
            shutil.rmtree(target_dir)
            return 1

        # 3. Register and Bind
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        register_and_bind_skill(
            skill_manifest=manifest_data,
            entry_file_path=plugin_path,
            target_agent_id=target_agent,
        )

        console.print(
            f"[bold green]✅ Ingested '[cyan]{sid}[/cyan]' into staged skills at {target_dir}.[/bold green]"
        )
        return run_sync()

    except Exception as e:
        console.print(f"[bold red]Ingestion failed:[/bold red] {e}")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        return 1


def run_edit(skill_id: str) -> int:
    """Opens a skill manifest in $EDITOR, then validates and syncs automatically on exit."""
    manifest_path = find_skill_manifest(skill_id)
    if not manifest_path:
        console.print(f"[bold red]Error:[/bold red] Could not locate skill '{skill_id}'.")
        return 1

    editor = os.environ.get("EDITOR", "nano")
    console.print(f"[bold cyan]Opening {manifest_path} with {editor}...[/bold cyan]")
    subprocess.call([editor, str(manifest_path)])

    is_valid, errors, _ = validate_manifest_file(manifest_path, auto_fix=True)
    if not is_valid:
        console.print(
            "[bold red]❌ Manifest contains schema errors after edit:[/bold red]\n"
            + "\n".join(errors)
        )
        return 1

    console.print("[bold green]✅ Manifest validation passed.[/bold green]")
    return run_sync()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/lifecycle.py`

```python
"""
charon/cli/librarian/lifecycle.py
System Version: v0.2.0 | File Revision: 2.1.0

Module: Skill lifecycle operations: promotion, demotion/quarantine, renaming, and purging.
Features strict isolation guards to prevent unintended directory deletion or database record wipes.
"""

import json
import logging
from pathlib import Path
import re
import shutil
from typing import List, Optional

from rich.console import Console

from charon.cli.database import run_sync
from charon.cli.librarian.manifest import validate_manifest_file
from charon.cli.librarian.permissions import find_skill_manifest
from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.db.connection import get_connection

console = Console()
logger = logging.getLogger("charon.cli.librarian.lifecycle")


def _slugify(text: str) -> str:
    """Normalizes raw input strings into clean snake_case identifiers."""
    if not text:
        return ""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")


def _cleanup_agent_mappings_for_skill(skill_id: str) -> None:
    """
    Purges corresponding bindings from agent_skill_map BEFORE database resync.

    SAFETY GUARANTEE: Uses explicit parameter binding scoped strictly to `skill_id`.
    Never executes global tables resets or un-parameterized DELETE statements.
    """
    if not STATE_DB_PATH.exists() or not skill_id:
        return
    try:
        with get_connection(STATE_DB_PATH) as conn:
            cursor = conn.cursor()
            # Delete ONLY mappings for this explicit skill_id
            cursor.execute(
                "DELETE FROM agent_skill_map WHERE skill_id = ?",
                (skill_id,),
            )
            # Delete ONLY skill_registry record for this explicit skill_id
            cursor.execute(
                "DELETE FROM skill_registry WHERE skill_id = ?",
                (skill_id,),
            )
            conn.commit()
            logger.info(f"Purged database records scoped strictly to skill_id='{skill_id}'")
    except Exception as e:
        logger.warning(f"Failed to purge DB records for skill '{skill_id}': {e}")


def run_promote(skill_id: str) -> int:
    """Promotes a staged skill into active production dynamic status after schema validation."""
    clean_id = _slugify(skill_id)
    if not clean_id:
        console.print("[bold red]Error:[/bold red] Invalid skill_id provided.")
        return 1

    staged_manifest = find_skill_manifest(clean_id, stage_filter="Staged")
    if not staged_manifest:
        console.print(
            f"[bold red]Error:[/bold red] Skill '{clean_id}' with stage='Staged' not found."
        )
        return 1

    # Pre-check schema validity before promoting
    is_valid, errors, _ = validate_manifest_file(staged_manifest, auto_fix=True)
    if not is_valid:
        console.print(
            "[bold red]❌ Cannot promote invalid skill manifest:[/bold red]\n"
            + "\n".join(errors)
        )
        return 1

    staged_dir = staged_manifest.parent
    target_dir = PKG_DYNAMIC_SKILLS_DIR / staged_dir.name

    existing_dynamic_manifest = find_skill_manifest(
        clean_id, stage_filter="Dynamic"
    )
    old_dynamic_dir: Optional[Path] = (
        existing_dynamic_manifest.parent
        if existing_dynamic_manifest
        else None
    )

    shutil.copytree(staged_dir, target_dir, dirs_exist_ok=True)

    target_manifest = target_dir / "manifest.json"
    if target_manifest.exists():
        with open(target_manifest, "r+", encoding="utf-8") as f:
            data = json.load(f)
            data["stage"] = "Dynamic"
            f.seek(0)
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.truncate()
            f.write("\n")

    shutil.rmtree(staged_dir)

    # Clean up redundant dynamic dir if target moved locations
    if (
            old_dynamic_dir
            and old_dynamic_dir.exists()
            and old_dynamic_dir.resolve() != target_dir.resolve()
    ):
        shutil.rmtree(old_dynamic_dir)
        console.print(
            f"[dim]Cleaned up redundant dynamic directory: {old_dynamic_dir}[/dim]"
        )

    console.print(
        f"[bold green]✅ Promoted[/bold green] skill '[bold white]{clean_id}[/bold white]' -> [cyan]{target_dir}[/cyan]"
    )
    return run_sync()


def run_demote(skill_id: str) -> int:
    """Demotes/quarantines a dynamic skill back to staged status for debugging."""
    clean_id = _slugify(skill_id)
    if not clean_id:
        console.print("[bold red]Error:[/bold red] Invalid skill_id provided.")
        return 1

    dynamic_manifest = find_skill_manifest(clean_id, stage_filter="Dynamic")
    if not dynamic_manifest:
        console.print(
            f"[bold red]Error:[/bold red] Active dynamic skill '{clean_id}' not found."
        )
        return 1

    dynamic_dir = dynamic_manifest.parent
    target_dir = PKG_STAGED_SKILLS_DIR / dynamic_dir.name

    shutil.copytree(dynamic_dir, target_dir, dirs_exist_ok=True)
    shutil.rmtree(dynamic_dir)

    staged_manifest = target_dir / "manifest.json"
    if staged_manifest.exists():
        with open(staged_manifest, "r+", encoding="utf-8") as f:
            data = json.load(f)
            data["stage"] = "Staged"
            f.seek(0)
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.truncate()
            f.write("\n")

    console.print(
        f"[bold yellow]⚠️ Demoted[/bold yellow] skill '[bold white]{clean_id}[/bold white]' -> [cyan]{target_dir}[/cyan]"
    )
    return run_sync()


def run_rename(old_skill_id: str, new_skill_id: str) -> int:
    """Renames a skill_id inside its manifest, updates folder structure, and syncs SQLite indexing."""
    clean_old_id = _slugify(old_skill_id)
    clean_new_id = _slugify(new_skill_id)

    if not clean_old_id or not clean_new_id:
        console.print("[bold red]Error:[/bold red] Source and target skill IDs must be non-empty.")
        return 1

    manifest_path = find_skill_manifest(clean_old_id)
    if not manifest_path:
        console.print(
            f"[bold red]Error:[/bold red] Could not locate skill '{clean_old_id}'."
        )
        return 1

    skill_dir = manifest_path.parent
    target_dir = skill_dir.parent / clean_new_id

    # COLLISION GUARD: Prevent overwriting an existing non-target folder
    if target_dir.exists() and target_dir.resolve() != skill_dir.resolve():
        console.print(
            f"[bold red]Error:[/bold red] Target directory already exists: {target_dir}"
        )
        return 1

    # In-place manifest update for skill_id
    with open(manifest_path, "r+", encoding="utf-8") as f:
        data = json.load(f)
        data["skill_id"] = clean_new_id
        f.seek(0)
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.truncate()
        f.write("\n")

    if skill_dir.name != clean_new_id:
        skill_dir.rename(target_dir)
        console.print(
            f"[dim]Renamed skill folder {skill_dir} -> {target_dir}[/dim]"
        )

    # Scoped database cleanup for old ID to avoid orphaned DB records
    _cleanup_agent_mappings_for_skill(clean_old_id)

    console.print(
        f"[bold green]✅ Renamed[/bold green] '{clean_old_id}' -> '[bold cyan]{clean_new_id}[/bold cyan]'."
    )
    return run_sync()


def run_delete_skill(skill_id: str) -> int:
    """
    Purges directory instances of a specific skill and cleans corresponding SQLite records.

    SAFETY ISOLATION GUARANTEES:
      1. Requires explicit non-empty skill_id (prevents empty/wildcard matching).
      2. Validates child subfolder depth to prevent wiping root skill directories.
      3. Scopes DB removal queries strictly to the target skill_id.
    """
    clean_id = _slugify(skill_id)
    if not clean_id:
        console.print("[bold red]Error:[/bold red] Cannot execute deletion with an empty or invalid skill_id.")
        return 1

    search_roots = [
        PKG_STAGED_SKILLS_DIR,
        PKG_DYNAMIC_SKILLS_DIR,
        DYNAMIC_SKILLS_DIR,
    ]

    # Protected root directories that must NEVER be deleted
    protected_roots = {r.resolve() for r in search_roots if r.exists()}
    protected_roots.update({Path.home().resolve(), Path.cwd().resolve(), Path("/").resolve()})

    deleted_paths: List[Path] = []

    for root in search_roots:
        if not root.exists():
            continue

        for manifest_path in list(root.rglob("manifest.json")):
            skill_dir = manifest_path.parent.resolve()

            # SAFETY GUARD 1: Absolute protection against wiping root container directories
            if skill_dir in protected_roots:
                logger.warning(
                    f"Skipping deletion at {manifest_path}: Manifest is located directly in root directory {skill_dir}."
                )
                continue

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                manifest_id = data.get("skill_id")

                # SAFETY GUARD 2: Explicit equality match on skill_id
                if manifest_id == clean_id or manifest_id == skill_id:
                    if skill_dir.exists():
                        shutil.rmtree(skill_dir)
                        deleted_paths.append(skill_dir)
            except Exception as e:
                logger.error(f"Error inspecting manifest at {manifest_path}: {e}")

    if not deleted_paths:
        console.print(
            f"[bold red]Error:[/bold red] Could not locate any skill folder matching '{clean_id}'."
        )
        return 1

    # SAFETY GUARD 3: Targeted DB cleanup scoped only to target skill_id
    _cleanup_agent_mappings_for_skill(clean_id)

    for p in deleted_paths:
        console.print(f"[bold yellow]🗑️ Purged directory:[/bold yellow] {p}")

    console.print(
        f"[bold green]✅ Successfully deleted skill '[bold cyan]{clean_id}[/bold cyan]'.[/bold green]"
    )
    return run_sync()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/manifest.py`

```python
"""
charon/cli/librarian/manifest.py
System Version: v0.2.0 | File Revision: 2.0.0

Module: Dynamic, schema-driven manifest validation and auto-migration engine.
Leverages Pydantic SkillManifest model directly to eliminate hardcoded format constraints.
Refactored for multi-action unrolling, robust schema fallback, and clean CLI diagnostics.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
)
from charon.core.skills import SkillManifest

console = Console()
logger = logging.getLogger("charon.cli.librarian.manifest")


def _migrate_raw_dict(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Dynamically converts legacy/deprecated dictionary keys to the current SkillManifest schema."""
    migrated = dict(raw)
    modified = False

    # Ensure required top-level defaults
    if "category" not in migrated or not migrated["category"]:
        migrated["category"] = "General"
        modified = True

    if "version" not in migrated or not migrated["version"]:
        migrated["version"] = "1.0.0"
        modified = True

    # Standardize actions / legacy keys into supported_actions mapping
    if "actions" in migrated and "supported_actions" not in migrated:
        actions = migrated.pop("actions")
        if isinstance(actions, dict):
            migrated["supported_actions"] = actions
            modified = True
        elif isinstance(actions, list):
            migrated["supported_actions"] = {
                act.get("name", f"action_{i}"): act
                for i, act in enumerate(actions)
                if isinstance(act, dict)
            }
            modified = True

    # Flatten single handler declarations into supported_actions mapping
    if "handler_name" in migrated and "supported_actions" not in migrated:
        handler = migrated.pop("handler_name")
        skill_id = migrated.get("skill_id", "default_action")
        migrated["supported_actions"] = {
            skill_id: {
                "handler_name": handler,
                "description": migrated.get(
                    "description", "Auto-migrated handler"
                ),
            }
        }
        modified = True

    # Standardize shorthand string actions into full canonical dictionaries
    if "supported_actions" in migrated and isinstance(migrated["supported_actions"], dict):
        for act_key, act_val in list(migrated["supported_actions"].items()):
            if isinstance(act_val, str):
                migrated["supported_actions"][act_key] = {
                    "description": act_val,
                    "parameters": {}
                }
                modified = True
            elif isinstance(act_val, dict):
                if "description" not in act_val or not act_val["description"]:
                    act_val["description"] = f"Execution action handler for {act_key}"
                    modified = True

    return migrated, modified


def validate_manifest_file(
    file_path: Path, auto_fix: bool = False
) -> Tuple[bool, List[str], bool]:
    """Validates a manifest against Pydantic SkillManifest schema and performs auto-migration if enabled."""
    if not file_path.exists():
        return False, [f"File not found: {file_path}"], False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        return False, [f"JSON Parse Error: {e}"], False

    if not isinstance(raw_data, dict):
        return False, ["Invalid manifest structure: root JSON must be an object"], False

    migrated_data, was_migrated = _migrate_raw_dict(raw_data)

    try:
        manifest = SkillManifest.model_validate(migrated_data)
        was_fixed = False

        if (was_migrated or auto_fix) and auto_fix:
            canonical_data = manifest.model_dump(exclude_none=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(canonical_data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            was_fixed = True

        return True, [], was_fixed
    except ValidationError as ve:
        errors = [
            f"Field '{' -> '.join(str(x) for x in err['loc'])}': {err['msg']}"
            for err in ve.errors()
        ]
        return False, errors, False


def run_check(
    paths: Optional[List[Path]] = None, auto_fix: bool = False
) -> int:
    """Scans target paths and outputs a schema validation diagnostic report."""
    target_paths = paths or [
        PKG_DYNAMIC_SKILLS_DIR,
        PKG_STAGED_SKILLS_DIR,
        DYNAMIC_SKILLS_DIR,
    ]
    manifest_files: List[Path] = []

    for path in target_paths:
        if not path.exists():
            continue
        if path.is_file() and path.name == "manifest.json":
            manifest_files.append(path)
        elif path.is_dir():
            manifest_files.extend(path.rglob("manifest.json"))

    if not manifest_files:
        console.print(
            "[yellow]No `manifest.json` files discovered to check.[/yellow]"
        )
        return 0

    table = Table(title="Charon Skill Manifest Validation Report")
    table.add_column("Manifest Path", style="cyan", overflow="fold")
    table.add_column("Skill ID", style="bold white")
    table.add_column("Category", style="magenta")
    table.add_column("Actions", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Notes / Errors", style="dim")

    total_invalid = 0
    for manifest_path in manifest_files:
        is_valid, errors, was_fixed = validate_manifest_file(
            manifest_path, auto_fix=auto_fix
        )
        try:
            rel_path = str(manifest_path.relative_to(Path.cwd()))
        except ValueError:
            rel_path = str(manifest_path.resolve())

        if is_valid:
            status_str = (
                "[bold green]FIXED[/bold green]"
                if was_fixed
                else "[bold green]VALID[/bold green]"
            )
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                skill_id = data.get("skill_id", "unknown")
                category = data.get("category", "General")
                actions_count = str(len(data.get("supported_actions", {})))
            except Exception:
                skill_id, category, actions_count = "unknown", "General", "?"

            note = "Migrated to canonical schema" if was_fixed else "OK"
            table.add_row(rel_path, skill_id, category, actions_count, status_str, note)
        else:
            total_invalid += 1
            table.add_row(
                rel_path,
                "-",
                "-",
                "0",
                "[bold red]INVALID[/bold red]",
                f"[red]{' | '.join(errors)}[/red]",
            )

    console.print(table)
    return 0 if total_invalid == 0 else 1
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/permissions.py`

```python
"""
charon/cli/librarian/permissions.py
System Version: v0.2.0 | File Revision: 2.0.0

Module: DB-backed authorization management, default action configuration, and inventory views.
Aligned with Schema V3.
"""

import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.db.connection import get_connection

console = Console()


def find_skill_manifest(
    skill_id: str, stage_filter: Optional[str] = None
) -> Optional[Path]:
    """Locates a skill's manifest.json across staged and dynamic skill directories."""
    search_dirs = [
        PKG_STAGED_SKILLS_DIR,
        PKG_DYNAMIC_SKILLS_DIR,
        DYNAMIC_SKILLS_DIR,
    ]
    for root in search_dirs:
        if not root.exists():
            continue
        for manifest_path in root.rglob("manifest.json"):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("skill_id") == skill_id:
                        if (
                            stage_filter
                            and data.get("stage", "").lower()
                            != stage_filter.lower()
                        ):
                            continue
                        return manifest_path
            except Exception:
                continue
    return None


def run_permission_change(skill_id: str, agent_id: str, action: str) -> int:
    """Grants or revokes an agent's binding to a skill in agent_skill_map."""
    action_clean = action.lower().strip()
    if action_clean not in ("grant", "revoke"):
        console.print(
            f"[bold red]Error:[/bold red] Invalid permission action '{action}'. Use 'grant' or 'revoke'."
        )
        return 1

    with get_connection(STATE_DB_PATH) as conn:
        cursor = conn.cursor()

        # Validate skill exists in registry
        cursor.execute(
            "SELECT skill_id FROM skill_registry WHERE skill_id = ? LIMIT 1",
            (skill_id,),
        )
        if not cursor.fetchone():
            console.print(
                f"[bold red]Error:[/bold red] Skill ID '{skill_id}' not found in DB."
            )
            return 1

        # Validate agent exists in registry
        cursor.execute(
            "SELECT agent_id FROM agent_registry WHERE agent_id = ? LIMIT 1",
            (agent_id,),
        )
        if not cursor.fetchone():
            console.print(
                f"[bold red]Error:[/bold red] Agent ID '{agent_id}' not found in DB."
            )
            return 1

        if action_clean == "grant":
            cursor.execute(
                """
                INSERT INTO agent_skill_map (agent_id, skill_id)
                VALUES (?, ?)
                ON CONFLICT(agent_id, skill_id) DO NOTHING
                """,
                (agent_id, skill_id),
            )
            console.print(
                f"[bold green]✅ Granted[/bold green] agent '{agent_id}' access to skill '[bold cyan]{skill_id}[/bold cyan]'."
            )

        elif action_clean == "revoke":
            cursor.execute(
                "DELETE FROM agent_skill_map WHERE agent_id = ? AND skill_id = ?",
                (agent_id, skill_id),
            )
            console.print(
                f"[bold green]✅ Revoked[/bold green] agent '{agent_id}' access from skill '[bold cyan]{skill_id}[/bold cyan]'."
            )

        conn.commit()
    return 0


def set_default_action(agent_id: str, action_name: str) -> int:
    """Updates the default_action column in agent_registry for a specific agent."""
    with get_connection(STATE_DB_PATH) as conn:
        cursor = conn.cursor()

        # Ensure action exists in skill_registry and check status
        cursor.execute(
            "SELECT skill_id, status FROM skill_registry WHERE action_name = ? LIMIT 1",
            (action_name,),
        )
        row = cursor.fetchone()
        if not row:
            console.print(
                f"[bold red]Error:[/bold red] Action '{action_name}' does not exist in skill_registry."
            )
            return 1

        if row[1] != "ACTIVE":
            console.print(
                f"[bold yellow]Warning:[/bold yellow] Action '{action_name}' belongs to skill '{row[0]}' which has status '{row[1]}'."
            )

        cursor.execute(
            """
            UPDATE agent_registry
            SET default_action = ?, updated_at = CURRENT_TIMESTAMP
            WHERE agent_id = ?
            """,
            (action_name, agent_id),
        )

        if cursor.rowcount == 0:
            console.print(
                f"[bold red]Error:[/bold red] Agent '{agent_id}' not found in agent_registry."
            )
            return 1

        conn.commit()
        console.print(
            f"[bold green]✅ Set default action for agent '[cyan]{agent_id}[/cyan]' to '[bold yellow]{action_name}[/bold yellow]'."
        )
    return 0


def run_list() -> int:
    """Displays a formatted summary of skill_registry joined with authorized agents."""
    table = Table(title="Charon Skill Registry Inventory (V3 DB State)")
    table.add_column("Skill ID", style="bold white")
    table.add_column("Action Name", style="magenta")
    table.add_column("Status", style="cyan")
    table.add_column("Authorized Agents", style="green")
    table.add_column("Category", style="yellow")

    with get_connection(STATE_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                s.skill_id,
                s.action_name,
                s.status,
                s.category,
                GROUP_CONCAT(DISTINCT asm.agent_id) AS agents
            FROM skill_registry s
            LEFT JOIN agent_skill_map asm ON s.skill_id = asm.skill_id
            GROUP BY s.skill_id, s.action_name, s.status, s.category
            ORDER BY s.skill_id ASC, s.action_name ASC
            """
        )
        rows = cursor.fetchall()
        for row in rows:
            skill_id, action_name, status, category, agents = row
            formatted_agents = agents.replace(",", ", ") if agents else "[dim]None[/dim]"
            table.add_row(
                skill_id,
                action_name,
                status,
                category or "General",
                formatted_agents,
            )

    console.print(table)
    console.print(f"\n[bold]Total Registered Actions:[/bold] {len(rows)}\n")
    return 0
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/purge_gaps.py`

```python
"""
charon/cli/librarian/purge_gaps.py
System Version: v0.2.0 | File Revision: 1.2.0

Module: Database maintenance utilities for purging resolved gap records and optimizing state DB.
Aligned with Schema V3.
"""

import logging
import sys
from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("charon.cli.librarian.purge_gaps")


def purge_resolved_gaps() -> int:
    """
    Purges all resolved gap records from the state database and performs a VACUUM.
    Returns the total number of purged records.
    """
    if not STATE_DB_PATH.exists():
        logger.info(f"[MAINTENANCE] Database file not found at {STATE_DB_PATH}. Skipping purge.")
        return 0

    # 1. Execute the purge within a standard managed transaction
    with get_connection(STATE_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM skill_gaps WHERE LOWER(status) = 'resolved'")
        purged_count = cursor.rowcount
        conn.commit()

    # 2. Run VACUUM in autocommit mode if any records were purged
    if purged_count > 0:
        try:
            with get_connection(STATE_DB_PATH) as conn:
                conn.isolation_level = None  # Enable autocommit for VACUUM
                conn.execute("VACUUM")
            logger.info(f"[MAINTENANCE] Purged {purged_count} resolved gaps and vacuumed database.")
        except Exception as e:
            logger.warning(f"[MAINTENANCE] Purged {purged_count} records, but VACUUM failed: {e}")
    else:
        logger.info("[MAINTENANCE] No resolved gaps found to purge.")

    return purged_count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(0 if purge_resolved_gaps() >= 0 else 1)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/service.py`

```python
"""
charon/cli/librarian/service.py
System Version: v0.2.0 | File Revision: 2.0.0

Encapsulated service methods for registering skills, performing targeted agent bindings,
and seeding role-based routes according to the V3 database schema.
Guarantees strict isolation on all mutations and deletion operations.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("charon.cli.librarian.service")


def register_and_bind_skill(
    skill_manifest: Dict[str, Any],
    entry_file_path: Path,
    target_agent_id: Optional[str] = None,
    db_path: Optional[Path] = None,
    initial_status: str = "ACTIVE",
) -> None:
    """
    Executes skill lifecycle registration in an atomic, scoped transaction:
      1. UPSERT into skill_registry (Keyed on skill_id, action_name)
      2. INSERT into agent_skill_map (Relational authorization: agent_id <-> skill_id)
      3. UPSERT into route_registry (Action trigger <-> system_roles)
    """
    db_file = db_path or STATE_DB_PATH

    skill_id = skill_manifest.get("skill_id")
    if not skill_id:
        raise ValueError("Skill manifest must contain a valid 'skill_id'.")

    version = skill_manifest.get("version", "1.0.0")
    category = skill_manifest.get("category", "General")
    description = skill_manifest.get("description", "")
    sys_reqs = json.dumps(skill_manifest.get("system_requirements", []))
    consumed = json.dumps(skill_manifest.get("consumed_artifacts", []))
    produced = json.dumps(skill_manifest.get("produced_artifacts", []))

    allowed_agents = skill_manifest.get("allowed_agents", ["*"])
    if isinstance(allowed_agents, str):
        allowed_agents = [allowed_agents]

    is_global = 1 if ("*" in allowed_agents or skill_manifest.get("is_global", False)) else 0
    actions: Dict[str, Any] = skill_manifest.get("supported_actions", {})

    # Default fallback if no supported_actions defined
    if not actions:
        actions = {skill_id: {"description": description, "handler_name": "handle_default"}}

    resolved_entry_path = str(entry_file_path.resolve())

    with get_connection(db_file) as conn:
        cursor = conn.cursor()

        # -----------------------------------------------------------------
        # STEP 1: skill_registry (UPSERT action rows for this skill)
        # -----------------------------------------------------------------
        for action_name, action_def in actions.items():
            if isinstance(action_def, dict):
                act_desc = action_def.get("description") or description or f"Executes '{action_name}'"
                handler_name = (
                    action_def.get("handler_name")
                    or action_def.get("handler")
                    or f"handle_{action_name}"
                )
                params = json.dumps(action_def.get("parameters", {}))
            else:
                act_desc = description or f"Executes '{action_name}'"
                handler_name = str(action_def) if action_def else f"handle_{action_name}"
                params = json.dumps({})

            cursor.execute(
                """
                INSERT INTO skill_registry (
                    skill_id, action_name, version, category, description,
                    parameters, system_requirements, consumed_artifacts, 
                    produced_artifacts, entry_file_path, handler_name, status, is_global
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(skill_id, action_name) DO UPDATE SET
                    version=excluded.version,
                    category=excluded.category,
                    description=excluded.description,
                    parameters=excluded.parameters,
                    system_requirements=excluded.system_requirements,
                    consumed_artifacts=excluded.consumed_artifacts,
                    produced_artifacts=excluded.produced_artifacts,
                    entry_file_path=excluded.entry_file_path,
                    handler_name=excluded.handler_name,
                    status=excluded.status,
                    is_global=excluded.is_global,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    skill_id,
                    action_name,
                    version,
                    category,
                    act_desc,
                    params,
                    sys_reqs,
                    consumed,
                    produced,
                    resolved_entry_path,
                    handler_name,
                    initial_status,
                    is_global,
                ),
            )

            # -------------------------------------------------------------
            # STEP 2: route_registry (Binds action_trigger -> target_role)
            # -------------------------------------------------------------
            target_role = None
            if target_agent_id:
                cursor.execute(
                    "SELECT role_name FROM system_roles WHERE agent_id = ?",
                    (target_agent_id,)
                )
                role_row = cursor.fetchone()
                if role_row:
                    target_role = role_row[0]

            if not target_role:
                cursor.execute(
                    """
                    SELECT sr.role_name 
                    FROM system_roles sr
                    JOIN agent_skill_map asm ON sr.agent_id = asm.agent_id
                    WHERE asm.skill_id = ?
                    LIMIT 1
                    """,
                    (skill_id,),
                )
                role_row = cursor.fetchone()
                target_role = role_row[0] if role_row else "system_fallback"

            cursor.execute(
                """
                INSERT INTO route_registry (
                    action_trigger, target_role, fallback_role, route_type, is_active, description
                )
                VALUES (?, ?, 'system_fallback', 'DYNAMIC_AUTO', 1, ?)
                ON CONFLICT(action_trigger) DO UPDATE SET
                    target_role = excluded.target_role,
                    description = excluded.description,
                    is_active = 1
                """,
                (action_name, target_role, act_desc),
            )

        # -----------------------------------------------------------------
        # STEP 3: agent_skill_map (Maps agent_id <-> skill_id)
        # -----------------------------------------------------------------
        if target_agent_id:
            cursor.execute(
                """
                INSERT INTO agent_skill_map (agent_id, skill_id)
                SELECT agent_id, ? FROM agent_registry WHERE agent_id = ? AND is_active = 1
                ON CONFLICT(agent_id, skill_id) DO NOTHING
                """,
                (skill_id, target_agent_id),
            )
        elif is_global:
            cursor.execute(
                """
                INSERT INTO agent_skill_map (agent_id, skill_id)
                SELECT agent_id, ? FROM agent_registry WHERE is_active = 1
                ON CONFLICT(agent_id, skill_id) DO NOTHING
                """,
                (skill_id,),
            )
        else:
            # Explicitly bind specifically allowed agents
            for agent_id in allowed_agents:
                if agent_id and agent_id != "*":
                    cursor.execute(
                        """
                        INSERT INTO agent_skill_map (agent_id, skill_id)
                        SELECT agent_id, ? FROM agent_registry WHERE agent_id = ? AND is_active = 1
                        ON CONFLICT(agent_id, skill_id) DO NOTHING
                        """,
                        (skill_id, agent_id),
                    )

        conn.commit()
        logger.info(f"[SERVICE] Successfully registered skill '{skill_id}' in state DB.")


def unregister_skill(
    skill_id: str,
    db_path: Optional[Path] = None,
) -> None:
    """
    Safely unregisters a single skill from the database.

    ISOLATION GUARANTEE:
    - Scoped strictly to the provided `skill_id`.
    - Purges matching rows in `skill_registry` and `agent_skill_map`.
    - Removes corresponding `route_registry` triggers bound to this skill's actions.
    - NEVER wipes or alters unrelated skill or agent records.
    """
    if not skill_id:
        logger.warning("[SERVICE] Empty skill_id passed to unregister_skill. Aborting.")
        return

    db_file = db_path or STATE_DB_PATH
    if not db_file.exists():
        return

    with get_connection(db_file) as conn:
        cursor = conn.cursor()

        # Find action triggers associated with this skill to clean route_registry safely
        cursor.execute("SELECT action_name FROM skill_registry WHERE skill_id = ?", (skill_id,))
        action_rows = cursor.fetchall()
        action_triggers = [row[0] for row in action_rows if row[0]]

        # Delete from agent_skill_map (Scoped to skill_id)
        cursor.execute("DELETE FROM agent_skill_map WHERE skill_id = ?", (skill_id,))

        # Delete from skill_registry (Scoped to skill_id)
        cursor.execute("DELETE FROM skill_registry WHERE skill_id = ?", (skill_id,))

        # Delete from route_registry (Scoped to this skill's action triggers)
        for trigger in action_triggers:
            cursor.execute("DELETE FROM route_registry WHERE action_trigger = ?", (trigger,))

        conn.commit()
        logger.info(f"[SERVICE] Safely unregistered skill_id='{skill_id}' from database.")
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/tui/__init__.py`

```python
"""
charon/cli/librarian/tui/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Package entrypoint for the Charon Librarian Interactive Terminal User Interface.
"""

from charon.cli.librarian.tui.app import LibrarianTUI

__all__ = ["LibrarianTUI"]
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/tui/app.py`

```python
"""
charon/cli/librarian/tui/app.py
System Version: v0.1.0 | File Revision: 1.5.0

Module: LibrarianTUI application orchestrator and main menu navigation loop.
Refactored to support interactive ingestion name resolution, staged folder sanitization,
and automatic pre-run synchronization.
"""

from pathlib import Path
import sys
from typing import List

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax

from charon.cli.database import run_sync
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
                    "* **Interactive Resolution**: User is prompted to confirm or customize the `skill_id` slug upon import.\n"
                    "* **Standalone `.py` File**: Copied as `plugin.py` into `skills/staged/<skill_id>/`; boilerplate `manifest.json` generated from template.\n"
                    "* **Directory without Manifest**: Copied to staged area, entrypoint normalized to `plugin.py`, and `manifest.json` generated from template.\n"
                    "* **Staged Sanitization**: Pre-existing folders in `staged/` are auto-slugified and synced during DB maintenance checks.\n\n"
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

                # run_ingest handles interactive naming, collision detection, and user confirmation
                run_ingest(source_path=source_path)
                Prompt.ask("\nPress Enter to return")

    def start(self):
        # Enforce initial DB sync and staged folder sanitization on startup
        run_sync()

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
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/tui/diagnostics.py`

```python
"""
charon/cli/librarian/tui/diagnostics.py
System Version: v0.1.0 | File Revision: 1.5.0

Module: Diagnostic health audits, dependency resolutions, and registry maintenance interface.
"""

import subprocess
import sys
from typing import Dict, List

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from charon.cli.database import run_audit, run_sync
from charon.cli.librarian.purge_gaps import purge_resolved_gaps
from charon.cli.librarian.tui.discovery import discover_skills, get_resolved_gaps_count
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


def run_diagnostics_suite(librarian: SkillLibrarian):
    """Main interactive entry point for Option [3]: Diagnostics & Maintenance."""
    while True:
        skills = discover_skills()
        broken_skills = [s for s in skills if s.get("missing_requirements")]
        # Updated: Check relational RBAC bindings rather than legacy shelf_tags
        unassigned_skills = [s for s in skills if not s.get("authorized_agents")]
        resolved_gaps = get_resolved_gaps_count()

        console.clear()

        grid = Table.grid(expand=True)
        grid.add_column(justify="left")
        grid.add_column(justify="left")

        grid.add_row(
            f"• Total Skills Audited: [bold white]{len(skills)}[/bold white]",
            f"• Broken Binary Dependencies: [{'bold red' if broken_skills else 'dim green'}]{len(broken_skills)}[/{'bold red' if broken_skills else 'dim green'}]",
        )

        db_status = "NEEDS PURGE" if resolved_gaps > 0 else "OK"
        db_color = "bold yellow" if resolved_gaps > 0 else "bold green"

        grid.add_row(
            f"• Unassigned Skills: [{'bold yellow' if unassigned_skills else 'dim green'}]{len(unassigned_skills)}[/{'bold yellow' if unassigned_skills else 'dim green'}]",
            f"• Database Registry: [{db_color}]{db_status}[/{db_color}]",
        )

        elements = [
            "[bold cyan]🛠️  CHARON LIBRARIAN DIAGNOSTICS & MAINTENANCE SUITE[/bold cyan]",
            "[dim]System Health Audit & Automated Repair Center[/dim]\n",
            grid,
        ]

        if resolved_gaps > 0:
            elements.append(
                f"\n[bold yellow]🧹 MAINTENANCE REQUIRED:[/bold yellow] "
                f"[yellow]{resolved_gaps} resolved gap record(s) pending DB purge & vacuum. Select [4] to audit and purge.[/yellow]"
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
        console.print("  [B] Back to Main Menu")
        console.print("  [Q] Exit Librarian TUI\n")

        choices = ["1", "2", "3", "4", "b", "B", "q", "Q"]
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
            run_sync()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()
            console.print("[bold green]✓ Re-index and synchronization complete.[/bold green]")
            Prompt.ask("\nPress Enter to continue")
        elif choice == "4":
            console.clear()
            console.print("[bold cyan]📋 SQLite vs Filesystem State Drift Audit[/bold cyan]\n")
            run_audit()

            if resolved_gaps > 0:
                console.print(
                    f"\n[bold yellow]⚠️ Drift Detected: {resolved_gaps} resolved gap(s) pending purge.[/bold yellow]")
                confirm = Prompt.ask("Purge resolved gaps and vacuum database?", choices=["y", "n"], default="y")
                if confirm.lower() == "y":
                    purged = purge_resolved_gaps()
                    console.print(f"[bold green]✓ Purged {purged} record(s).[/bold green]")
            Prompt.ask("\nPress Enter to continue")


def audit_report(skills: List[Dict]):
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
                s["skill_id"],
                s["stage"],
                status,
                ", ".join(missing),
                ", ".join(packages),
            )
        else:
            table.add_row(
                s["skill_id"],
                s["stage"],
                "[bold green]HEALTHY[/bold green]",
                "[dim]None[/dim]",
                "[dim]N/A[/dim]",
            )

    console.print(table)
    Prompt.ask("\nPress Enter to return to Diagnostics Menu")


def resolve_all_dependencies(broken_skills: List[Dict]):
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
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/tui/discovery.py`

```python
"""
charon/cli/librarian/tui/discovery.py
System Version: v0.1.0 | File Revision: 2.3.1

Module: V3-aligned skill discovery, manifest parsing, database permission queries,
agent default skill bindings, and decoupled dual-pathway integrity auditing.
"""

import importlib.util
import json
import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.core.skills import SkillLibrarian
from charon.db.connection import get_connection

logger = logging.getLogger("charon.cli.librarian.tui.discovery")

PYPI_TO_MODULE_MAP = {
    "beautifulsoup4": "bs4",
    "paho-mqtt": "paho",
    "python-dateutil": "dateutil",
    "pyyaml": "yaml",
    "pillow": "PIL",
    "opencv-python": "cv2",
    "scikit-learn": "sklearn",
}


def is_requirement_installed(req: str) -> bool:
    """Checks if a requirement exists as an OS binary on $PATH or an importable Python module."""
    if shutil.which(req):
        return True

    cleaned_req = req.strip().lower()
    module_name = PYPI_TO_MODULE_MAP.get(cleaned_req, cleaned_req)

    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def get_active_db_agent_ids() -> Set[str]:
    """Queries active agent_ids from agent_registry in charon_state.db."""
    if not STATE_DB_PATH.exists():
        return set()
    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT agent_id FROM agent_registry WHERE is_active = 1")
            return {row[0] for row in cursor.fetchall()}
    except Exception as e:
        logger.debug(f"Failed to query active agents from state DB: {e}")
        return set()


def resolve_skill_contract(
    cursor: sqlite3.Cursor, identifier: str
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolves any identifier (folder name, manifest ID, DB skill_id, or action_name)
    against skill_registry. Returns (action_name, skill_id).
    """
    if not identifier:
        return (None, None)

    norm_id = identifier.replace("sk_", "").strip()

    # 1. Exact match against action_name or skill_id variants
    cursor.execute(
        """
        SELECT action_name, skill_id FROM skill_registry 
        WHERE action_name = ? OR skill_id = ? OR skill_id = ? OR action_name = ?
        """,
        (identifier, identifier, f"sk_{norm_id}", norm_id),
    )
    row = cursor.fetchone()
    if row:
        return (row[0] or row[1], row[1])

    # 2. Path-based resolution (handles Unix '/' and Windows '\' path separators)
    cursor.execute(
        """
        SELECT action_name, skill_id FROM skill_registry 
        WHERE entry_file_path LIKE ? OR entry_file_path LIKE ?
           OR entry_file_path LIKE ? OR entry_file_path LIKE ?
        """,
        (f"%/{identifier}/%", f"%/{norm_id}/%", f"%\\{identifier}\\%", f"%\\{norm_id}\\%"),
    )
    row = cursor.fetchone()
    if row:
        return (row[0] or row[1], row[1])

    return (None, None)


def get_skill_permissions() -> Dict[str, Set[str]]:
    """Queries DB agent_skill_map to map authorized agent_ids to skill_ids and action_names."""
    skill_map: Dict[str, Set[str]] = {}

    if not STATE_DB_PATH.exists():
        return skill_map

    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT asm.skill_id, asm.agent_id, sr.action_name
                FROM agent_skill_map asm
                LEFT JOIN skill_registry sr ON (asm.skill_id = sr.skill_id OR asm.skill_id = sr.action_name)
                """
            )
            for db_skill_id, agent_id, action_name in cursor.fetchall():
                if db_skill_id:
                    skill_map.setdefault(db_skill_id, set()).add(agent_id)
                    norm_id = db_skill_id.lower().replace("sk_", "")
                    skill_map.setdefault(norm_id, set()).add(agent_id)
                if action_name:
                    skill_map.setdefault(action_name, set()).add(agent_id)
    except Exception as e:
        logger.debug(f"Failed to query permissions from agent_skill_map: {e}")

    return skill_map


def get_skill_defaults() -> Dict[str, Set[str]]:
    """Queries state DB to map skill_ids and action_names to agent_ids using them as default actions."""
    default_map: Dict[str, Set[str]] = {}

    if not STATE_DB_PATH.exists():
        return default_map

    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.skill_id, s.action_name, a.agent_id, a.default_action
                FROM agent_registry a
                LEFT JOIN skill_registry s ON (a.default_action = s.action_name OR a.default_action = s.skill_id)
                WHERE a.is_active = 1 AND a.default_action IS NOT NULL
                """
            )
            for db_skill_id, action_name, agent_id, default_action in cursor.fetchall():
                if db_skill_id:
                    default_map.setdefault(db_skill_id, set()).add(agent_id)
                    norm_id = db_skill_id.lower().replace("sk_", "")
                    default_map.setdefault(norm_id, set()).add(agent_id)
                if action_name:
                    default_map.setdefault(action_name, set()).add(agent_id)
                if default_action:
                    default_map.setdefault(default_action, set()).add(agent_id)
    except Exception as e:
        logger.debug(f"Failed to query default action mappings: {e}")

    return default_map


def grant_agent_permission(agent_id: str, skill_id: str) -> None:
    """Grants an agent permission for a skill in agent_skill_map using registry resolution."""
    if not STATE_DB_PATH.exists() or not skill_id:
        return
    try:
        with get_connection(STATE_DB_PATH) as conn:
            cursor = conn.cursor()
            _, target_sk_id = resolve_skill_contract(cursor, skill_id)
            if not target_sk_id:
                target_sk_id = skill_id

            # Validate skill existence in skill_registry to prevent foreign key violations
            cursor.execute("SELECT 1 FROM skill_registry WHERE skill_id = ?", (target_sk_id,))
            if not cursor.fetchone():
                logger.warning(
                    f"Cannot grant permission: skill '{target_sk_id}' is not yet indexed in skill_registry."
                )
                return

            cursor.execute(
                """
                INSERT INTO agent_skill_map (agent_id, skill_id) 
                VALUES (?, ?)
                ON CONFLICT(agent_id, skill_id) DO NOTHING
                """,
                (agent_id, target_sk_id),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to grant agent permission: {e}")


def revoke_agent_permission(agent_id: str, skill_id: str) -> None:
    """Revokes an agent's permission for a skill in agent_skill_map."""
    if not STATE_DB_PATH.exists() or not skill_id:
        return
    try:
        with get_connection(STATE_DB_PATH) as conn:
            cursor = conn.cursor()
            _, matched_skill_id = resolve_skill_contract(cursor, skill_id)
            norm_id = skill_id.replace("sk_", "")

            cursor.execute(
                """
                DELETE FROM agent_skill_map 
                WHERE agent_id = ? AND (skill_id = ? OR skill_id = ? OR skill_id = ?)
                """,
                (agent_id, skill_id, matched_skill_id or "", f"sk_{norm_id}"),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to revoke agent permission: {e}")


def set_agent_default_skill(agent_id: str, skill_id: str) -> bool:
    """
    Binds a skill as default_action target for an agent in Schema V3.
    Resolves through skill_registry first. Fails if unresolvable.
    """
    if not STATE_DB_PATH.exists() or not agent_id or not skill_id:
        return False
    try:
        with get_connection(STATE_DB_PATH) as conn:
            cursor = conn.cursor()

            action_name, matched_skill_id = resolve_skill_contract(cursor, skill_id)

            if not action_name or not matched_skill_id:
                logger.error(
                    f"Refusing default assignment: '{skill_id}' cannot be resolved in skill_registry."
                )
                return False

            # 1. Update agent_registry default_action contract
            cursor.execute(
                """
                UPDATE agent_registry
                SET default_action = ?, updated_at = CURRENT_TIMESTAMP
                WHERE agent_id = ?
                """,
                (action_name, agent_id),
            )

            # 2. Ensure agent_skill_map link exists
            cursor.execute(
                """
                INSERT INTO agent_skill_map (agent_id, skill_id)
                VALUES (?, ?)
                ON CONFLICT(agent_id, skill_id) DO NOTHING
                """,
                (agent_id, matched_skill_id),
            )

            # 3. Update is_default state in agent_skill_map if column exists
            try:
                cursor.execute(
                    "UPDATE agent_skill_map SET is_default = 0 WHERE agent_id = ?",
                    (agent_id,),
                )
                cursor.execute(
                    """
                    UPDATE agent_skill_map SET is_default = 1 
                    WHERE agent_id = ? AND (skill_id = ? OR skill_id = ?)
                    """,
                    (agent_id, skill_id, matched_skill_id),
                )
            except sqlite3.OperationalError:
                pass

            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to set default skill for agent '{agent_id}': {e}")
        return False


def discover_skills() -> List[Dict[str, Any]]:
    """Scans search roots and returns enriched skill records validated against DB permissions."""
    skill_permissions = get_skill_permissions()
    skill_defaults = get_skill_defaults()
    skills_by_id: Dict[str, Dict[str, Any]] = {}

    roots = [
        ("Staged", PKG_STAGED_SKILLS_DIR),
        ("Dynamic", PKG_DYNAMIC_SKILLS_DIR),
        ("Dynamic", DYNAMIC_SKILLS_DIR),
    ]

    for stage, root in roots:
        if not root.exists():
            continue
        for manifest_path in root.rglob("manifest.json"):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                folder_name = manifest_path.parent.name
                skill_id = data.get("skill_id", folder_name)
                norm_id = skill_id.lower().replace("sk_", "")
                sk_id = f"sk_{norm_id}"

                sys_reqs = data.get("system_requirements", [])
                missing_reqs = [req for req in sys_reqs if not is_requirement_installed(req)]

                actions = data.get("supported_actions", {})
                action_keys = list(actions.keys()) if isinstance(actions, dict) else [str(a) for a in actions]

                category = data.get("category")
                if not category or category == "General":
                    if any("kicad" in a or "cad" in a for a in action_keys):
                        category = "Hardware & EDA"
                    elif any("pdf" in a or "ocr" in a or "chunk" in a for a in action_keys):
                        category = "Document Processing"
                    elif any("vector" in a or "prune" in a for a in action_keys):
                        category = "Data & Embeddings"
                    else:
                        category = "General / Utility"

                auth_set = (
                    skill_permissions.get(skill_id, set())
                    | skill_permissions.get(norm_id, set())
                    | skill_permissions.get(sk_id, set())
                    | skill_permissions.get(folder_name, set())
                )
                for act in action_keys:
                    auth_set |= skill_permissions.get(act, set())

                authorized_agents = sorted(list(auth_set))

                def_set = (
                    skill_defaults.get(skill_id, set())
                    | skill_defaults.get(norm_id, set())
                    | skill_defaults.get(sk_id, set())
                    | skill_defaults.get(folder_name, set())
                )
                for act in action_keys:
                    def_set |= skill_defaults.get(act, set())

                default_for_agents = sorted(list(def_set))

                skills_by_id[skill_id] = {
                    "skill_id": skill_id,
                    "version": data.get("version", "1.0.0"),
                    "description": data.get("description", "No description provided."),
                    "folder_name": folder_name,
                    "manifest_path": manifest_path,
                    "stage": data.get("stage", stage),
                    "category": category,
                    "authorized_agents": authorized_agents,
                    "default_for_agents": default_for_agents,
                    "system_requirements": sys_reqs,
                    "missing_requirements": missing_reqs,
                    "supported_actions": actions,
                    "health_status": "HEALTHY" if not missing_reqs else "MISSING_PREREQ",
                }
            except Exception as e:
                logger.warning(f"Failed to load or parse skill manifest at {manifest_path}: {e}")
                continue

    return list(skills_by_id.values())


# ============================================================================
# DECOUPLED DUAL-PATHWAY AUDITING
# ============================================================================

def audit_agent_skill_integrity() -> Dict[str, Any]:
    """
    PATHWAY 1: Database Integrity Audit.
    Validates that active agents have valid default_action targets in skill_registry
    and corresponding authorization entries in agent_skill_map.
    """
    audit_report: Dict[str, Any] = {
        "is_clean": True,
        "orphan_default_actions": [],
        "missing_permission_links": [],
        "active_agents_checked": 0,
    }

    if not STATE_DB_PATH.exists():
        return audit_report

    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT 
                    a.agent_id,
                    a.default_action,
                    s.skill_id AS skill_in_registry,
                    asm.skill_id AS linked_in_map
                FROM agent_registry a
                LEFT JOIN skill_registry s ON (a.default_action = s.action_name OR a.default_action = s.skill_id)
                LEFT JOIN agent_skill_map asm ON a.agent_id = asm.agent_id AND s.skill_id = asm.skill_id
                WHERE a.is_active = 1
                """
            )
            rows = cursor.fetchall()
            audit_report["active_agents_checked"] = len(rows)

            for agent_id, default_action, skill_in_registry, linked_in_map in rows:
                if default_action and not skill_in_registry:
                    audit_report["is_clean"] = False
                    audit_report["orphan_default_actions"].append(
                        {"agent_id": agent_id, "default_action": default_action}
                    )
                elif skill_in_registry and not linked_in_map:
                    audit_report["is_clean"] = False
                    audit_report["missing_permission_links"].append(
                        {"agent_id": agent_id, "skill_id": skill_in_registry, "default_action": default_action}
                    )

    except Exception as e:
        logger.error(f"Failed to execute database agent-skill integrity audit: {e}")

    return audit_report


def audit_filesystem_manifest_health() -> Dict[str, Any]:
    """
    PATHWAY 2: Filesystem Health Audit.
    Scans physical disk roots, verifying manifest validation, plugin entrypoints,
    and matching entries in skill_registry.
    """
    audit_report: Dict[str, Any] = {
        "is_healthy": True,
        "unregistered_disk_skills": [],
        "missing_plugin_files": [],
        "corrupt_manifests": [],
    }

    if not STATE_DB_PATH.exists():
        return audit_report

    registered_paths: Set[str] = set()
    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT entry_file_path FROM skill_registry")
            registered_paths = {
                str(Path(row[0]).resolve()) for row in cursor.fetchall() if row[0]
            }
    except Exception as e:
        logger.error(f"Failed to query skill_registry paths: {e}")

    roots = [PKG_STAGED_SKILLS_DIR, PKG_DYNAMIC_SKILLS_DIR, DYNAMIC_SKILLS_DIR]

    for root in roots:
        if not root.exists():
            continue
        for manifest_path in root.rglob("manifest.json"):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                plugin_path = manifest_path.parent / "plugin.py"
                if not plugin_path.exists():
                    audit_report["is_healthy"] = False
                    audit_report["missing_plugin_files"].append(str(manifest_path.parent))

                str_plugin_path = str(plugin_path.resolve())
                if registered_paths and str_plugin_path not in registered_paths:
                    audit_report["is_healthy"] = False
                    audit_report["unregistered_disk_skills"].append(
                        {"folder": manifest_path.parent.name, "path": str(manifest_path)}
                    )

            except Exception as e:
                audit_report["is_healthy"] = False
                audit_report["corrupt_manifests"].append({"path": str(manifest_path), "error": str(e)})

    return audit_report


def get_open_gaps_count() -> int:
    """Queries count of open skill gaps in charon_state.db."""
    if not STATE_DB_PATH.exists():
        return 0
    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM skill_gaps WHERE status = 'open'")
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.debug(f"Failed to query open gaps count: {e}")
        return 0


def get_resolved_gaps_count() -> int:
    """Queries count of resolved skill gaps pending database purge."""
    if not STATE_DB_PATH.exists():
        return 0
    try:
        with get_connection(STATE_DB_PATH, read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM skill_gaps WHERE status = 'resolved'")
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.debug(f"Failed to query resolved gaps count: {e}")
        return 0


def save_manifest(skill: Dict[str, Any], librarian: SkillLibrarian) -> None:
    """Saves non-permission manifest changes to disk and triggers librarian re-indexing."""
    manifest_path = skill["manifest_path"]
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["category"] = skill["category"]
    data["version"] = skill.get("version", "1.0.0")
    data["description"] = skill.get("description", "")

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    librarian.reindex_skills()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian/tui/views.py`

```python
"""
charon/cli/librarian/tui/views.py
System Version: v0.1.0 | File Revision: 2.2.0

Module: Rich visual rendering components, main menu header, and interactive catalog/inspector views.
Includes automatic sync hooks before rendering to guarantee staged folder sanitization.
"""

import json
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from charon.cli.database import run_sync
from charon.cli.librarian.ingestion import run_edit
from charon.cli.librarian.lifecycle import (
    run_delete_skill,
    run_demote,
    run_promote,
    run_rename,
)
from charon.cli.librarian.tui.diagnostics import PACKAGE_MAP
from charon.cli.librarian.tui.discovery import (
    discover_skills,
    get_open_gaps_count,
    get_resolved_gaps_count,
    grant_agent_permission,
    revoke_agent_permission,
    set_agent_default_skill,
)
from charon.core.skills import SkillLibrarian

console = Console()


def render_header(skill_count: int, agent_count: int, broken_deps_count: Optional[int] = None):
    """
    Renders the main control panel header using a borderless 2x2 Rich grid layout
    with integrated database maintenance status notifications.
    """
    if broken_deps_count is None:
        skills = discover_skills()
        broken_deps_count = sum(1 for s in skills if s.get("missing_requirements"))
        skill_count = len(skills)

    open_gaps = get_open_gaps_count()
    resolved_gaps = get_resolved_gaps_count()

    gap_color = "bold red" if open_gaps > 0 else "dim green"
    broken_color = "bold red" if broken_deps_count > 0 else "dim green"

    console.clear()

    grid = Table.grid(expand=True)
    grid.add_column(justify="left")
    grid.add_column(justify="left")

    grid.add_row(
        f"• Registered System Agents: [bold white]{agent_count}[/bold white]",
        f"• Total Skills Index: [bold white]{skill_count}[/bold white]",
    )
    grid.add_row(
        f"• Open Skill Gaps: [{gap_color}]{open_gaps}[/{gap_color}]",
        f"• Broken Dependencies: [{broken_color}]{broken_deps_count}[/{broken_color}]",
    )

    elements = [
        "[bold cyan]🏛️  CHARON SKILL LIBRARIAN CONTROL PANEL[/bold cyan]",
        "[dim]Interactive Governance & Permission Navigator[/dim]\n",
        grid,
    ]

    if resolved_gaps > 0:
        elements.append(
            f"\n[bold yellow]🧹 MAINTENANCE REQUIRED:[/bold yellow] "
            f"[yellow]{resolved_gaps} resolved gap record(s) pending DB purge & vacuum. Select [3] Diagnostics Suite from Main Menu.[/yellow]"
        )

    header_content = Group(*elements)
    console.print(Panel(header_content, border_style="cyan", padding=(0, 2), expand=True))


def display_skill_table(skills: List[Dict[str, Any]], title: str):
    """Renders a structured data table of skills with color-coded requirement statuses and DB agent permissions."""
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Skill ID", style="bold white")
    table.add_column("Category", style="cyan")
    table.add_column("Stage", style="blue")
    table.add_column("Authorized Agents", style="green")
    table.add_column("Actions", style="magenta")
    table.add_column("Prerequisites", style="yellow")

    for idx, s in enumerate(skills, start=1):
        auth_list = []
        default_for = s.get("default_for_agents", [])

        for agent in s.get("authorized_agents", []):
            if agent in default_for:
                auth_list.append(f"[bold yellow]⭐ {agent}[/bold yellow]")
            else:
                auth_list.append(agent)

        auth_str = ", ".join(auth_list) if auth_list else "[bold red]Unassigned[/bold red]"

        actions = s.get("supported_actions", {})
        if isinstance(actions, dict):
            actions_list = list(actions.keys())
        elif isinstance(actions, list):
            actions_list = [str(a) for a in actions]
        else:
            actions_list = []
        actions_str = ", ".join(actions_list) if actions_list else "[dim]None[/dim]"

        reqs = []
        for r in s.get("system_requirements", []):
            if r in s.get("missing_requirements", []):
                reqs.append(f"[bold red]❌ {r}[/bold red]")
            else:
                reqs.append(f"[bold green]✓ {r}[/bold green]")
        reqs_str = ", ".join(reqs) if reqs else "[dim]None[/dim]"

        table.add_row(str(idx), s["skill_id"], s["category"], s["stage"], auth_str, actions_str, reqs_str)

    console.print(table)


def view_catalog(agents: List[str], librarian: SkillLibrarian, initial_filter: Optional[str] = None):
    """Displays interactive catalog navigation menu and handles filtered views."""
    while True:
        run_sync()  # Ensure staged directories and DB mappings are aligned before discovery
        skills = discover_skills()
        broken_deps_count = sum(1 for s in skills if s.get("missing_requirements"))
        render_header(len(skills), len(agents), broken_deps_count)

        if initial_filter == "agent":
            choice = "3"
            initial_filter = None
        else:
            console.print("\n[bold]Catalog Navigation Filters:[/bold]")
            console.print("  [1] Show All Skills")
            console.print("  [2] Filter by Category")
            console.print("  [3] Filter by Agent Permission")
            console.print("  [4] Show Unassigned Skills")
            console.print("  [B] Back to Main Menu")
            console.print("  [Q] Exit Librarian TUI\n")

            choice = Prompt.ask("Select view", choices=["1", "2", "3", "4", "b", "B", "q", "Q"], default="1")

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
                s for s in skills if
                target_agent in s.get("authorized_agents", []) or "*" in s.get("authorized_agents", [])
            ]
            title = f"Skills Authorized for: {target_agent}"

        elif choice == "4":
            filtered = [s for s in skills if not s.get("authorized_agents")]
            title = "Unassigned Skills (No Agent Permissions in DB)"

        elif choice.lower() == "b":
            break

        inspect_skill_list(filtered, title, agents, librarian)


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
        reqs = []
        for r in skill.get("system_requirements", []):
            if r in skill.get("missing_requirements", []):
                reqs.append(f"[bold red]► ❌ {r} (MISSING ON OS PATH)[/bold red]")
            else:
                reqs.append(f"[bold green]✓ {r} (INSTALLED)[/bold green]")

        urgent_banner = ""
        if skill.get("missing_requirements"):
            urgent_banner = "\n[bold red]⚠️  URGENT: Skill is broken due to missing OS dependencies! Press [R] to resolve.[/bold red]\n"

        auth_agents = skill.get("authorized_agents", [])
        default_for = skill.get("default_for_agents", [])

        auth_display = []
        for a in auth_agents:
            if a in default_for:
                auth_display.append(f"[bold yellow]⭐ {a} (DEFAULT)[/bold yellow]")
            else:
                auth_display.append(a)

        card = (
            f"[bold cyan]Skill ID:[/bold cyan] {skill['skill_id']} [dim](v{skill.get('version', '1.0.0')})[/dim]\n"
            f"[bold cyan]Description:[/bold cyan] [italic]{skill.get('description', 'No description provided.')}[/italic]\n"
            f"[bold cyan]Category:[/bold cyan] {skill['category']} | "
            f"[bold cyan]Stage:[/bold cyan] {skill['stage']}\n"
            f"[bold cyan]Manifest Path:[/bold cyan] {skill['manifest_path']}\n\n"
            f"[bold green]Authorized Agents (DB):[/bold green] {', '.join(auth_display) or 'None'}\n"
            f"[bold yellow]System Binaries:[/bold yellow] {', '.join(reqs) or 'None'}\n"
            f"[bold magenta]Actions Handled:[/bold magenta] {json.dumps(skill.get('supported_actions', {}))}\n"
            f"{urgent_banner}"
        )

        console.print(
            Panel(card, title=f"Inspector: {skill['skill_id']}", border_style="blue", padding=(0, 2), expand=True))
        console.print("[bold]Operations:[/bold]")
        console.print("  [1] Grant Agent Permission (SQLite)")
        console.print("  [2] Revoke Agent Permission (SQLite)")
        console.print("  [3] Set as Default Skill for Agent (SQLite)")

        stage_choice_key = "4"
        if skill["stage"] == "Staged":
            console.print(f"  [{stage_choice_key}] Promote Staged Skill to Production Dynamic")
        elif skill["stage"] in ("Dynamic", "User Dynamic"):
            console.print(f"  [{stage_choice_key}] Demote Skill to Staged (Quarantine)")

        console.print("  [E] Edit Manifest in $EDITOR")
        console.print("  [N] Rename Skill ID")

        if skill.get("missing_requirements"):
            console.print("  [bold red][R] ⚠️  Resolve Missing System Binaries (apt install)[/bold red]")

        console.print("  [D] Delete Skill from System")
        console.print("  [B] Back")
        console.print("  [Q] Exit Librarian TUI\n")

        choices = ["1", "2", "3", "4", "e", "E", "n", "N", "d", "D", "b", "B", "q", "Q"]

        if skill.get("missing_requirements"):
            choices.extend(["r", "R"])

        op = Prompt.ask("Select operation", choices=choices, default="B")

        if op.lower() == "q":
            console.print("[bold cyan]Librarian session closed.[/bold cyan]")
            sys.exit(0)

        elif op.lower() == "e":
            run_edit(skill["skill_id"])
            run_sync()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()
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
            sel = (
                    int(Prompt.ask("Agent", choices=[str(i) for i in range(1, len(available_to_grant) + 1)])) - 1
            )
            target_agent = available_to_grant[sel]

            grant_agent_permission(target_agent, skill["skill_id"])
            run_sync()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()

            skill.setdefault("authorized_agents", []).append(target_agent)
            skill["authorized_agents"].sort()
            console.print(
                f"[bold green]✓ Granted {target_agent} access to skill '{skill['skill_id']}' in SQLite DB[/bold green]")
            Prompt.ask("Press Enter to refresh")

        elif op == "2":
            if not auth_agents:
                console.print("[yellow]No agents currently granted access in agent_skill_map.[/yellow]")
                Prompt.ask("Press Enter to continue")
                continue
            console.print("\n[bold]Select Agent to Revoke Permission:[/bold]")
            for idx, a in enumerate(auth_agents, start=1):
                console.print(f"  [{idx}] {a}")
            sel = int(Prompt.ask("Agent", choices=[str(i) for i in range(1, len(auth_agents) + 1)])) - 1
            target_agent = auth_agents[sel]

            revoke_agent_permission(target_agent, skill["skill_id"])
            run_sync()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()

            skill["authorized_agents"].remove(target_agent)
            if target_agent in default_for:
                default_for.remove(target_agent)

            console.print(
                f"[bold green]✓ Revoked {target_agent} access to skill '{skill['skill_id']}' in SQLite DB[/bold green]")
            Prompt.ask("Press Enter to refresh")

        elif op == "3":
            if not auth_agents:
                console.print(
                    "[yellow]No agents are currently authorized for this skill. Grant permission first.[/yellow]")
                Prompt.ask("Press Enter to continue")
                continue

            console.print("\n[bold]Select Agent to Set Default Skill Target:[/bold]")
            for idx, a in enumerate(auth_agents, start=1):
                is_curr_default = " (Already Default)" if a in default_for else ""
                console.print(f"  [{idx}] {a}{is_curr_default}")

            sel = int(Prompt.ask("Agent", choices=[str(i) for i in range(1, len(auth_agents) + 1)])) - 1
            target_agent = auth_agents[sel]

            set_agent_default_skill(target_agent, skill["skill_id"])
            run_sync()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()

            if "default_for_agents" not in skill:
                skill["default_for_agents"] = []
            if target_agent not in skill["default_for_agents"]:
                skill["default_for_agents"].append(target_agent)

            was_modified = True
            console.print(
                f"[bold green]✓ Set '{skill['skill_id']}' as default skill for agent '{target_agent}' in SQLite DB[/bold green]")
            Prompt.ask("Press Enter to refresh")

        elif op == "4":
            if skill["stage"] == "Staged":
                run_promote(skill["skill_id"])
            elif skill["stage"] in ("Dynamic", "User Dynamic"):
                run_demote(skill["skill_id"])

            run_sync()
            if hasattr(librarian, "reindex_skills"):
                librarian.reindex_skills()
            was_modified = True
            Prompt.ask("Press Enter to continue")
            break

        elif op.lower() == "n":
            new_id = Prompt.ask("\n[bold cyan]Enter new skill_id[/bold cyan]").strip()
            if new_id and new_id != skill["skill_id"]:
                run_rename(skill["skill_id"], new_id)
                run_sync()
                if hasattr(librarian, "reindex_skills"):
                    librarian.reindex_skills()
                skill["skill_id"] = new_id
                was_modified = True
                Prompt.ask("Press Enter to continue")
                break

        elif op.lower() == "r":
            apt_pkgs = [PACKAGE_MAP.get(req, req) for req in skill.get("missing_requirements", [])]
            missing_str = " ".join(apt_pkgs)
            cmd = f"sudo apt-get update && sudo apt-get install -y {missing_str}"
            console.print(f"\n[bold yellow]Executing System Resolver Command:[/bold yellow]\n  {cmd}\n")
            confirm = Prompt.ask("Run command with elevated privileges?", choices=["y", "n"], default="y")

            if confirm.lower() == "y":
                subprocess.run(cmd, shell=True)
                skill["missing_requirements"] = [
                    req for req in skill.get("system_requirements", []) if not shutil.which(req)
                ]
                skill["health_status"] = "HEALTHY" if not skill["missing_requirements"] else "MISSING_PREREQ"
                was_modified = True
                Prompt.ask("\nPress Enter to refresh health status")

        elif op.lower() == "d":
            confirm = Prompt.ask(
                f"\n[bold red]⚠️ PERMANENT DELETE:[/bold red] Are you sure you want to purge '[bold white]{skill['skill_id']}[/bold white]'?",
                choices=["y", "n"],
                default="n",
            )
            if confirm.lower() == "y":
                run_delete_skill(skill["skill_id"])
                run_sync()
                if hasattr(librarian, "reindex_skills"):
                    librarian.reindex_skills()
                was_modified = True
                Prompt.ask("Press Enter to return to catalog")
                break

        elif op.lower() == "b":
            break

    return was_modified
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian.py`

```python

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/librarian_tui.py`

```python

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/main.py`

```python
"""
charon/cli/main.py
System Version: v0.1.0 | File Revision: 1.7.0

Module: CLI entrypoint and interactive shell loop execution.
Includes direct launcher support for real-time TelemetryBus trace monitoring,
Skill Librarian permission & registry management, and Human-in-the-Loop Skill Forge.
"""

import argparse
import asyncio
import os
import sys
from typing import List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from rich.panel import Panel

from charon.cli.client import CharonClient
from charon.cli.interactive import prompt_concierge_choice
from charon.cli.ui import console
from charon.config import CHARON_API_KEY

DEFAULT_HOST = os.getenv("CHARON_HOST", "http://localhost:8000")
DEFAULT_API_KEY = CHARON_API_KEY

HELP_EPILOG = """
Charon Tool Suite Subcommands:
  charon librarian [list|sync|check|grant|revoke|promote|demote|delete]
                             Manage skill permissions, manifest validation, DB indexing,
                             and staging/quarantine workflows. Omit subcommands to launch
                             the interactive TUI Control Panel.
  charon forge [list|resolve|interactive]
                             Inspect skill gaps logged by agents and forge skill scaffolds.
  charon telemetry            Launch live Rich terminal telemetry trace monitor.

Examples:
  charon librarian
  charon librarian list
  charon librarian grant extract_pdf_ocr_skill The_Archivist
  charon librarian promote hallucinated_vector_pruning_action_skill
  charon forge resolve --gap-id 1 --action custom_action --agent The_Engineer
  charon "Check battery level on workspace robot" -n
"""


async def async_main() -> None:
    """Main async entrypoint for the Charon CLI client."""

    # -------------------------------------------------------------------------
    # Direct Subcommand Intercepts (Bypasses top-level argparse flag stealing)
    # -------------------------------------------------------------------------
    if len(sys.argv) > 1:
        subcmd = sys.argv[1].lower()

        # 1. Skill Librarian Intercept
        if subcmd in ("librarian", "skills"):
            lib_args = sys.argv[2:]
            try:
                from charon.cli.librarian import main as run_librarian
                res = run_librarian(lib_args)
                sys.exit(res if isinstance(res, int) else 0)
            except Exception as exc:
                console.print(f"[bold red]Librarian Error:[/bold red] {exc}")
                sys.exit(1)

        # 2. Skill Forge Intercept
        if subcmd in ("forge", "skill-forge", "skill_forge"):
            forge_args = sys.argv[2:]
            try:
                try:
                    from charon.skill_forge_cli import async_main as run_skill_forge
                except ImportError:
                    from charon.skill_forge_cli import main as run_skill_forge

                if asyncio.iscoroutinefunction(run_skill_forge):
                    res = await run_skill_forge(forge_args)
                else:
                    res = run_skill_forge(forge_args)
                sys.exit(res if isinstance(res, int) else 0)
            except Exception as exc:
                console.print(f"[bold red]Skill Forge Error:[/bold red] {exc}")
                sys.exit(1)

        # 3. Telemetry Viewer Intercept
        if subcmd == "telemetry":
            try:
                try:
                    from charon.telemetry.viewer import async_main as run_telemetry_viewer
                except ImportError:
                    from charon.telemetry.viewer import main as run_telemetry_viewer

                if asyncio.iscoroutinefunction(run_telemetry_viewer):
                    await run_telemetry_viewer()
                else:
                    run_telemetry_viewer()
                sys.exit(0)
            except Exception as exc:
                console.print(f"[bold red]Telemetry Viewer Error:[/bold red] {exc}")
                sys.exit(1)

    parser = argparse.ArgumentParser(
        prog="charon",
        description="The Continental Concierge CLI Client and Ecosystem Tools for Charon.",
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command", nargs="*", help="Optional command string to execute immediately."
    )
    parser.add_argument(
        "-a", "--agent", help="Bypass triage router and force execution on a target agent."
    )
    parser.add_argument(
        "-f",
        "--forge",
        action="store_true",
        help="Launch the interactive Skill Forge CLI wizard.",
    )
    parser.add_argument(
        "-k", "--api-key", default=DEFAULT_API_KEY, help="API Key for Charon daemon authorization."
    )
    parser.add_argument(
        "-n", "--non-interactive", action="store_true", help="Execute command and exit immediately."
    )
    parser.add_argument("--ping", action="store_true", help="Check daemon reachability.")
    parser.add_argument(
        "-t",
        "--telemetry",
        action="store_true",
        help="Launch the real-time Rich telemetry trace viewer.",
    )
    parser.add_argument("--url", default=DEFAULT_HOST, help="Target Charon daemon HTTP URL.")
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version="Charon v3.1.0 (FastAPI Gateway Engine)",
    )

    args, unknown_args = parser.parse_known_args()

    # Post-Argparse Fallback: Skill Librarian Intercept
    if args.command and args.command[0].lower() in ("librarian", "skills"):
        lib_args = args.command[1:] + unknown_args
        try:
            from charon.cli.librarian import main as run_librarian
            res = run_librarian(lib_args)
            sys.exit(res if isinstance(res, int) else 0)
        except Exception as exc:
            console.print(f"[bold red]Librarian Error:[/bold red] {exc}")
            sys.exit(1)

    # Telemetry Viewer Intercept
    if args.telemetry or (args.command and args.command[0].lower() == "telemetry"):
        try:
            try:
                from charon.telemetry.viewer import async_main as run_telemetry_viewer
            except ImportError:
                from charon.telemetry.viewer import main as run_telemetry_viewer

            if asyncio.iscoroutinefunction(run_telemetry_viewer):
                await run_telemetry_viewer()
            else:
                run_telemetry_viewer()
        except ImportError:
            console.print(
                "[bold red]Error:[/bold red] Telemetry viewer module (`charon.telemetry.viewer`) not found."
            )
            sys.exit(1)
        except Exception as exc:
            console.print(f"[bold red]Telemetry Viewer Error:[/bold red] {exc}")
            sys.exit(1)
        sys.exit(0)

    # Skill Forge CLI Intercept (Flag-based fallback)
    is_forge_cmd = args.forge or (
        args.command and args.command[0].lower() in ("forge", "skill-forge", "skill_forge")
    )
    if is_forge_cmd:
        if args.command and args.command[0].lower() in ("forge", "skill-forge", "skill_forge"):
            forge_args: List[str] = args.command[1:] + unknown_args
        else:
            forge_args = (args.command if args.command else []) + unknown_args

        try:
            try:
                from charon.skill_forge_cli import async_main as run_skill_forge
            except ImportError:
                from charon.skill_forge_cli import main as run_skill_forge

            if asyncio.iscoroutinefunction(run_skill_forge):
                await run_skill_forge(forge_args)
            else:
                run_skill_forge(forge_args)
        except ImportError:
            console.print(
                "[bold red]Error:[/bold red] Skill Forge module (`charon.skill_forge_cli`) not found."
            )
            sys.exit(1)
        except Exception as exc:
            console.print(f"[bold red]Skill Forge Error:[/bold red] {exc}")
            sys.exit(1)
        sys.exit(0)

    # Validate Non-Interactive Flag
    if args.non_interactive and not args.command:
        console.print(
            "[bold red]Error:[/bold red] Non-interactive mode (-n / --non-interactive) requires a command string."
        )
        sys.exit(1)

    client = CharonClient(base_url=args.url, api_key=args.api_key)

    try:
        if args.ping:
            if await client.ping_daemon():
                console.print("[bold green]✓[/bold green] Charon daemon is online and responsive.")
                sys.exit(0)
            else:
                console.print(
                    f"[bold red]✗ Connection Refused:[/bold red] Charon daemon is not responding at {args.url}."
                )
                sys.exit(1)

        if not await client.ping_daemon():
            console.print(
                f"[bold red]Connection Refused:[/bold red] Charon daemon is not responding at {args.url}."
            )
            console.print("[dim]Ensure the daemon is running (`python3 daemon.py` or systemd service).[/dim]")
            sys.exit(1)

        session = PromptSession(history=InMemoryHistory())

        if not args.non_interactive and not args.command:
            console.print(
                Panel(
                    "[bold blue]Welcome to The Continental.[/bold blue]\n[dim]How may I be of service this evening?[/dim]",
                    border_style="blue",
                    expand=False,
                )
            )

        staged_input: Optional[str] = None

        if args.command:
            initial_command = " ".join(args.command)
            console.print(f"[bold green]>[/bold green] {initial_command}")
            try:
                success, staged_input = await client.submit_and_stream(
                    initial_command,
                    session,
                    agent_override=args.agent,
                    non_interactive=args.non_interactive,
                )
            except Exception as stream_err:
                console.print(f"[bold red]Streaming Error:[/bold red] {stream_err}")
                success = False

            if args.non_interactive:
                sys.exit(0 if success else 1)

        while True:
            try:
                if staged_input:
                    proposal_cmd = staged_input
                    staged_input = None
                    user_input = await prompt_concierge_choice(proposal_cmd, session=session)

                    if user_input is None:
                        continue

                    console.print(f"[bold green]>[/bold green] {user_input}")
                else:
                    user_input = await session.prompt_async(
                        HTML("<ansigreen><b>> </b></ansigreen>")
                    )
                    user_input = user_input.strip()

                if user_input.lower() in ["exit", "quit", "q", "that will be all"]:
                    console.print("[bold blue]A wise decision. Good evening.[/bold blue]")
                    break

                if user_input:
                    try:
                        _, staged_input = await client.submit_and_stream(
                            user_input, session, agent_override=args.agent
                        )
                    except Exception as stream_err:
                        console.print(f"[bold red]Execution Error:[/bold red] {stream_err}")

            except (KeyboardInterrupt, EOFError):
                console.print("\n[bold blue]A wise decision. Good evening.[/bold blue]")
                break
    finally:
        if hasattr(client, "close"):
            if asyncio.iscoroutinefunction(client.close):
                await client.close()
            else:
                client.close()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/cli/ui.py`

```python
"""
charon/cli/ui.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Visual effects, spinner, and terminal rendering helpers for Charon CLI.
"""

import itertools
import sys
import threading
import time
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown

console = Console()


class CharonSpinner:
    """Thread-safe terminal spinner supporting dynamic status updates."""

    def __init__(self, message: str = "Tending to the arrangements..."):
        self.spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        self.message = message
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def spin(self) -> None:
        while self.running:
            with self._lock:
                msg = self.message
            # \r clears back to start, \033[K clears to end of line to eliminate artifact text
            sys.stdout.write(f"\r\033[K\033[36m{next(self.spinner)}\033[0m {msg}")
            sys.stdout.flush()
            time.sleep(0.08)
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def start(self, message: Optional[str] = None) -> None:
        with self._lock:
            if message:
                self.message = message
            if not self.running:
                self.running = True
                self.thread = threading.Thread(target=self.spin, daemon=True)
                self.thread.start()

    def update(self, message: str) -> None:
        """Dynamically updates the spinner text without restarting the animation thread."""
        with self._lock:
            self.message = message

    def stop(self) -> None:
        with self._lock:
            if self.running:
                self.running = False
                if self.thread and self.thread.is_alive():
                    self.thread.join(timeout=0.5)
                self.thread = None


def teletype_print(text: str, delay: float = 0.015) -> None:
    """Prints plain text character-by-character to simulate a concierge feed."""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()


def render_response(message: str) -> None:
    """Renders formatted response content cleanly, preserving multiline command outputs."""
    if message.startswith("[System]: "):
        message = message[10:]

    if any(marker in message for marker in ["```", "### ", "## ", "# ", "* ", "- "]):
        console.print()
        console.print(Markdown(message))
    elif "\n" in message:
        console.print()
        console.print(message)
    else:
        teletype_print(message)

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/daemon.py`

```python
"""
charon/daemon.py
System Version: v0.1.0 | File Revision: 1.5.0

Module: Charon Daemon (`charond`) - Gateway Entry Point.

Wires FastAPI network routes, static dashboard serving, persistent queue processing,
state SQLite tables, execution workspace handling, live telemetry bus forwarding,
SkillGapRegistry integration, agent progress callbacks, and proactive task heartbeats
to the central OrchestrationEngine execution loop.
"""

import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from charon.config.logging import setup_logging
from charon.config.paths import ensure_ecosystem_directories
from charon.core.orchestration import OrchestrationEngine
from charon.core.registry import SkillGapRegistry
from charon.gateway.core import CharonDaemon
from charon.gateway.middleware import APIKeyMiddleware
from charon.gateway.models import WSEvent
from charon.gateway.routes import router as api_router
from charon.gateway.ws import manager
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

# 1. Ensure runtime paths exist and logging handlers are configured
ensure_ecosystem_directories()
setup_logging()

logger = logging.getLogger("Charon.Daemon")

# 2. Initialize engine, gateway daemon wrapper, and central gap registry
engine = OrchestrationEngine()
daemon = CharonDaemon(engine=engine)
gap_registry = SkillGapRegistry.get_instance()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Initializing Charon FastAPI Gateway, Core Engine, Gap Registry, and Persistent Queue..."
    )

    # Expose runtime instances on FastAPI app.state for HTTP and WS route handlers
    app.state.daemon = daemon
    app.state.engine = daemon.engine
    app.state.emitter = daemon.emitter
    app.state.gatekeeper = daemon.gatekeeper
    app.state.concierge = daemon.concierge
    app.state.state_mgr = daemon.state_mgr
    app.state.ledger = daemon.ledger
    app.state.workspace_mgr = daemon.workspace_mgr
    app.state.queue = daemon.queue
    app.state.gap_registry = gap_registry

    # Bridge central TelemetryBus & Agent Progress Callbacks -> Daemon WebSocket Emitter
    loop = asyncio.get_running_loop()

    # =====================================================================
    # ---> Direct UI Telemetry Bridge for Injected Agent Callbacks <---
    def ui_telemetry_bridge(payload: dict) -> None:
        """Callback injected into agents to push live progress updates directly to the GNOME HUD via WebSocket."""
        try:
            ws_event = WSEvent.model_construct(
                event_type=payload.get("type", "task_progress"),
                agent_name=payload.get("agent_name", "System"),
                client_id="desktop_concierge",
                data=payload.get("data", {}),
            )
            # Safely drop the synchronous agent update onto the async WS queue across thread boundary
            asyncio.run_coroutine_threadsafe(manager.broadcast(ws_event), loop)
        except Exception as err:
            logger.error(f"[Daemon] UI Telemetry Bridge error: {err}")

    # Inject the callback into the Dispatcher so it gets bound to every resolved Agent
    if hasattr(engine, "dispatcher") and engine.dispatcher:
        engine.dispatcher.agent_telemetry_callback = ui_telemetry_bridge
        logger.info(
            "[Charon.Daemon] AgentDispatcher injected with ui_telemetry_bridge callback."
        )

    # =====================================================================

    def bridge_telemetry_event(event) -> None:
        """Callback that forwards internal TelemetryBus TraceEvents and Gap Alerts to WebSocket emitter."""
        try:
            # 1. Normalize the event payload (handles both Pydantic models and raw dicts)
            if hasattr(event, "model_dump"):
                event_dict = event.model_dump(mode="json")
            elif hasattr(event, "dict"):
                event_dict = event.dict()
            elif isinstance(event, dict):
                event_dict = event
            else:
                event_dict = vars(event)

            # Safely extract dictionaries and normalize Enum values
            details = event_dict.get("details") or {}
            safe_details = {str(k): str(v) for k, v in details.items()}

            raw_event_type = event_dict.get("event_type", "THINKING")
            event_type_str = (
                raw_event_type.value
                if hasattr(raw_event_type, "value")
                else str(raw_event_type)
            )
            agent_name_str = event_dict.get("agent_name", "Coordinator")

            # 2. Construct the WSEvent
            ws_event = WSEvent.model_construct(
                event_type="telemetry_trace",
                task_id=str(details.get("task_id", "system")),
                client_id="telemetry_viewer",
                agent_name=agent_name_str,
                data={
                    "event_type": event_type_str,
                    "agent_name": agent_name_str,
                    "action": event_dict.get("action"),
                    "reasoning_chunk": event_dict.get("reasoning_chunk"),
                    "timestamp": event_dict.get("timestamp"),
                    "duration_ms": event_dict.get("duration_ms"),
                    "details": safe_details,
                },
            )

            # 3. Broadcast to all active clients (including the telemetry viewer)
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(ws_event),
                loop,
            )

            # Proactive Skill Blueprint Ready Broadcast
            if details.get("has_blueprint"):
                blueprint_event = WSEvent.model_construct(
                    event_type="skill_blueprint_ready",
                    task_id=str(details.get("task_id", "system")),
                    client_id="telemetry_viewer",
                    agent_name=agent_name_str,
                    data={
                        "agent_name": agent_name_str,
                        "action": event_dict.get("action"),
                        "pending_blueprints": len(
                            gap_registry.get_pending_blueprints()
                        ),
                        "message": "Recurring skill gap threshold met. SkillBlueprint ready for code generation.",
                    },
                )
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast(blueprint_event), loop
                )

            # Diagnostic Gap Detected Broadcast
            if details.get("diagnostics"):
                gap_event = WSEvent.model_construct(
                    event_type="skill_gap_detected",
                    task_id=str(details.get("task_id", "system")),
                    client_id="telemetry_viewer",
                    agent_name=agent_name_str,
                    data={
                        "agent_name": agent_name_str,
                        "action": event_dict.get("action"),
                        "diagnostics": str(details.get("diagnostics")),
                    },
                )
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast(gap_event), loop
                )

        except Exception as err:
            logger.error(
                f"[Daemon] FATAL Telemetry bridge error: {err}", exc_info=True
            )

    # Register subscription handler to live telemetry bus
    telemetry_bus.subscribe(bridge_telemetry_event)
    logger.info(
        "[Charon.Daemon] TelemetryBus subscriber & SkillGap notifier bridged to WebSocket Emitter."
    )

    async def active_task_heartbeat_worker():
        """Periodic background tick emitting heartbeats for active in-flight tasks."""
        while True:
            try:
                await asyncio.sleep(2)
                if hasattr(daemon, "get_active_tasks"):
                    active_tasks = daemon.get_active_tasks()
                    for task in active_tasks:
                        await daemon.emitter.emit(
                            event_type="task_heartbeat",
                            task_id=task.get("id"),
                            client_id=task.get("client_id"),
                            data={
                                "status": task.get("status", "processing"),
                                "active_agent": task.get(
                                    "assigned_agent", "Orchestrator"
                                ),
                                "elapsed_seconds": task.get("elapsed", 0),
                            },
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(
                    f"Task heartbeat worker encountered an anomaly: {e}"
                )

    # Spawn background task workers
    queue_task = asyncio.create_task(
        daemon.process_queue(), name="queue_worker"
    )
    overseer_task = asyncio.create_task(
        daemon.start_overseer_reporter(interval=30), name="overseer_reporter"
    )
    heartbeat_task = asyncio.create_task(
        active_task_heartbeat_worker(), name="task_heartbeat_worker"
    )

    yield

    # =====================================================================
    # ---> TEARDOWN SEQUENCE <---
    # =====================================================================
    logger.info(
        "Shutting down Charon Daemon background tasks and core subsystems..."
    )

    # 1. Unsubscribe from global telemetry bus to prevent memory leaks/dangling callbacks
    if hasattr(telemetry_bus, "unsubscribe"):
        telemetry_bus.unsubscribe(bridge_telemetry_event)
        logger.info("[Charon.Daemon] Unsubscribed from TelemetryBus.")

    # 2. Cancel the background worker loops
    queue_task.cancel()
    overseer_task.cancel()
    heartbeat_task.cancel()
    await asyncio.gather(
        queue_task, overseer_task, heartbeat_task, return_exceptions=True
    )
    logger.info("[Charon.Daemon] Async background workers halted.")

    # 3. Trigger Core Engine / Daemon graceful shutdown
    if hasattr(engine, "shutdown"):
        await engine.shutdown()
        logger.info(
            "[Charon.Daemon] Core OrchestrationEngine safely shut down."
        )

    logger.info("Charon Daemon shutdown complete.")


app = FastAPI(
    title="Charon Engine API Gateway",
    version="3.1.0",
    description="FastAPI Network Gateway, State Engine, and Orchestration Core for Charon.",
    lifespan=lifespan,
)

# Middleware Configuration
app.add_middleware(APIKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST & WebSocket API Routes
app.include_router(api_router)

# Mount Static Dashboard Interface
app.mount(
    "/dashboard",
    StaticFiles(directory="charon/gateway/static/dashboard", html=True),
    name="dashboard",
)


def main():
    uvicorn.run("charon.daemon:app", host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/exceptions.py`

```python
"""
charon/exceptions.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Centralized exception definitions for Charon daemon and specialist agent handoffs.
"""

from typing import Any, Optional


class CharonBaseException(Exception):
    """Base exception class for all Charon system exceptions."""
    pass


class HandoffException(CharonBaseException):
    """Raised when an agent detects a request outside its domain or capabilities,

    triggering a dynamic inter-agent handoff inside the dispatcher.
    """

    def __init__(
        self,
        target_agent: str,
        reason: str,
        payload: Optional[Any] = None,
    ):
        self.target_agent = target_agent
        self.reason = reason
        self.payload = payload
        super().__init__(f"Dynamic handoff to {target_agent}: {reason}")
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/__init__.py`

```python
"""
charon/gateway/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Package initialization gateway for gateway.
"""


```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/core.py`

```python
"""
charon/gateway/core.py
System Version: v0.1.0 | File Revision: 2.1.1

Module: Charon Core Daemon Orchestrator.

Central daemon managing lifecycle execution state, persistent task queue processing,
workspace isolation, Gatekeeper authorization resolution, and client event broadcasting.
"""

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.config import (
    DEFAULT_CONCIERGE_MIN_CONFIDENCE,
    DEFAULT_HEAVY_MODEL,
    DEFAULT_TRIAGE_MODEL,
    PROJECT_MEMORY_DIR,
    ensure_ecosystem_directories,
)
from charon.core.concierge import ConciergeService
from charon.core.orchestration import OrchestrationEngine
from charon.core.ledger import ExecutionLedger
from charon.core.queue import PersistentTaskQueue
from charon.core.session import SessionGateway
from charon.core.state import StateManager, TaskStatus
from charon.core.workspace import WorkspaceManager
from charon.gateway.emitter import EventEmitter
from charon.gateway.gatekeeper import GatekeeperManager
from charon.gateway.models import WSEvent
from charon.gateway.telemetry import TelemetryReporter

logger = logging.getLogger("Charon.Gateway.Core")


class DaemonLogInterceptor(logging.Handler):
    """
    Taps into internal python loggers (Charon and CHAROND) during task execution
    and converts structural log events into real-time WebSocket progress frames.
    """

    def __init__(self, daemon: "CharonDaemon"):
        super().__init__()
        self.daemon = daemon

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Only intercept log records from Charon core modules and domain agents
            if not (record.name.startswith("Charon") or record.name.startswith("CHAROND")):
                return

            task_id = getattr(self.daemon.emitter, "current_task_id", None)
            client_id = getattr(self.daemon.emitter, "current_client_id", None)
            if not task_id or not client_id:
                return

            msg = record.getMessage()

            # Ignore network/polling HTTP noise
            if "httpx" in record.name or "HTTP Request" in msg or "WebSocket" in msg:
                return

            event_type = "task_progress"
            data: Dict[str, Any] = {
                "message": msg,
                "logger": record.name,
                "level": record.levelname,
            }

            # Map domain log events to CLI-understood WebSocket events
            if "Parser" in record.name and "routed task to:" in msg:
                target_agent = msg.split("routed task to:")[-1].strip()
                event_type = "agent_action"
                data.update({
                    "agent": target_agent,
                    "action": f"Task routed to {target_agent}",
                    "phase": "triage",
                })
            elif "Coordinator" in record.name:
                event_type = "agent_action"
                data.update({
                    "agent": "Coordinator",
                    "action": msg,
                    "phase": "reflection_loop",
                })
            elif "Dispatcher" in record.name and "Executing task:" in msg:
                event_type = "agent_action"
                data.update({
                    "action": msg,
                    "phase": "dispatch",
                })
            elif any(domain in record.name for domain in
                     ["Quartermaster", "Generalist", "Engineer", "Archivist", "Steward", "Spark", "Machinist"]):
                event_type = "step"
                data.update({"step": msg})

            event = WSEvent(
                event_type=event_type,
                task_id=task_id,
                data=data,
            )

            # Schedule emission on current event loop without blocking execution
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.daemon.emitter.emit_targeted(event))
            except RuntimeError:
                pass
        except Exception:
            self.handleError(record)


class CharonDaemon:
    """Central orchestrator daemon managing persistent queues, state tables, and dispatch execution."""

    def __init__(
            self,
            engine: Optional[OrchestrationEngine] = None,
            heavy_model: str = DEFAULT_HEAVY_MODEL,
            triage_model: str = DEFAULT_TRIAGE_MODEL,
            db_path: Optional[Union[str, Path]] = None,
            concierge_min_confidence: float = DEFAULT_CONCIERGE_MIN_CONFIDENCE,
    ):
        ensure_ecosystem_directories()
        self.db_path: Path = Path(db_path) if db_path else PROJECT_MEMORY_DIR

        # Initialize SQLite State, Ledger, and Workspace Managers
        self.state_mgr = StateManager()
        self.ledger = ExecutionLedger()
        self.workspace_mgr = WorkspaceManager()
        self.queue = PersistentTaskQueue(state_manager=self.state_mgr)

        if engine:
            self.engine = engine
            self.orchestrator = engine.orchestrator
        else:
            self.orchestrator = SessionGateway(
                db_path=self.db_path,
                heavy_model=heavy_model,
                triage_model=triage_model,
            )
            self.engine = OrchestrationEngine(orchestrator=self.orchestrator)

        # Initialize Concierge with confidence threshold guardrails
        self.concierge = ConciergeService(min_confidence=concierge_min_confidence)
        self.emitter = EventEmitter()
        self.gatekeeper = GatekeeperManager()

        # Bind gateway components directly to engine context
        self.engine.bind_gateway_context(
            gatekeeper=self.gatekeeper,
            emitter=self.emitter,
            concierge=self.concierge,
        )

        # Updated TelemetryReporter instantiation passing state_manager for ticker provider
        self.telemetry = TelemetryReporter(
            queue_provider=self.queue.qsize,
            gatekeeper_status_provider=lambda: self.gatekeeper.awaiting_approval,
            task_provider=lambda: self.emitter.current_task_id,
            state_manager=self.state_mgr,
        )

        # Attach real-time log interceptor to root logger hierarchy
        self.log_interceptor = DaemonLogInterceptor(self)
        logging.getLogger().addHandler(self.log_interceptor)

    @property
    def awaiting_gatekeeper(self) -> bool:
        """Backward compatibility helper for gatekeeper state."""
        return self.gatekeeper.awaiting_approval

    async def verify_engine(self, retries: int = 3, delay: float = 3.0) -> bool:
        """Verify inference engine availability."""
        return await self.telemetry.verify_engine(retries=retries, delay=delay)

    async def evaluate_and_emit_concierge(
            self,
            user_input: str,
            result_text: str,
            completed_action: str = "",
            params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Flexible Concierge evaluator with dynamic parameter inspection and authorization guards."""
        if not self.concierge or not self.emitter:
            return

        # Explicit Authorization Guardrail: Suppress suggestions if result indicates gatekeeper intercept
        if result_text and str(result_text).startswith("[Awaiting Authorization]"):
            logger.debug("[CONCIERGE] Task result awaiting authorization. Suppressing evaluation.")
            return

        # Notify UI that Concierge is evaluating follow-ups
        await self.emitter.emit_targeted(
            WSEvent(
                event_type="agent_action",
                task_id=self.emitter.current_task_id,
                data={
                    "agent": "Concierge",
                    "action": "Evaluating proactive proposals...",
                    "phase": "concierge_eval",
                },
            )
        )

        try:
            eval_fn = getattr(
                self.concierge,
                "evaluate_next_step",
                getattr(self.concierge, "get_next_step", None),
            )
            if not eval_fn:
                logger.warning("Concierge instance has no valid evaluation method.")
                return

            sig = inspect.signature(eval_fn)
            fn_params = sig.parameters

            kwargs: Dict[str, Any] = {}
            if "user_query" in fn_params:
                kwargs["user_query"] = user_input
            elif "query" in fn_params:
                kwargs["query"] = user_input
            elif "prompt" in fn_params:
                kwargs["prompt"] = user_input

            if "completed_action" in fn_params:
                kwargs["completed_action"] = completed_action
            elif "action" in fn_params:
                kwargs["action"] = completed_action

            if "execution_result" in fn_params:
                kwargs["execution_result"] = str(result_text)
            elif "result" in fn_params:
                kwargs["result"] = str(result_text)

            if "params" in fn_params:
                kwargs["params"] = params or {}

            if kwargs:
                coro_or_res = eval_fn(**kwargs)
            else:
                coro_or_res = eval_fn(user_input, completed_action, str(result_text))

            suggestion = (
                await coro_or_res if inspect.iscoroutine(coro_or_res) else coro_or_res
            )

            if suggestion:
                logger.info(f"Concierge generated proposal: {suggestion}")
                await self.emitter.emit_concierge(suggestion)
            else:
                logger.debug("Concierge evaluated task context and returned no proposal.")

        except Exception as concierge_err:
            logger.warning(f"Concierge evaluation error: {concierge_err}", exc_info=True)

    async def start_overseer_reporter(self, interval: int = 5) -> None:
        """Start background telemetry reporting task."""
        await self.telemetry.start_loop(interval=interval)

    async def process_queue(self) -> None:
        """Primary queue processing loop for incoming task directives and gatekeeper decisions."""
        while not await self.verify_engine():
            logger.warning("Inference engine unavailable. Retrying verification in 10s...")
            await asyncio.sleep(10)

        # Recover pending or interrupted tasks from SQLite state DB upon daemon startup
        recovered_count = await self.queue.initialize_and_recover()
        logger.info(
            f"Charon daemon persistent queue processor operational. "
            f"Recovered {recovered_count} task(s) from persistent state storage."
        )

        while True:
            try:
                item = await self.queue.get()
            except asyncio.CancelledError:
                break

            task_id = item.get("task_id")
            client_id = item.get("client_id")
            user_input = str(item.get("prompt", "")).strip()
            agent_override_str = item.get("agent_override")
            routing_hint_payload = item.get("routing_hint")
            approval_id = item.get("approval_id")
            decision = item.get("decision")

            try:
                self.emitter.set_context(task_id=task_id, client_id=client_id)

                # 1. Direct Gatekeeper Approval/Denial Payload
                if approval_id and decision:
                    logger.info(f"Processing Gatekeeper decision '{decision}' for intercept {approval_id}")
                    if hasattr(self.gatekeeper, "resolve_intercept"):
                        self.gatekeeper.resolve_intercept(approval_id, decision)
                    elif hasattr(self.gatekeeper, "submit_decision"):
                        self.gatekeeper.submit_decision(approval_id, decision)

                    if task_id:
                        await self.ledger.log_event(
                            task_id=task_id,
                            event_type="gatekeeper_decision",
                            data={"approval_id": approval_id, "decision": decision},
                        )
                    continue

                # 2. String Command Approval Fallback
                if self.gatekeeper.awaiting_approval and user_input.lower() in [
                    "proceed", "yes", "approve", "cancel", "abort", "no"
                ]:
                    cmd = user_input.lower()
                    dec = "APPROVED" if cmd in ["proceed", "yes", "approve"] else "REJECTED"
                    active_id = getattr(self.gatekeeper, "active_approval_id", None)
                    if active_id and hasattr(self.gatekeeper, "resolve_intercept"):
                        self.gatekeeper.resolve_intercept(active_id, dec)
                        if task_id:
                            await self.ledger.log_event(
                                task_id=task_id,
                                event_type="gatekeeper_string_response",
                                data={"approval_id": active_id, "decision": dec},
                            )
                        continue

                # 3. Standard Request Execution Phase
                if task_id:
                    self.workspace_mgr.get_task_workspace(task_id, create=True)
                    await self.state_mgr.update_status(task_id, TaskStatus.RUNNING)
                    await self.ledger.log_event(
                        task_id=task_id,
                        event_type="task_started",
                        data={
                            "prompt": user_input,
                            "agent_override": agent_override_str,
                            "has_routing_hint": bool(routing_hint_payload),
                        },
                    )

                # Initial status notification
                await self.emitter.emit_targeted(
                    WSEvent(
                        event_type="status_change",
                        task_id=task_id,
                        data={"status": "executing", "prompt": user_input},
                    )
                )

                # Emit initial Triage Router progress event
                await self.emitter.emit_targeted(
                    WSEvent(
                        event_type="agent_action",
                        task_id=task_id,
                        data={
                            "agent": "Triage Router",
                            "action": "Analyzing intent & selecting agent...",
                            "phase": "triage_start",
                        },
                    )
                )

                def stream_cb(msg: str):
                    """Callback bridging streamed model outputs & progress indicators to WS."""
                    asyncio.create_task(self.emitter.emit_stream(msg))

                    if msg.startswith("[") and "]" in msg and ":" in msg:
                        try:
                            tag_content = msg[1:msg.find("]")]
                            agent_name, action_text = [s.strip() for s in tag_content.split(":", 1)]
                            asyncio.create_task(
                                self.emitter.emit_targeted(
                                    WSEvent(
                                        event_type="agent_action",
                                        task_id=task_id,
                                        data={
                                            "agent": agent_name,
                                            "action": action_text,
                                            "phase": "execution",
                                        },
                                    )
                                )
                            )
                        except Exception:
                            pass

                result = await self.engine.process_request(
                    user_input=user_input,
                    stream_cb=stream_cb,
                    agent_override=agent_override_str,
                    task_id=task_id,
                    routing_hint=routing_hint_payload,
                )

                if result and not result.startswith("[Awaiting Authorization]"):
                    if task_id:
                        await self.state_mgr.update_status(task_id, TaskStatus.COMPLETED)
                        await self.ledger.log_event(
                            task_id=task_id,
                            event_type="task_completed",
                            data={"result_summary": str(result)[:300]},
                        )
                    if hasattr(self.orchestrator, "memory"):
                        self.orchestrator.memory.add_system_message(str(result))

                    # Invoke Concierge follow-up evaluator BEFORE task completion event closes WS listener
                    await self.evaluate_and_emit_concierge(
                        user_input=user_input,
                        result_text=result,
                        completed_action=agent_override_str or "task_execution",
                        params=item,
                    )

                    await self.emitter.emit_completed(result)

                elif result and result.startswith("[Awaiting Authorization]"):
                    if task_id:
                        await self.state_mgr.update_status(
                            task_id,
                            TaskStatus.AWAITING_APPROVAL,
                            approval_id=getattr(self.gatekeeper, "active_approval_id", None),
                        )
                        await self.ledger.log_event(
                            task_id=task_id,
                            event_type="task_intercepted",
                            data={"reason": result},
                        )

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error processing queue item for task '{task_id}': {e}", exc_info=True)
                if task_id:
                    await self.state_mgr.update_status(
                        task_id, TaskStatus.FAILED, error_message=str(e)
                    )
                    await self.ledger.log_event(
                        task_id=task_id,
                        event_type="task_failed",
                        data={"error": str(e)},
                    )
                await self.emitter.emit_completed(f"[System Error]: {str(e)}")
            finally:
                self.emitter.clear_context()
                self.queue.task_done()

    async def shutdown(self) -> None:
        """
        Gracefully terminate engine sub-components, halt in-flight agent tasks,
        and close persistent database connections.
        """
        logger.info("Initiating OrchestrationEngine shutdown sequence...")

        # 1. Halt the DAG Executor (Stops new nodes from being dispatched)
        dag_executor = getattr(self.engine, "dag_executor", getattr(self.orchestrator, "dag_executor", None))
        if dag_executor and hasattr(dag_executor, "shutdown"):
            try:
                if inspect.iscoroutinefunction(dag_executor.shutdown):
                    await dag_executor.shutdown()
                else:
                    dag_executor.shutdown()
                logger.debug("DAG Executor shutdown complete.")
            except Exception as e:
                logger.error(f"Error shutting down DAG executor: {e}")

        # 2. Halt Orchestrator (Kills active agent loops, flushes ChromaDB)
        if hasattr(self.orchestrator, "shutdown"):
            try:
                if inspect.iscoroutinefunction(self.orchestrator.shutdown):
                    await self.orchestrator.shutdown()
                else:
                    self.orchestrator.shutdown()
                logger.debug("Orchestrator shutdown complete.")
            except Exception as e:
                logger.error(f"Error shutting down Orchestrator: {e}")

        # 3. Safely Close SQLite Connections (State, Ledger, Librarian)
        librarian = getattr(self.engine, "librarian", getattr(self.orchestrator, "librarian", None))
        persistent_stores = [
            (self.state_mgr, "StateManager"),
            (self.ledger, "ExecutionLedger"),
        ]
        if librarian:
            persistent_stores.append((librarian, "SkillLibrarian"))

        for component, name in persistent_stores:
            # Handle both .close() and .shutdown() naming conventions
            teardown_fn = getattr(component, "close", getattr(component, "shutdown", None))
            if teardown_fn:
                try:
                    if inspect.iscoroutinefunction(teardown_fn):
                        await teardown_fn()
                    else:
                        teardown_fn()
                    logger.debug(f"Closed {name} persistent connections.")
                except Exception as e:
                    logger.error(f"Error closing {name}: {e}")

        logger.info("OrchestrationEngine shutdown sequence finalized.")
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/emitter.py`

```python
"""
charon/gateway/emitter.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: WebSocket Event Emitter.
Handles targeted or broadcast WebSocket event transmissions with socket error recovery
and direct support for live ThoughtRecord stream emissions.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from charon.gateway.models import WSEvent
from charon.gateway.ws import manager

logger = logging.getLogger("Charon.Gateway.Emitter")


class EventEmitter:
    """Handles targeted or broadcast WebSocket event transmissions with socket error recovery."""

    def __init__(self):
        self.current_task_id: Optional[str] = None
        self.current_client_id: Optional[str] = None
        self.current_agent: str = "System"

    def set_context(self, task_id: Optional[str], client_id: Optional[str]) -> None:
        """Update active client/task context for targeted transmissions."""
        self.current_task_id = task_id
        self.current_client_id = client_id

    def set_active_agent(self, agent_name: str) -> None:
        """Update the currently active agent for telemetry tracking."""
        self.current_agent = agent_name

    def clear_context(self) -> None:
        """Clear client/task context after execution loop completion."""
        self.current_task_id = None
        self.current_client_id = None
        self.current_agent = "System"

    async def emit_targeted(self, event: WSEvent) -> None:
        """Send event to specific client if bound and connected, with fallback to broadcast on missing/dead sockets."""
        if self.current_client_id and manager.is_client_connected(self.current_client_id):
            try:
                await manager.send_to_client(self.current_client_id, event)
                return
            except Exception as e:
                logger.warning(
                    f"Targeted socket delivery failed for client '{self.current_client_id}': {e}. Fallback to broadcast."
                )

        try:
            await manager.broadcast(event)
        except Exception as e:
            logger.error(f"Failed to broadcast WebSocket event: {e}", exc_info=True)

    async def emit_thought(self, thought_data: Dict[str, Any]) -> None:
        """Emit live CoT thought telemetry event from TaskBlackboard thought stream."""
        agent_name = thought_data.get("source_agent", self.current_agent)
        await self.emit_targeted(
            WSEvent(
                event_type="thought_record",
                task_id=self.current_task_id,
                agent_name=agent_name,
                data=thought_data,
            )
        )

    async def emit_agent_action(
        self,
        agent: str,
        action: str,
        phase: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit real-time sub-step agent action frame to drive CLI spinner status."""
        self.set_active_agent(agent)
        data: Dict[str, Any] = {"agent": agent, "action": action}
        if phase:
            data["phase"] = phase
        if extra_data:
            data.update(extra_data)

        await self.emit_targeted(
            WSEvent(
                event_type="agent_action",
                task_id=self.current_task_id,
                agent_name=agent,
                data=data,
            )
        )

    async def emit_step(self, step_description: str, extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Emit high-level plan step execution event."""
        data: Dict[str, Any] = {"step": step_description}
        if extra_data:
            data.update(extra_data)

        await self.emit_targeted(
            WSEvent(
                event_type="step",
                task_id=self.current_task_id,
                agent_name=self.current_agent,
                data=data,
            )
        )

    async def emit_progress(self, message: str, phase: Optional[str] = None, agent_name: Optional[str] = None) -> None:
        """Emit general progress update message."""
        active_agent = agent_name or self.current_agent
        data: Dict[str, Any] = {"message": message}
        if phase:
            data["phase"] = phase

        await self.emit_targeted(
            WSEvent(
                event_type="task_progress",
                task_id=self.current_task_id,
                agent_name=active_agent,
                data=data,
            )
        )

    async def emit_stream(self, message: str, agent_name: Optional[str] = None) -> None:
        """Emit agent log/stream output globally so monitors can render it."""
        active_agent = agent_name or self.current_agent
        event = WSEvent(
            event_type="agent_log",
            task_id=self.current_task_id,
            agent_name=active_agent,
            data={"message": message},
        )
        try:
            await manager.broadcast(event)
        except Exception as e:
            logger.error(f"Failed to broadcast stream token: {e}")

    async def emit_completed(self, message: str, agent_name: Optional[str] = None) -> None:
        """Emit task completion event."""
        active_agent = agent_name or self.current_agent
        await self.emit_targeted(
            WSEvent(
                event_type="task_complete",
                task_id=self.current_task_id,
                agent_name=active_agent,
                data={
                    "summary": message,
                    "result": message,
                    "output": message,
                    "content": message,
                },
            )
        )

    async def emit_error(self, error_message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Emit task failure/error event for UI alert rendering."""
        data: Dict[str, Any] = {"error": error_message}
        if details:
            data["details"] = details

        await self.emit_targeted(
            WSEvent(
                event_type="task_error",
                task_id=self.current_task_id,
                agent_name="System",
                data=data,
            )
        )

    async def emit_concierge(self, suggestion: Dict[str, Any]) -> None:
        """Emit concierge next-step suggestions."""
        await self.emit_targeted(
            WSEvent(
                event_type="concierge_suggestion",
                task_id=self.current_task_id,
                agent_name="Concierge",
                data=suggestion if isinstance(suggestion, dict) else {"suggestion": str(suggestion)},
            )
        )

    async def emit_gatekeeper(
        self, manifest_message: str, action: str, approval_id: Optional[str] = None
    ) -> str:
        """
        Emit gatekeeper intercept request using the bound approval token ID.
        Returns the active approval ID.
        """
        token = approval_id or f"appr_{uuid.uuid4().hex[:8]}"
        await self.emit_targeted(
            WSEvent(
                event_type="gatekeeper_intercept",
                task_id=self.current_task_id,
                agent_name="Gatekeeper",
                data={
                    "manifest": manifest_message,
                    "action": action,
                    "approval_id": token,
                },
            )
        )
        return token

    async def emit_agent_response(self, agent: str, content: str) -> None:
        """Emit completed agent output response."""
        await self.emit_targeted(
            WSEvent(
                event_type="agent_response",
                task_id=self.current_task_id,
                agent_name=agent,
                data={"agent": agent, "content": content},
            )
        )

    async def emit_telemetry_trace(self, event_type: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Emit routing and execution telemetry for HUD visualizers."""
        data = {"event_type": event_type}
        if details:
            data["details"] = details
            if "action" in details:
                data["action"] = details["action"]

        await self.emit_targeted(
            WSEvent(
                event_type="telemetry_trace",
                task_id=self.current_task_id,
                agent_name=self.current_agent,
                data=data,
            )
        )
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/gatekeeper.py`

```python
"""
charon/gateway/gatekeeper.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Gatekeeper State Manager & Tiered Risk Matrix
Intercepts Level 2/3 high-risk agent actions and handles human-in-the-loop authorization
using approval token IDs (appr_xxxxxx) and asyncio event signaling.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set, Tuple

from pydantic import BaseModel

logger = logging.getLogger("Charon.Gateway.Gatekeeper")

# ADR-003: Level 2/3 High-Risk Actions requiring mandatory human authorization
HIGH_RISK_ACTIONS: Set[str] = {
    # Hardware & Physical Operations (Level 2/3)
    "flash_hardware",
    "flash_firmware",
    "transmit_to_printer",
    # Code Execution & Terminal Commands (Level 2/3)
    "execute_sandbox_code",
    "run_existing_script",
    "execute_cli_command",
    "execute_shell_command",
    # OS & Service Mutations (Level 2/3)
    "manage_service",
    "package_manager",
    "modify_system_service",
    "update_kernel_config",
    # Workspace & Ledger Purging (Level 2/3)
    "delete_workspace",
    "purge_database",
    "expunge_record",
    "delete_rule",
    "purge_logs",
    "vacuum_database",
}


@dataclass
class PendingIntercept:
    """Represents an active authorization intercept held in memory."""

    approval_id: str
    agent: str
    extraction: Optional[BaseModel]
    user_raw_input: str
    event: asyncio.Event = field(default_factory=asyncio.Event)
    decision: Optional[str] = None  # "APPROVED", "REJECTED", "CANCEL", etc.


class GatekeeperManager:
    """Manages pre-flight authorization intercepts and pending execution state."""

    def __init__(self) -> None:
        self.pending_intercepts: Dict[str, PendingIntercept] = {}
        # Single-state pointers for backward compatibility
        self.pending_agent: Optional[str] = None
        self.pending_extraction: Optional[BaseModel] = None
        self.pending_raw_input: str = ""
        self.active_approval_id: Optional[str] = None

    @property
    def awaiting_approval(self) -> bool:
        """Dynamic check returning True if any active pending intercepts exist."""
        return len(self.pending_intercepts) > 0

    @awaiting_approval.setter
    def awaiting_approval(self, value: bool) -> None:
        """Compatibility setter allowing legacy direct assignment without state drift."""
        pass

    def requires_approval(self, extraction: Optional[BaseModel]) -> bool:
        """Check if extraction payload flags approval required or matches ADR-003 high-risk matrix."""
        if not extraction:
            return False

        # 1. Direct payload flag check
        if getattr(extraction, "requires_approval", False):
            return True

        # 2. Defense-in-depth check against Level 2/3 action matrix
        action = getattr(extraction, "action", "")
        if action and str(action).lower() in HIGH_RISK_ACTIONS:
            return True

        return False

    def requires_approval_raw(
        self,
        agent_name: str,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Helper to evaluate risk on raw agent/action strings during DAG step execution."""
        if str(action).lower() in HIGH_RISK_ACTIONS:
            return True
        if parameters and parameters.get("requires_approval"):
            return True
        return False

    def intercept_task(
        self,
        agent: str,
        extraction: Optional[BaseModel],
        user_raw_input: str,
    ) -> Tuple[str, str, str]:
        """
        Creates a pending approval token (appr_xxxxxx), sets state, and builds the manifest text.
        Returns: Tuple[manifest_message, action_name, approval_id]
        """
        approval_id = f"appr_{uuid.uuid4().hex[:8]}"
        intercept = PendingIntercept(
            approval_id=approval_id,
            agent=agent,
            extraction=extraction,
            user_raw_input=user_raw_input,
        )
        self.pending_intercepts[approval_id] = intercept

        # Update legacy single-state flags
        self.pending_agent = agent
        self.pending_extraction = extraction
        self.pending_raw_input = user_raw_input
        self.active_approval_id = approval_id

        action = getattr(extraction, "action", "unknown") if extraction else "unknown"
        param_details = []

        if extraction:
            if hasattr(extraction, "model_dump"):
                payload_dict = extraction.model_dump()
            elif hasattr(extraction, "dict"):
                payload_dict = extraction.dict()
            else:
                payload_dict = getattr(extraction, "__dict__", {})

            for key, val in payload_dict.items():
                if key not in ["requires_approval", "memory_candidate"] and val is not None:
                    formatted_val = (
                        f"\n    '''\n    {str(val).strip()}\n    '''"
                        if isinstance(val, str) and len(str(val)) > 80
                        else str(val)
                    )
                    param_details.append(f"  • {key}: {formatted_val}")

        manifest_params = (
            "\n".join(param_details) if param_details else "  • No parameters specified."
        )
        manifest_message = (
            f"\n🛡️ GATEKEEPER PRE-FLIGHT MANIFEST [{approval_id}]\n"
            f"─────────────────────────────────────────────────────────────\n"
            f" Target Agent : {agent}\n"
            f" Action        : {action}\n"
            f" Proposed Parameters:\n{manifest_params}\n"
            f"─────────────────────────────────────────────────────────────\n"
            f"Authorization required before proceeding.\n"
            f"Reply with 'proceed' or 'cancel' (Token: {approval_id})."
        )

        logger.warning(
            f"GATEKEEPER TRIGGERED [{approval_id}]: Action '{action}' by {agent} requires approval."
        )
        return manifest_message, str(action), approval_id

    def resolve_intercept(self, approval_id: str, decision: str) -> bool:
        """
        Resolves a pending intercept token, unblocking waiting execution threads.
        Called directly by gateway routes or WebSocket handlers.
        """
        norm_decision = decision.strip().upper()

        # 1. Resolve targeted approval_id if present
        if approval_id in self.pending_intercepts:
            intercept = self.pending_intercepts[approval_id]
            intercept.decision = norm_decision
            intercept.event.set()
            logger.info(f"Resolved Gatekeeper Intercept '{approval_id}' -> {norm_decision}")
            return True

        # 2. Fallback: Resolve active single-state intercept if active token matches
        if self.active_approval_id and self.active_approval_id in self.pending_intercepts:
            intercept = self.pending_intercepts[self.active_approval_id]
            intercept.decision = norm_decision
            intercept.event.set()
            logger.info(f"Resolved active Gatekeeper Intercept '{self.active_approval_id}' -> {norm_decision}")
            return True

        logger.warning(f"Attempted to resolve unknown or expired approval_id: {approval_id}")
        return False

    def submit_decision(self, approval_id: str, decision: str) -> bool:
        """Explicit alias for resolve_intercept to support direct core caller contracts."""
        return self.resolve_intercept(approval_id, decision)

    async def wait_for_decision(self, approval_id: str, timeout: float = 300.0) -> str:
        """
        Asynchronously waits for client authorization response targeting approval_id.
        Times out after `timeout` seconds (default 5 mins), returning "EXPIRED".
        """
        intercept = self.pending_intercepts.get(approval_id)
        if not intercept:
            logger.warning(f"wait_for_decision called on missing or expired approval_id: {approval_id}")
            return "EXPIRED"

        try:
            await asyncio.wait_for(intercept.event.wait(), timeout=timeout)
            return intercept.decision or "REJECTED"
        except asyncio.TimeoutError:
            logger.warning(f"Gatekeeper Intercept '{approval_id}' timed out after {timeout}s.")
            intercept.decision = "EXPIRED"
            return "EXPIRED"
        finally:
            # Safely release intercept memory AFTER waiting consumers process decision
            self.pending_intercepts.pop(approval_id, None)
            if self.active_approval_id == approval_id:
                self.reset()

    def handle_approval(self) -> Tuple[Optional[str], Optional[BaseModel], str]:
        """Legacy helper to approve and release the currently active payload."""
        agent = self.pending_agent
        extraction = self.pending_extraction
        raw_input = self.pending_raw_input

        if extraction and hasattr(extraction, "confirmed"):
            setattr(extraction, "confirmed", True)

        eff_input = (
            raw_input
            if "proceed" in raw_input.lower()
            else f"{raw_input} proceed"
        )
        self.reset()
        return agent, extraction, eff_input

    def reset(self) -> None:
        """Clear active gatekeeper pending pointers."""
        if self.active_approval_id and self.active_approval_id in self.pending_intercepts:
            self.pending_intercepts.pop(self.active_approval_id, None)

        self.pending_agent = None
        self.pending_extraction = None
        self.pending_raw_input = ""
        self.active_approval_id = None
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/middleware.py`

```python
"""
charon/gateway/middleware.py
System Version: v0.1.0 | File Revision: 1.2.0

Module: Local Network & Peripheral Node Authentication Boundary.

Enforces API key verification across HTTP connections for external clients, CLI tools,
and LAN network nodes communicating with charond.
Exempts dashboard assets, health checks, CORS preflight requests, and OpenAPI documentation routes.
"""

import logging
import secrets
from typing import List, Optional
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from charon.config import API_KEY_HEADER_NAME, CHARON_API_KEY

logger = logging.getLogger("Charon.Gateway.Middleware")


class APIKeyMiddleware(BaseHTTPMiddleware):
    """HTTP Middleware inspecting incoming REST requests for valid authentication."""

    def __init__(self, app, public_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.public_paths = public_paths or [
            "/v1/health",
            "/dashboard",
            "/favicon.ico",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]

    async def dispatch(self, request: Request, call_next):
        # 1. CORS Preflight Bypass (OPTIONS requests do not carry Auth headers)
        if request.method == "OPTIONS":
            return await call_next(request)

        # 2. WebSocket Protocol Scope Pass-Through
        # (WebSocket authentication is handled directly in routes.py websocket_endpoint)
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        # 3. Public Path Prefix Bypass
        path = request.url.path
        if any(
            path == p or path.startswith(f"{p.rstrip('/')}/")
            for p in self.public_paths
        ):
            return await call_next(request)

        # 4. Key Configuration Fail-Safe Check
        api_key_str = str(CHARON_API_KEY).strip() if CHARON_API_KEY else ""
        if not api_key_str:
            logger.critical("CHARON_API_KEY is unconfigured or empty! Rejecting request for safety.")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Server security error: CHARON_API_KEY is unconfigured on host daemon."},
            )

        # 5. Multi-Channel Key Extraction (Header, Bearer Token, or Query Parameter)
        provided_key = None
        if API_KEY_HEADER_NAME:
            provided_key = request.headers.get(API_KEY_HEADER_NAME) or request.headers.get(API_KEY_HEADER_NAME.lower())

        # Fallback A: Authorization header ("Bearer <token>")
        if not provided_key and "authorization" in request.headers:
            auth_header = request.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                provided_key = auth_header[7:].strip()

        # Fallback B: Query parameter (Required for constrained local nodes)
        if not provided_key:
            provided_key = request.query_params.get("api_key")

        # 6. Constant-Time Key Validation
        if not provided_key or not secrets.compare_digest(provided_key.strip(), api_key_str):
            client_ip = request.client.host if request.client else "Unknown"
            logger.warning(f"Unauthorized HTTP request to '{path}' blocked from IP: {client_ip}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid or missing API key token for HTTP access."},
            )

        return await call_next(request)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/models.py`

```python
"""
charon/gateway/models.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Gateway REST request/response and WebSocket event schemas.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ==============================================================================
# Task & Intercept REST Models
# ==============================================================================

class TaskRequest(BaseModel):
    prompt: str = Field(
        ...,
        description="Natural language prompt or command for Charon orchestration."
    )
    client_id: Optional[str] = Field(
        default="desktop_concierge",
        description="Originating client identifier."
    )
    agent_override: Optional[str] = Field(
        default=None,
        description="Optional agent key to bypass triage routing and force execution."
    )
    context: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Metadata or environmental context payload."
    )


class TaskResponse(BaseModel):
    task_id: str = Field(
        ...,
        description="Unique identifier assigned to the task."
    )
    status: Literal[
        "queued",
        "executing",
        "completed",
        "intercepted",
        "rescinded",
        "cancelled",
        "failed",
    ] = Field(
        ...,
        description="Current execution state of the task."
    )
    assigned_agent: Optional[str] = Field(
        default=None,
        description="The agent routed or assigned to handle this task."
    )
    message: str = Field(
        ...,
        description="Status summary, acknowledgment, or confirmation message."
    )
    result: Optional[Any] = Field(
        default=None,
        description="Execution output or structured payload if synchronously completed."
    )


class GatekeeperDecision(BaseModel):
    approval_id: str = Field(
        ...,
        description="Approval identifier matching the pre-flight intercept manifest."
    )
    decision: Literal["proceed", "rescind", "cancel"] = Field(
        ...,
        description="Physical authorization command submitted by the operator."
    )
    client_id: Optional[str] = Field(
        default="desktop_concierge",
        description="Identifier of the client node submitting the decision."
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional operator context or reasoning for the authorization response."
    )


# ==============================================================================
# Dynamic Router & Agent Control Models
# ==============================================================================

class AgentManifestResponse(BaseModel):
    """Payload representing an agent's dynamic routing configuration and capabilities."""
    agent_id: str = Field(..., description="Unique slug or key identifying the agent (e.g. 'the_machinist').")
    name: str = Field(..., description="Display name of the agent.")
    description: str = Field(..., description="Capability description evaluated during Pass 1 LLM triage.")
    system_prompt: str = Field(..., description="Base instructions injected into agent execution contexts.")
    priority_weight: float = Field(
        default=1.0,
        ge=0.1,
        le=5.0,
        description="Multiplier applied to Pass 1 LLM confidence scores (0.1 to 5.0)."
    )
    override_triggers: List[str] = Field(
        default_factory=list,
        description="Keyword or prefix shortcuts that instantly bypass triage and force dispatch."
    )
    active_tools: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of registered tool schemas assigned to this agent."
    )
    status: Literal["active", "disabled", "maintenance"] = Field(
        default="active",
        description="Operational status of the agent node."
    )


class AgentUpdateRequest(BaseModel):
    """Request payload for mutating agent triage parameters at runtime."""
    description: Optional[str] = Field(
        default=None,
        description="Updated capability description fed into Pass 1 triage prompts."
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="Updated system prompt for specialized execution."
    )
    priority_weight: Optional[float] = Field(
        default=None,
        ge=0.1,
        le=5.0,
        description="Updated score multiplier for triage ranking."
    )
    override_triggers: Optional[List[str]] = Field(
        default=None,
        description="Updated list of exact keyword/prefix triggers forcing routing."
    )


class ToolPatchRequest(BaseModel):
    """Payload for dynamically toggling tool availability for an agent."""
    tool_name: str = Field(..., description="Exact class or module name of the targeted skill tool.")
    enabled: bool = Field(..., description="Target status for enabling or disabling tool execution.")


class DynamicRuleRequest(BaseModel):
    """Payload for defining hard-shortcut override routing rules."""
    trigger: str = Field(..., description="Exact trigger string or prefix (e.g., '#archivist', 'git:').")
    agent_id: str = Field(..., description="ID of the target agent to receive forced dispatch.")
    description: Optional[str] = Field(default="", description="Operator notes explaining rule purpose.")


class DynamicRuleResponse(BaseModel):
    """Outbound representation of an active dynamic shortcut rule."""
    rule_id: str = Field(..., description="Unique UUID assigned to the dynamic shortcut rule.")
    trigger: str = Field(..., description="Trigger string or prefix pattern.")
    target_agent: str = Field(..., description="Target agent ID handling the shortcut.")
    description: str = Field(default="", description="Rule operator notes.")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC creation timestamp."
    )


class TriageLogEntry(BaseModel):
    """Snapshot of a Pass 1 LLM triage evaluation for debugging and telemetry."""
    task_id: str = Field(..., description="Task identifier evaluated by triage.")
    prompt: str = Field(..., description="Original user prompt evaluated.")
    selected_agent: str = Field(..., description="Agent designated for dispatch.")
    confidence_score: float = Field(..., description="Final calculated confidence score after priority scaling.")
    candidate_scores: Dict[str, float] = Field(..., description="Raw or weighted score map across all candidates.")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of evaluation."
    )


# ==============================================================================
# WebSocket Event Stream Models
# ==============================================================================

class WSEvent(BaseModel):
    event_type: Literal[
        "status_change",
        "agent_log",
        "agent_action",
        "agent_response",
        "thought_record",
        "telemetry_trace",
        "step",
        "task_progress",
        "gatekeeper_intercept",
        "concierge_suggestion",
        "task_complete",
        "overseer_report",
        "steward_event",
        "system_alert",
        "heartbeat_idle",
        "heartbeat_active",
        "router_agent_updated",
        "router_tool_toggled",
        "router_rule_changed",
        "error",
        "task_error",
    ] = Field(
        ...,
        description="Event discriminator consumed by desktop shell extensions or UI clients."
    )
    task_id: Optional[str] = Field(
        default=None,
        description="Active task identifier associated with the event, if applicable."
    )
    client_id: Optional[str] = Field(
        default=None,
        description="Target or origin client node identifier for network routing."
    )

    agent_name: str = Field(
        default="System",
        description="The specific agent emitting this event (e.g. 'The_Machinist', 'System')."
    )

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp generated at event emission."
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event payload containing telemetry, logs, or intercept parameters."
    )
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/routes.py`

```python
"""
charon/gateway/routes.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: REST API and WebSocket ingress endpoints.
Handles health checks, task queueing, Gatekeeper approval handshakes, WS IPC,
Skill Blueprint inspection & human-in-the-loop Gemini prompt generation,
and mounts sub-routers (Router Control API).
"""

import json
import logging
from pathlib import Path
import secrets
from typing import Any, Dict, Optional
import uuid

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from charon.config import API_KEY_HEADER_NAME, CHARON_API_KEY
from charon.gateway.models import GatekeeperDecision, TaskRequest, TaskResponse, WSEvent
from charon.gateway.routes_router import router as router_control_api
from charon.gateway.ws import manager

logger = logging.getLogger("Charon.Gateway.Routes")

router = APIRouter()

# Mount Sub-Routers
router.include_router(router_control_api)


class SkillRegisterRequest(BaseModel):
    """Payload for registering manually verified skill code generated via Gemini Chat."""
    skill_name: str = Field(..., description="Name of the skill class/module (e.g. dynamic_csv_exporter)")
    action_name: str = Field(..., description="Action name handled by skill (e.g. export_csv_report)")
    code: str = Field(..., description="Python source code implementation for the skill")
    description: str = Field(default="", description="Optional description of skill capabilities")


def _extract_ws_token(websocket: WebSocket, query_api_key: Optional[str]) -> Optional[str]:
    """Extracts API key token from HTTP headers or query parameter fallbacks."""
    custom_header = websocket.headers.get(API_KEY_HEADER_NAME.lower()) if API_KEY_HEADER_NAME else None
    if custom_header:
        return custom_header.strip()

    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    if query_api_key:
        return query_api_key.strip()

    return None


# ============================================================================
# Core Ingress & Health Endpoints
# ============================================================================

@router.get("/v1/health")
async def health_check(request: Request):
    """Returns runtime state, active connection count, and task queue depth."""
    daemon = getattr(request.app.state, "daemon", None)
    queue_depth = 0
    if daemon and hasattr(daemon, "queue") and hasattr(daemon.queue, "qsize"):
        try:
            queue_depth = daemon.queue.qsize()
        except Exception:
            queue_depth = 0

    return {
        "status": "online",
        "service": "Charon Gateway & Core Engine",
        "active_ws_clients": len(manager.active_connections),
        "registered_client_nodes": list(manager.client_sockets.keys()),
        "queue_depth": queue_depth,
    }


@router.post("/v1/task", response_model=TaskResponse)
async def submit_task(request_data: TaskRequest, request: Request):
    """REST ingress endpoint for queuing execution tasks."""
    daemon = getattr(request.app.state, "daemon", None)
    if not daemon or not hasattr(daemon, "queue"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Daemon or Task Queue is currently initializing.",
        )

    task_id = f"task_{uuid.uuid4().hex[:8]}"

    await daemon.queue.put({
        "task_id": task_id,
        "client_id": request_data.client_id,
        "prompt": request_data.prompt,
        "agent_override": request_data.agent_override,
        "context": request_data.context or {},
    })

    return TaskResponse(
        task_id=task_id,
        status="queued",
        assigned_agent=request_data.agent_override,
        message="Task accepted and queued for orchestration.",
    )


@router.post("/v1/gatekeeper/respond")
async def respond_to_gatekeeper(decision: GatekeeperDecision, request: Request):
    """
    Direct resolution endpoint for Gatekeeper Level 2/3 Escalation Matrix.
    Unblocks paused tasks in GatekeeperManager targeting approval_id.
    """
    daemon = getattr(request.app.state, "daemon", None)
    approval_id = decision.approval_id
    user_decision = decision.decision.strip().upper()

    resolved = False
    if daemon and hasattr(daemon, "gatekeeper") and daemon.gatekeeper:
        if hasattr(daemon.gatekeeper, "resolve_intercept"):
            resolved = daemon.gatekeeper.resolve_intercept(approval_id, user_decision)
        elif hasattr(daemon.gatekeeper, "submit_decision"):
            resolved = daemon.gatekeeper.submit_decision(approval_id, user_decision)

    if not resolved:
        logger.warning(f"Gatekeeper response for unknown/expired approval_id: {approval_id}")

    return {
        "status": "acknowledged" if resolved else "expired_or_not_found",
        "approval_id": approval_id,
        "decision": user_decision,
    }


# ============================================================================
# Skill Gap Registry & Blueprint Endpoints (Human-in-the-Loop Gemini Workflow)
# ============================================================================

@router.get("/v1/skills/gaps")
async def get_skill_gaps(request: Request):
    """Returns frequency metrics for tracked diagnostic gaps."""
    registry = getattr(request.app.state, "gap_registry", None)
    if not registry:
        return {"status": "success", "metrics": {}}

    metrics = registry.get_gap_metrics() if hasattr(registry, "get_gap_metrics") else {}
    return {
        "status": "success",
        "metrics": metrics,
    }


@router.get("/v1/skills/blueprints")
async def get_pending_blueprints(request: Request):
    """Returns all queued SkillBlueprint artifacts ready for manual review/forging."""
    registry = getattr(request.app.state, "gap_registry", None)
    if not registry or not hasattr(registry, "list_pending_blueprints"):
        return {"status": "success", "count": 0, "blueprints": []}

    blueprints = registry.list_pending_blueprints()
    dumped = []
    for bp in blueprints:
        if hasattr(bp, "model_dump"):
            dumped.append(bp.model_dump())
        elif hasattr(bp, "dict"):
            dumped.append(bp.dict())
        elif isinstance(bp, dict):
            dumped.append(bp)

    return {
        "status": "success",
        "count": len(dumped),
        "blueprints": dumped,
    }


@router.get("/v1/skills/blueprints/{action_name}/prompt")
async def get_gemini_prompt_for_blueprint(action_name: str, request: Request):
    """
    Formats a SkillBlueprint into a structured Gemini Chat prompt ready to copy-paste.
    Designed for dev environments without direct LLM API keys.
    """
    registry = getattr(request.app.state, "gap_registry", None)
    if not registry or not hasattr(registry, "get_blueprint"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Skill Gap Registry unavailable.",
        )

    blueprint = registry.get_blueprint(action_name)
    if not blueprint:
        raise HTTPException(
            status_code=404,
            detail=f"No pending SkillBlueprint found for action '{action_name}'.",
        )

    consumed = ", ".join(blueprint.consumed_artifacts) if getattr(blueprint, "consumed_artifacts", None) else "None"
    produced = ", ".join(blueprint.produced_artifacts) if getattr(blueprint, "produced_artifacts", None) else "None"
    code_draft = getattr(blueprint, "code_draft", None) or "# No dynamic draft recorded."

    ticks = "```"
    formatted_prompt = (
        "You are an expert Python engineer crafting a dynamic skill for the Charon AI Agent Ecosystem.\n\n"
        f"### Target Action Name:\n`{blueprint.action_name}`\n\n"
        "### Skill Blueprint Specifications:\n"
        f"* **Suggested Skill Class Name:** `{getattr(blueprint, 'suggested_skill_name', 'DynamicSkill')}`\n"
        f"* **Description:** {getattr(blueprint, 'description', '')}\n"
        f"* **Consumed Context Inputs:** {consumed}\n"
        f"* **Produced Output Artifacts:** {produced}\n"
        f"* **Sample Dynamic Call:** `{getattr(blueprint, 'sample_call', '')}`\n\n"
        "### Initial Working Code Prototype:\n"
        f"{ticks}python\n{code_draft}\n{ticks}\n\n"
        "### Implementation Requirements:\n"
        "1. Write a clean, complete, and production-ready Python skill module.\n"
        "2. Provide standard input/output validation.\n"
        "3. Ensure it runs statelessly and handles execution exceptions gracefully.\n"
        "4. Return ONLY valid Python code enclosed in a ```python markdown code block."
    )

    return {
        "status": "success",
        "action_name": action_name,
        "copy_paste_prompt": formatted_prompt,
    }


@router.delete("/v1/skills/gaps/{action_name}")
async def reset_skill_gap(action_name: str, request: Request):
    """Resets the failure counter and removes pending blueprint for an action."""
    registry = getattr(request.app.state, "gap_registry", None)
    if registry and hasattr(registry, "reset_gap_counter"):
        registry.reset_gap_counter(action_name)
    return {
        "status": "success",
        "message": f"Gap counter and pending blueprint reset for action '{action_name}'.",
    }


@router.post("/v1/skills/register")
async def register_manual_skill(skill_req: SkillRegisterRequest, request: Request):
    """
    Accepts Python code generated via Gemini Chat, saves it to disk in charon/skills/dynamic/,
    triggers a live scan in SkillLibrarian, and resets the gap counter in SkillGapRegistry.
    """
    registry = getattr(request.app.state, "gap_registry", None)
    if registry and hasattr(registry, "reset_gap_counter"):
        registry.reset_gap_counter(skill_req.action_name)

    skills_dir = Path("charon/skills/dynamic")
    skills_dir.mkdir(parents=True, exist_ok=True)

    file_path = skills_dir / f"{skill_req.skill_name.lower()}.py"
    file_path.write_text(skill_req.code, encoding="utf-8")

    engine = getattr(request.app.state, "engine", None)
    if engine and hasattr(engine, "librarian") and engine.librarian:
        try:
            if hasattr(engine.librarian, "scan_and_register_dynamic_skills"):
                engine.librarian.scan_and_register_dynamic_skills()
        except Exception as err:
            logger.warning(f"Live librarian reload notification skipped: {err}")

    logger.info(f"[Gateway] Skill '{skill_req.skill_name}' successfully ingested into {file_path}.")
    return {
        "status": "success",
        "action_name": skill_req.action_name,
        "skill_name": skill_req.skill_name,
        "saved_path": str(file_path),
        "message": f"Skill '{skill_req.skill_name}' successfully ingested, written to {file_path}, and registered.",
    }


# ============================================================================
# WebSocket Stream
# ============================================================================

@router.websocket("/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
    api_key: Optional[str] = Query(None, alias="api_key"),
):
    """Full-duplex WebSocket stream for desktop extension, CLI, and real-time telemetry."""
    token = _extract_ws_token(websocket, api_key)

    # Validate token if CHARON_API_KEY is defined
    if CHARON_API_KEY:
        if not token or not secrets.compare_digest(token, CHARON_API_KEY):
            logger.warning(f"WebSocket connection rejected for client '{client_id}': Unauthorized.")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await manager.connect(websocket, client_id=client_id)
    try:
        await manager.send_event(
            websocket,
            WSEvent.model_construct(
                event_type="status_change",
                agent_name="System",
                client_id=client_id,
                data={
                    "status": "connected",
                    "client_id": client_id,
                    "message": "Connected to Charon Gateway Stream",
                },
            ),
        )

        while True:
            raw_data = await websocket.receive_text()
            if not raw_data.strip():
                continue

            try:
                msg = json.loads(raw_data)
                action = msg.get("action") or msg.get("event_type")
                daemon = getattr(websocket.app.state, "daemon", None)

                if action in ("ping", "heartbeat"):
                    await manager.send_event(
                        websocket,
                        WSEvent.model_construct(
                            event_type="status_change",
                            agent_name="System",
                            client_id=client_id,
                            data={"status": "alive", "client_id": client_id},
                        ),
                    )
                elif action == "submit_task":
                    task_id = f"task_{uuid.uuid4().hex[:8]}"
                    effective_client_id = client_id or msg.get("client_id")
                    if daemon and hasattr(daemon, "queue"):
                        await daemon.queue.put({
                            "task_id": task_id,
                            "client_id": effective_client_id,
                            "prompt": msg.get("prompt", ""),
                            "agent_override": msg.get("agent_override"),
                            "context": msg.get("context", {}),
                        })
                        await manager.send_event(
                            websocket,
                            WSEvent.model_construct(
                                event_type="status_change",
                                task_id=task_id,
                                agent_name="System",
                                client_id=effective_client_id,
                                data={"status": "queued", "task_id": task_id},
                            ),
                        )
                elif action in ("gatekeeper_respond", "approval_response"):
                    approval_id = msg.get("approval_id")
                    decision_str = msg.get("decision", "REJECTED").upper()
                    if daemon and hasattr(daemon, "gatekeeper") and daemon.gatekeeper and approval_id:
                        if hasattr(daemon.gatekeeper, "resolve_intercept"):
                            daemon.gatekeeper.resolve_intercept(approval_id, decision_str)
                        elif hasattr(daemon.gatekeeper, "submit_decision"):
                            daemon.gatekeeper.submit_decision(approval_id, decision_str)

            except json.JSONDecodeError:
                logger.debug(f"Received non-JSON raw WS frame: {raw_data[:50]}")
            except Exception as e:
                logger.error(f"Error handling WS frame from client '{client_id}': {e}", exc_info=True)

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: '{client_id}'")
    except Exception as e:
        logger.error(f"Unexpected WebSocket loop closure for client '{client_id}': {e}")
    finally:
        manager.disconnect(websocket)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/routes_router.py`

```python
"""
charon/gateway/routes_router.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Gateway Router Control endpoints.
Provides APIs for managing dynamic triage prompts, priority weighting, tool toggles,
hard routing rules, and triage telemetry debugging.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status

from charon.gateway.models import (
    AgentManifestResponse,
    AgentUpdateRequest,
    DynamicRuleRequest,
    ToolPatchRequest,
    WSEvent,
)
from charon.gateway.ws import manager

logger = logging.getLogger("Charon.Gateway.RoutesRouter")

router = APIRouter(prefix="/v1/router", tags=["Dynamic Router"])


def _get_engine(request: Request):
    """Helper to retrieve OrchestrationEngine or raise clean HTTP 503 error."""
    engine = getattr(request.app.state, "engine", None)
    if not engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OrchestrationEngine unavailable or still initializing.",
        )
    return engine


# ============================================================================
# Agent Manifest & Priority Weight Endpoints
# ============================================================================

@router.get("/agents", response_model=Dict[str, Any])
async def list_router_agents(request: Request):
    """
    Retrieves all registered agents, capability manifests, active tool schemas,
    priority weights, and keyword override triggers.
    """
    engine = _get_engine(request)
    if not hasattr(engine, "librarian") or not engine.librarian:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SkillLibrarian unavailable on Core Engine.",
        )

    manifests = engine.librarian.get_all_agent_manifests()
    return {
        "status": "success",
        "count": len(manifests),
        "agents": manifests,
    }


@router.get("/agents/{agent_id}", response_model=AgentManifestResponse)
async def get_router_agent(agent_id: str, request: Request):
    """Retrieves routing configuration details for a single agent."""
    engine = _get_engine(request)
    if not hasattr(engine, "librarian") or not engine.librarian:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SkillLibrarian unavailable on Core Engine.",
        )

    manifest = engine.librarian.get_agent_manifest(agent_id)
    if not manifest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found in registry.",
        )

    return manifest


@router.put("/agents/{agent_id}", response_model=Dict[str, Any])
async def update_router_agent(agent_id: str, update_req: AgentUpdateRequest, request: Request):
    """
    Updates an agent's dynamic description, system prompt, priority weight,
    or shortcut triggers in SQLite and hot-reloads the in-memory cache.
    """
    engine = _get_engine(request)
    librarian = engine.librarian

    existing = librarian.get_agent_manifest(agent_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found.",
        )

    if hasattr(update_req, "model_dump"):
        update_data = update_req.model_dump(exclude_unset=True)
    elif hasattr(update_req, "dict"):
        update_data = update_req.dict(exclude_unset=True)
    else:
        update_data = dict(update_req)

    success = librarian.update_agent_manifest(agent_id, update_data)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist update for agent '{agent_id}'.",
        )

    librarian.reload_agent_manifest(agent_id)

    await manager.broadcast(
        WSEvent.model_construct(
            event_type="router_agent_updated",
            agent_name="System",
            data={
                "agent_id": agent_id,
                "updated_fields": list(update_data.keys()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    )

    logger.info(f"[Router API] Hot-reloaded agent '{agent_id}' configuration.")
    return {
        "status": "success",
        "agent_id": agent_id,
        "message": f"Agent '{agent_id}' manifest updated and reloaded in runtime engine.",
        "updated_fields": update_data,
    }


# ============================================================================
# Dynamic Tool Schemas & Toggling Endpoints
# ============================================================================

@router.patch("/agents/{agent_id}/tools", response_model=Dict[str, Any])
async def toggle_agent_tool(agent_id: str, patch_req: ToolPatchRequest, request: Request):
    """Dynamically enables or disables a specific tool for an agent at runtime."""
    engine = _get_engine(request)
    librarian = engine.librarian

    updated = librarian.set_tool_status(
        agent_id=agent_id,
        tool_name=patch_req.tool_name,
        enabled=patch_req.enabled,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to set tool '{patch_req.tool_name}' status for agent '{agent_id}'.",
        )

    await manager.broadcast(
        WSEvent.model_construct(
            event_type="router_tool_toggled",
            agent_name="System",
            data={
                "agent_id": agent_id,
                "tool_name": patch_req.tool_name,
                "enabled": patch_req.enabled,
            },
        )
    )

    return {
        "status": "success",
        "agent_id": agent_id,
        "tool_name": patch_req.tool_name,
        "enabled": patch_req.enabled,
        "message": f"Tool '{patch_req.tool_name}' set to enabled={patch_req.enabled} for agent '{agent_id}'.",
    }


# ============================================================================
# Dynamic Shortcut & Hard Override Rules Endpoints
# ============================================================================

@router.get("/rules", response_model=Dict[str, Any])
async def list_routing_rules(request: Request):
    """Lists all active shortcut rule overrides (e.g., '#archivist' -> forced dispatch)."""
    engine = _get_engine(request)
    rules = engine.intent_parser.get_override_rules() if hasattr(engine, "intent_parser") else []

    return {
        "status": "success",
        "count": len(rules),
        "rules": rules,
    }


@router.post("/rules", response_model=Dict[str, Any])
async def create_routing_rule(rule_req: DynamicRuleRequest, request: Request):
    """Creates a new hard shortcut override rule in the IntentParser."""
    engine = _get_engine(request)

    if not hasattr(engine, "intent_parser"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="IntentParser missing from core engine.",
        )

    rule_id = engine.intent_parser.add_override_rule(
        trigger=rule_req.trigger,
        agent_id=rule_req.agent_id,
        description=rule_req.description,
    )

    return {
        "status": "success",
        "rule_id": rule_id,
        "trigger": rule_req.trigger,
        "agent_id": rule_req.agent_id,
        "message": f"Shortcut rule created: '{rule_req.trigger}' -> '{rule_req.agent_id}'",
    }


@router.delete("/rules/{rule_id}", response_model=Dict[str, Any])
async def delete_routing_rule(rule_id: str, request: Request):
    """Deletes an active hard shortcut override rule."""
    engine = _get_engine(request)

    if not hasattr(engine, "intent_parser"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="IntentParser missing from core engine.",
        )

    removed = engine.intent_parser.remove_override_rule(rule_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule ID '{rule_id}' not found.",
        )

    return {
        "status": "success",
        "rule_id": rule_id,
        "message": f"Shortcut rule '{rule_id}' removed.",
    }


# ============================================================================
# Triage Logs & Telemetry Endpoints
# ============================================================================

@router.get("/telemetry/recent", response_model=Dict[str, Any])
async def get_recent_triage_logs(request: Request, limit: int = 20):
    """
    Retrieves Pass 1 triage evaluation logs, including candidate scores and
    LLM confidence ratings for recent requests.
    """
    state_mgr = getattr(request.app.state, "state_manager", None) or getattr(request.app.state, "state_mgr", None)

    logs = []
    if state_mgr and hasattr(state_mgr, "get_recent_triage_evaluations"):
        try:
            logs = state_mgr.get_recent_triage_evaluations(limit=limit)
        except Exception as err:
            logger.warning(f"Failed to query recent triage evaluations: {err}")

    return {
        "status": "success",
        "count": len(logs),
        "logs": logs,
    }
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/telemetry.py`

```python
"""
charon/gateway/telemetry.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Overseer Telemetry & Modular Idle Ticker Reporter
Background loop sending system status updates, backend engine ping checks,
and dynamic ticker feeds via WebSockets.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional
import ollama

from charon.config import OLLAMA_HOST
from charon.core.state import StateManager
from charon.gateway.models import WSEvent
from charon.gateway.ticker.engine import ticker_engine, TickerEngine
from charon.gateway.ticker.providers.state_provider import StateManagerTickerProvider
from charon.gateway.ws import manager

logger = logging.getLogger("Charon.Gateway.Telemetry")


class TelemetryReporter:
    """Monitors engine connectivity, system health telemetry, and broadcasts dynamic ticker feeds."""

    def __init__(
        self,
        queue_provider: Callable[[], int],
        gatekeeper_status_provider: Callable[[], bool],
        task_provider: Callable[[], Optional[str]],
        state_manager: Optional[StateManager] = None,
        engine: Optional[TickerEngine] = None,
    ) -> None:
        self.ollama_client = ollama.AsyncClient(host=OLLAMA_HOST)
        self.get_queue_depth = queue_provider
        self.is_awaiting_gatekeeper = gatekeeper_status_provider
        self.get_current_task = task_provider
        self.state_manager = state_manager
        self.ticker_engine = engine or ticker_engine
        self.last_engine_state: Optional[bool] = None

        # Register default StateManager provider if state_manager exists
        if self.state_manager:
            self.ticker_engine.register_provider(
                StateManagerTickerProvider(self.state_manager)
            )

    async def verify_engine(self, retries: int = 3, delay: float = 2.0, timeout: float = 4.0) -> bool:
        """Ping Ollama host to confirm inference engine availability with explicit async timeout."""
        for attempt in range(1, retries + 1):
            try:
                await asyncio.wait_for(self.ollama_client.list(), timeout=timeout)
                return True
            except (asyncio.TimeoutError, Exception) as err:
                logger.debug(f"Engine health check attempt {attempt}/{retries} failed: {err}")
                if attempt < retries:
                    await asyncio.sleep(delay)
        return False

    def _safe_eval(self, provider: Callable[[], Any], fallback: Any) -> Any:
        """Helper to defensively execute telemetry metric providers without crashing the loop."""
        try:
            return provider()
        except Exception as e:
            provider_name = getattr(provider, "__name__", str(provider))
            logger.warning(f"Telemetry metric extraction failed for {provider_name}: {e}")
            return fallback

    async def start_loop(self, interval: float = 5.0) -> None:
        """Run overseer telemetry and idle ticker background reporting loop."""
        logger.info("Overseer telemetry and ticker loop initialized.")

        try:
            while True:
                try:
                    engine_online = await self.verify_engine(retries=1, delay=1.0, timeout=4.0)

                    # State transition alerts
                    if self.last_engine_state is not None:
                        if not engine_online and self.last_engine_state:
                            await manager.broadcast(
                                WSEvent(
                                    event_type="system_alert",
                                    agent_name="Overseer",
                                    task_id=None,
                                    data={
                                        "severity": "CRITICAL",
                                        "title": "Engine Disconnected",
                                        "message": f"Ollama backend ({OLLAMA_HOST}) unreachable!",
                                    },
                                )
                            )
                        elif engine_online and not self.last_engine_state:
                            await manager.broadcast(
                                WSEvent(
                                    event_type="system_alert",
                                    agent_name="Overseer",
                                    task_id=None,
                                    data={
                                        "severity": "INFO",
                                        "title": "Engine Restored",
                                        "message": "Ollama connection restored.",
                                    },
                                )
                            )

                    self.last_engine_state = engine_online

                    current_task = self._safe_eval(self.get_current_task, None)
                    queue_depth = self._safe_eval(self.get_queue_depth, 0)
                    gatekeeper_active = self._safe_eval(self.is_awaiting_gatekeeper, False)

                    is_idle = (current_task in (None, "Idle", "")) and queue_depth == 0

                    # Retrieve active slide safely
                    current_slide = None
                    try:
                        current_slide = await self.ticker_engine.get_active_slide()
                    except Exception as slide_err:
                        logger.debug(f"Failed to retrieve active ticker slide: {slide_err}")

                    slide_data = None
                    if current_slide:
                        if hasattr(current_slide, "model_dump"):
                            slide_data = current_slide.model_dump()
                        elif hasattr(current_slide, "dict"):
                            slide_data = current_slide.dict()
                        elif isinstance(current_slide, dict):
                            slide_data = current_slide

                    active_clients_count = 0
                    if hasattr(manager, "active_connections"):
                        try:
                            active_clients_count = len(manager.active_connections)
                        except Exception:
                            pass

                    telemetry_data = {
                        "status": "IDLE" if is_idle else "BUSY",
                        "engine_online": engine_online,
                        "queue_depth": queue_depth,
                        "active_clients": active_clients_count,
                        "awaiting_gatekeeper": gatekeeper_active,
                        "current_task": current_task or "Idle",
                        "current_slide": slide_data,
                    }

                    # 1. Primary Overseer Report
                    await manager.broadcast(
                        WSEvent(
                            event_type="overseer_report",
                            agent_name="Overseer",
                            task_id=current_task if isinstance(current_task, str) else None,
                            data=telemetry_data,
                        )
                    )

                    # 2. Dedicated Heartbeat Event for Top-Bar Extension Ticker
                    if is_idle:
                        await manager.broadcast(
                            WSEvent(
                                event_type="heartbeat_idle",
                                agent_name="Overseer",
                                task_id=None,
                                data={
                                    "status": "IDLE",
                                    "active_agent": None,
                                    "slide": slide_data,
                                    "default_text": "⚡ Charon: Ready",
                                },
                            )
                        )

                except Exception as e:
                    logger.error(f"Overseer reporter unexpected loop error: {e}", exc_info=True)

                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Overseer telemetry loop cancelled.")
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/ticker/__init__.py`

```python

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/ticker/base.py`

```python
"""
charon/gateway/ticker/base.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Core data models and abstract base class for TickerEngine plugins.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TickerSlide(BaseModel):
    """Represents a single visual ticker slide frame broadcast to clients."""

    provider_id: str = Field(
        ...,
        description="Unique identifier of the originating provider (e.g. 'task_tracker')."
    )
    display_text: str = Field(
        ...,
        description="Formatted text rendered in the top bar (e.g. '📌 14:30: KiCad DRC Review')."
    )
    priority: int = Field(
        default=0,
        description="Priority level. 0 = Normal rotation. >0 = Priority takeover (e.g., pinned task)."
    )
    duration_seconds: int = Field(
        default=5,
        description="Suggested display duration in seconds."
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary provider context payload associated with the slide."
    )


class BaseTickerProvider(ABC):
    """Abstract Base Class for all dynamic ticker provider plugins."""

    def __init__(self, provider_id: str, enabled: bool = True) -> None:
        self.provider_id = provider_id
        self.enabled = enabled

    @abstractmethod
    async def get_slides(self) -> List[TickerSlide]:
        """
        Fetch active ticker slides from this provider.

        Returns an empty list if the provider has no active information to display.
        """
        pass
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/ticker/engine.py`

```python
"""
charon/gateway/ticker/engine.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: TickerEngine manager for dynamic slide collection, prioritization, and rotation.
"""

import logging
from typing import Dict, List, Optional
from charon.gateway.ticker.base import BaseTickerProvider, TickerSlide

logger = logging.getLogger("Charon.Gateway.TickerEngine")


class TickerEngine:
    """Manages ticker provider plugins, handles round-robin rotation, and priority hijacking."""

    def __init__(self) -> None:
        self._providers: Dict[str, BaseTickerProvider] = {}
        self._rotation_index: int = 0

    def register_provider(self, provider: BaseTickerProvider) -> None:
        """Register a new ticker provider plugin."""
        self._providers[provider.provider_id] = provider
        logger.info(f"Registered TickerProvider: '{provider.provider_id}'")

    def unregister_provider(self, provider_id: str) -> None:
        """Unregister a provider plugin by ID."""
        if provider_id in self._providers:
            del self._providers[provider_id]
            logger.info(f"Unregistered TickerProvider: '{provider_id}'")

    async def get_active_slide(self) -> Optional[TickerSlide]:
        """
        Collects active slides from all enabled providers.

        Behavior:
        1. If any slide has priority > 0, returns the highest-priority slide immediately.
        2. Otherwise, cycles round-robin through normal slides across calls.
        """
        enabled_providers = [p for p in self._providers.values() if p.enabled]
        if not enabled_providers:
            return None

        all_slides: List[TickerSlide] = []

        for provider in enabled_providers:
            try:
                slides = await provider.get_slides()
                if slides:
                    all_slides.extend(slides)
            except Exception as e:
                logger.warning(
                    f"Ticker provider '{provider.provider_id}' failed during slide collection: {e}"
                )

        if not all_slides:
            return None

        # Check for high-priority slides (e.g., pinned tasks, critical alerts)
        priority_slides = [s for s in all_slides if s.priority > 0]
        if priority_slides:
            priority_slides.sort(key=lambda s: s.priority, reverse=True)
            return priority_slides[0]

        # Round-robin rotation for standard (priority == 0) slides
        self._rotation_index %= len(all_slides)
        selected_slide = all_slides[self._rotation_index]
        self._rotation_index = (self._rotation_index + 1) % len(all_slides)

        return selected_slide


# Global TickerEngine singleton instance
ticker_engine = TickerEngine()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/ticker/providers/__init__.py`

```python

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/ticker/providers/state_provider.py`

```python
"""
charon/gateway/ticker/providers/state_provider.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Ticker provider adapter for SQLite StateManager items.
"""

import logging
from typing import List, Optional
from charon.core.state import StateManager
from charon.gateway.ticker.base import BaseTickerProvider, TickerSlide

logger = logging.getLogger("Charon.Gateway.TickerProvider.StateManager")


class StateManagerTickerProvider(BaseTickerProvider):
    """Adapts StateManager active ticker db records into TickerSlide objects."""

    def __init__(self, state_manager: Optional[StateManager] = None) -> None:
        super().__init__(provider_id="state_manager", enabled=True)
        self.state_manager = state_manager

    async def get_slides(self) -> List[TickerSlide]:
        if not self.state_manager:
            return []

        try:
            items = await self.state_manager.get_active_ticker_items(limit=10)
            slides: List[TickerSlide] = []

            for item in items:
                # Support custom text fields or fallback formatted string
                text = item.get("display_text") or item.get("message") or str(item)
                priority = item.get("priority", 0)

                slides.append(
                    TickerSlide(
                        provider_id=self.provider_id,
                        display_text=text,
                        priority=priority,
                        data=item,
                    )
                )
            return slides
        except Exception as err:
            logger.warning(f"Failed to fetch StateManager ticker items: {err}")
            return []
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/ticker/providers/task_tracker.py`

```python
"""
charon/gateway/ticker/providers/task_tracker.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Task Tracker ticker provider with priority-weighted display frequency rules.
"""

import logging
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from charon.gateway.ticker.base import BaseTickerProvider, TickerSlide

logger = logging.getLogger("Charon.Gateway.TickerProvider.TaskTracker")


class TaskItem(BaseModel):
    """Schema representing a tracked task item."""

    id: str = Field(..., description="Unique task identifier.")
    title: str = Field(..., description="Short descriptive title of the task.")
    priority: Literal["high", "medium", "low"] = Field(
        default="low",
        description="Task priority level: 'high', 'medium', or 'low'."
    )
    pinned: bool = Field(
        default=True,
        description="Whether this task should be displayed on the ticker."
    )
    completed: bool = Field(
        default=False,
        description="Completion status of the task."
    )


class TaskTrackerTickerProvider(BaseTickerProvider):
    """
    Plug-and-play TickerProvider for task lists with frequency-weighted rules:
    - High Priority: Pinned and displayed with top frequency (~75% of priority slots).
    - Medium Priority: Pinned and displayed with lower frequency (~25% of priority slots).
    - Low Priority: Never individually pinned. Included in total task summary counts.
    """

    def __init__(self, db_client: Optional[Any] = None) -> None:
        super().__init__(provider_id="task_tracker", enabled=True)
        self.db_client = db_client
        self._tasks: Dict[str, TaskItem] = {}
        self._cycle_counter: int = 0
        self._high_index: int = 0
        self._med_index: int = 0

    def add_task(self, task: TaskItem) -> None:
        """Add or update a task item in the provider memory cache."""
        self._tasks[task.id] = task
        logger.debug(f"TaskTracker: Added/Updated task '{task.id}' [{task.priority.upper()}]")

    def complete_task(self, task_id: str) -> bool:
        """Mark a task as completed so it drops off active ticker rotation."""
        if task_id in self._tasks:
            self._tasks[task_id].completed = True
            logger.debug(f"TaskTracker: Marked task '{task_id}' as completed.")
            return True
        return False

    async def _fetch_active_tasks(self) -> List[TaskItem]:
        """
        Fetch incomplete tasks. Can be extended to query SQLite directly.
        """
        if self.db_client:
            # SQLite / DB extraction hook can be implemented here
            pass
        return [t for t in self._tasks.values() if not t.completed]

    async def get_slides(self) -> List[TickerSlide]:
        tasks = await self._fetch_active_tasks()
        if not tasks:
            return []

        # Filter by priority and pin status
        high_tasks = [t for t in tasks if t.priority == "high" and t.pinned]
        med_tasks = [t for t in tasks if t.priority == "medium" and t.pinned]
        low_tasks = [t for t in tasks if t.priority == "low"]

        slides: List[TickerSlide] = []
        self._cycle_counter += 1

        # ----------------------------------------------------------------------
        # Priority Weighted Frequency Allocation:
        # - 3 out of 4 cycles (75%): Yield High priority task (if available).
        # - 1 out of 4 cycles (25%): Interject Medium priority task (if available).
        # - Fallbacks ensure continuous display if only one category exists.
        # ----------------------------------------------------------------------
        selected_task: Optional[TaskItem] = None
        is_medium_turn = (self._cycle_counter % 4 == 0)

        if is_medium_turn and med_tasks:
            self._med_index %= len(med_tasks)
            selected_task = med_tasks[self._med_index]
            self._med_index = (self._med_index + 1) % len(med_tasks)
        elif high_tasks:
            self._high_index %= len(high_tasks)
            selected_task = high_tasks[self._high_index]
            self._high_index = (self._high_index + 1) % len(high_tasks)
        elif med_tasks:
            self._med_index %= len(med_tasks)
            selected_task = med_tasks[self._med_index]
            self._med_index = (self._med_index + 1) % len(med_tasks)

        # 1. Pinned Task Slide (High or Medium)
        if selected_task:
            is_high = selected_task.priority == "high"
            prefix = "🔥 [HIGH]" if is_high else "📌 [MED]"

            slides.append(
                TickerSlide(
                    provider_id=self.provider_id,
                    display_text=f"{prefix} {selected_task.title}",
                    priority=10 if is_high else 8,  # >0 triggers priority takeover in TickerEngine
                    duration_seconds=5,
                    data=selected_task.model_dump(),
                )
            )

        # 2. General Summary Task Slide (Standard round-robin rotation, priority=0)
        total_active = len(tasks)
        high_count = len([t for t in tasks if t.priority == "high"])
        med_count = len([t for t in tasks if t.priority == "medium"])
        low_count = len(low_tasks)

        slides.append(
            TickerSlide(
                provider_id=self.provider_id,
                display_text=f"📋 Tasks: {total_active} ({high_count}H / {med_count}M / {low_count}L)",
                priority=0,
                duration_seconds=5,
                data={
                    "total": total_active,
                    "high": high_count,
                    "medium": med_count,
                    "low": low_count,
                },
            )
        )

        return slides
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/gateway/ws.py`

```python
"""
charon/gateway/ws.py
System Version: v0.1.0 | File Revision: 1.2.0

Module: WebSocket connection pool manager and targeted event bus.
"""

import logging
from typing import Any, Dict, List, Optional, Union
from fastapi import WebSocket
from charon.gateway.models import WSEvent

logger = logging.getLogger("Charon.Gateway.WS")


def _dump_event(event: Union[WSEvent, Dict[str, Any]]) -> Dict[str, Any]:
    """Safely serializes WSEvent models or dict payloads across Pydantic v1 and v2."""
    if isinstance(event, dict):
        return event

    if hasattr(event, "model_dump"):
        try:
            return event.model_dump(mode="json")
        except Exception:
            return event.model_dump()

    if hasattr(event, "dict"):
        return event.dict()

    return dict(event)


class ConnectionManager:
    """Manages active WebSocket client connections and targeted event routing."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self.client_sockets: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, client_id: Optional[str] = None) -> None:
        """Accepts and registers a new socket connection."""
        await websocket.accept()
        if websocket not in self.active_connections:
            self.active_connections.append(websocket)

        if client_id:
            self.client_sockets.setdefault(client_id, [])
            if websocket not in self.client_sockets[client_id]:
                self.client_sockets[client_id].append(websocket)
            logger.info(f"Client registered to event bus: '{client_id}'")

    def disconnect(self, websocket: WebSocket) -> None:
        """Removes a closed socket from active connection structures."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        for client_id, sockets in list(self.client_sockets.items()):
            if websocket in sockets:
                sockets.remove(websocket)
                if not sockets:
                    self.client_sockets.pop(client_id, None)
                    logger.debug(f"All connections closed for client_id '{client_id}'. Client unregistered.")

    def is_client_connected(self, client_id: str) -> bool:
        """Helper checking if a client_id has at least one active WebSocket socket."""
        return bool(self.client_sockets.get(client_id))

    async def send_event(self, websocket: WebSocket, event: Union[WSEvent, Dict[str, Any]]) -> bool:
        """Sends a JSON event directly to a single socket safely."""
        try:
            payload = _dump_event(event)
            await websocket.send_json(payload)
            return True
        except Exception as e:
            logger.debug(f"Error sending to socket: {e}")
            self.disconnect(websocket)
            return False

    async def broadcast(self, event: Union[WSEvent, Dict[str, Any]]) -> None:
        """Broadcasts a system-wide event to ALL connected network nodes."""
        payload = _dump_event(event)
        disconnected: List[WebSocket] = []

        for connection in list(self.active_connections):
            try:
                await connection.send_json(payload)
            except Exception as e:
                logger.debug(f"Error broadcasting to socket: {e}")
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def send_to_client(self, client_id: str, event: Union[WSEvent, Dict[str, Any]]) -> None:
        """Unicasts an event directly to sockets registered under a specific client_id."""
        sockets = self.client_sockets.get(client_id, [])
        if not sockets:
            event_type = getattr(event, "event_type", None) or (
                event.get("event_type") if isinstance(event, dict) else "unknown"
            )
            logger.warning(
                f"No active WebSocket connection registered for client_id '{client_id}'. "
                f"Event type '{event_type}' dropped to prevent cross-client broadcast leakage."
            )
            return

        payload = _dump_event(event)
        disconnected: List[WebSocket] = []

        for ws in list(sockets):
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.debug(f"Error sending to client socket '{client_id}': {e}")
                disconnected.append(ws)

        for conn in disconnected:
            self.disconnect(conn)


# Shared Singleton Instance
manager = ConnectionManager()
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/skill_forge_cli.py`

```python
"""
charon/skill_forge_cli.py
System Version: v0.1.0 | File Revision: 3.0.0

Backwards-compatibility shim re-exporting Charon Skill Forge CLI functionality
from its consolidated home at `charon.cli.librarian.forge`.
"""

import sys
from charon.cli.librarian.forge import (
    build_parser,
    fetch_open_gaps,
    forge_skill_scaffold,
    main,
    promote_and_resolve_gap,
    register_disk_skills,
    sync_db,
)

__all__ = [
    "fetch_open_gaps",
    "forge_skill_scaffold",
    "register_disk_skills",
    "sync_db",
    "promote_and_resolve_gap",
    "build_parser",
    "main",
]

if __name__ == "__main__":
    sys.exit(main())
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/telemetry/__init__.py`

```python
"""
charon/telemetry/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Telemetry Package Exports.
"""

from charon.telemetry.trace import TraceEvent, TraceEventType, TelemetryBus, telemetry_bus
from charon.telemetry.viewer import RichTraceViewer, main as run_viewer

__all__ = [
    "TraceEvent",
    "TraceEventType",
    "TelemetryBus",
    "telemetry_bus",
    "RichTraceViewer",
    "run_viewer",
]

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/telemetry/trace.py`

```python
"""
charon/telemetry/trace.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Execution Trace Schemas and Real-Time Event Bus.
Captures agent chain-of-thought reasoning, contract evaluations, step outcomes,
and handoff exceptions in memory without writing noise to persistent database ledgers.
"""

from enum import Enum
import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field


class TraceEventType(str, Enum):
    INITIALIZATION = "INITIALIZATION"
    PROBE = "PROBE"
    NEGOTIATION = "NEGOTIATION"
    THINKING = "THINKING"
    EXECUTION = "EXECUTION"
    EXECUTION_START = "EXECUTION_START"
    EXECUTION_END = "EXECUTION_END"
    HANDOFF = "HANDOFF"
    ESCALATION = "ESCALATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TraceEvent(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    event_type: TraceEventType
    agent_name: str
    action: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    reasoning_chunk: Optional[str] = None
    duration_ms: Optional[float] = None


class ExecutionTrace(BaseModel):
    trace_id: str
    original_prompt: str
    start_time: float = Field(default_factory=time.time)
    end_time: Optional[float] = None
    events: List[TraceEvent] = Field(default_factory=list)
    active_agent: str = "Coordinator"
    status: str = "IN_PROGRESS"


class TelemetryBus:
    """Ephemeral pub/sub event bus streaming trace events to subscribers (e.g., CLI viewer)."""

    def __init__(self) -> None:
        self._listeners: List[Callable[[TraceEvent], None]] = []
        self._current_trace: Optional[ExecutionTrace] = None

    def start_trace(self, trace_id: str, prompt: str) -> ExecutionTrace:
        self._current_trace = ExecutionTrace(trace_id=trace_id, original_prompt=prompt)
        self.emit(
            TraceEvent(
                event_type=TraceEventType.INITIALIZATION,
                agent_name="Coordinator",
                details={"prompt": prompt},
            )
        )
        return self._current_trace

    def subscribe(self, listener: Callable[[TraceEvent], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[TraceEvent], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def emit(self, event: TraceEvent) -> None:
        if self._current_trace:
            self._current_trace.events.append(event)
            self._current_trace.active_agent = event.agent_name

        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass

    @property
    def current_trace(self) -> Optional[ExecutionTrace]:
        return self._current_trace


# Global Singleton Telemetry Bus
telemetry_bus = TelemetryBus()

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/telemetry/viewer.py`

```python
"""
charon/telemetry/viewer.py
System Version: v0.1.0 | File Revision: 1.5.0

Module: Real-Time Terminal Telemetry Viewer using Rich & WebSockets.
Renders live agent reasoning streams, handoff exceptions, contract outcomes,
and state changes in an interactive multi-panel interface across process boundaries.
Handles execution safely inside existing asyncio event loops with automatic reconnection.
"""

import asyncio
import concurrent.futures
from datetime import datetime
import json
import os
import threading
import time
from typing import List, Optional

import websockets
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from charon.config import CHARON_API_KEY
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

DEFAULT_WS_URL = os.getenv("CHARON_WS_URL", "ws://localhost:8000/v1/ws")


class RichTraceViewer:
    """Terminal dashboard for real-time Coordinator & Agent reasoning monitoring."""

    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or Console()
        self._live: Optional[Live] = None
        self._lock = threading.Lock()
        self.raw_prompt: str = ""
        self.active_agent: str = "Coordinator"
        self.current_action: str = "Initializing..."
        self.cot_text: str = ""
        self.history: List[Text] = []

    def start(self, prompt: str = "Live Daemon Telemetry Session") -> None:
        """Starts the live dynamic terminal layout."""
        self.raw_prompt = prompt
        self.cot_text = ""
        self.history.clear()
        telemetry_bus.subscribe(self.on_event)

        layout = self._build_layout()
        self._live = Live(
            layout,
            console=self.console,
            refresh_per_second=10,
            screen=False,
            auto_refresh=True,
        )
        self._live.start()

    def stop(self) -> None:
        """Stops live telemetry rendering."""
        telemetry_bus.unsubscribe(self.on_event)
        if self._live:
            self._live.stop()
            self._live = None

    def on_event(self, event: TraceEvent) -> None:
        """Callback processing incoming telemetry events safely."""
        with self._lock:
            if event.agent_name and event.agent_name != "Unknown":
                self.active_agent = event.agent_name

            if event.action:
                self.current_action = event.action

            # 1. Handle Chain-of-Thought Stream Chunks
            if event.event_type == TraceEventType.THINKING and event.reasoning_chunk:
                self.cot_text += event.reasoning_chunk

            # 2. Handle Major State Events
            timestamp = getattr(event, "timestamp", time.time())
            timestamp_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S.%f")[:-3]
            evt_name = event.event_type.name if hasattr(event.event_type, "name") else str(event.event_type)

            if event.event_type == TraceEventType.INITIALIZATION:
                prompt_text = event.details.get("prompt", "Decomposing user prompt into requirements.")
                if prompt_text and prompt_text != "Active Telemetry Session":
                    self.raw_prompt = prompt_text
                self._add_history(timestamp_str, "INIT", "Coordinator", "Decomposing user prompt into requirements.")

            elif event.event_type == TraceEventType.NEGOTIATION:
                status = event.details.get("status", "CHECK")
                self._add_history(
                    timestamp_str,
                    "CONTRACT",
                    event.agent_name,
                    f"Negotiating contract for '{event.action}' -> [{status}]",
                )

            elif event.event_type == TraceEventType.HANDOFF:
                target = event.details.get("target_agent", "Unknown")
                reason = event.details.get("reason", "")
                self._add_history(
                    timestamp_str,
                    "HANDOFF",
                    event.agent_name,
                    f"Redirecting target to [bold yellow]{target}[/bold yellow]. Reason: {reason}",
                )

            elif event.event_type == TraceEventType.ESCALATION:
                level = event.details.get("to_level", "L?")
                self._add_history(
                    timestamp_str,
                    "ESCALATE",
                    "Coordinator",
                    f"[bold red]Escalated step to {level}[/bold red] ({event.details.get('reason')})",
                )

            elif evt_name in ("EXECUTION", "EXECUTION_START", "EXECUTION_END", "COMPLETED"):
                dur = f"{event.duration_ms:.1f}ms" if event.duration_ms is not None else "N/A"
                self._add_history(
                    timestamp_str,
                    "COMPLETE",
                    event.agent_name,
                    f"Action '{event.action}' completed in {dur}.",
                )

            if self._live:
                self._live.update(self._build_layout())

    def _add_history(self, timestamp: str, tag: str, agent: str, details: str) -> None:
        tag_color = {
            "INIT": "cyan",
            "CONTRACT": "blue",
            "HANDOFF": "yellow",
            "ESCALATE": "red",
            "COMPLETE": "green",
        }.get(tag, "white")

        line = Text()
        line.append(f"[{timestamp}] ", style="dim grey")
        line.append(f"[{tag:^8}] ", style=f"bold {tag_color}")
        line.append(f"[{agent}] ", style="bold magenta")
        line.append_text(Text.from_markup(details))

        self.history.append(line)
        if len(self.history) > 12:
            self.history.pop(0)

    def _build_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=4),
        )

        # Header Panel
        header_text = Text()
        header_text.append("CHARON SYSTEM MONITOR | ", style="bold cyan")
        header_text.append("Active Agent: ", style="bold white")
        header_text.append(f"{self.active_agent}\n", style="bold green")
        header_text.append("Prompt: ", style="bold yellow")
        header_text.append(f"{self.raw_prompt[:90]}..." if len(self.raw_prompt) > 90 else self.raw_prompt)

        layout["header"].update(Panel(header_text, title="[bold white]System Trace[/bold white]", border_style="cyan"))

        # Body: CoT & Execution Tree
        layout["body"].split_row(
            Layout(name="cot", ratio=3),
            Layout(name="events", ratio=4),
        )

        if self.cot_text:
            import textwrap

            # 1. Keep memory footprint light by pruning the raw string
            self.cot_text = self.cot_text[-2500:]

            # 2. Text-wrap the lines manually so long unbroken tokens don't overflow the height
            wrapped_lines = []
            for line in self.cot_text.splitlines():
                # Assuming the CoT panel has a width of about 55-60 characters
                wrapped_lines.extend(textwrap.wrap(line, width=55) or [""])

            # 3. Take only the last 15 lines so the newest text is always visible
            cot_display = "\n".join(wrapped_lines[-15:])
            cot_style = "default"
        else:
            cot_display = "No active CoT reasoning stream..."
            cot_style = "dim"

        layout["body"]["cot"].update(
            Panel(
                Text(cot_display, style=cot_style),  # Safely renders unformatted LLM tokens
                title=f"[bold blue]Live CoT Stream ({self.active_agent})[/bold blue]",
                border_style="blue",
            )
        )

        # History Table
        event_table = Table(expand=True, show_header=False, box=None)
        event_table.add_column("Trace Log")
        for line in self.history:
            event_table.add_row(line)

        layout["body"]["events"].update(
            Panel(event_table, title="[bold green]Execution Event Stream[/bold green]", border_style="green")
        )

        # Footer Status Panel
        footer_text = Text()
        footer_text.append("Current Capability: ", style="dim white")
        footer_text.append(f"{self.current_action}\n", style="bold white")
        footer_text.append("Telemetry Ledger: ", style="dim white")
        footer_text.append("WebSocket Daemon Stream Operational", style="italic green")

        layout["footer"].update(Panel(footer_text, title="[bold grey]Status[/bold grey]", border_style="grey50"))

        return layout


async def async_main() -> None:
    """Async CLI entry point with resilient reconnect loop for Charon telemetry."""
    console = Console()
    ws_uri = f"{DEFAULT_WS_URL}?client_id=telemetry_viewer&api_key={CHARON_API_KEY}"

    viewer = RichTraceViewer(console=console)
    viewer.start(prompt="Active Telemetry Session")

    reconnect_delay = 1.0

    try:
        while True:
            try:
                viewer.current_action = f"Connecting to {DEFAULT_WS_URL}..."

                async with websockets.connect(ws_uri, ping_interval=20, ping_timeout=10) as ws:
                    reconnect_delay = 1.0  # Reset backoff on successful connection
                    viewer.current_action = "Connected to Charon Event Bus"

                    async for message in ws:
                        try:
                            raw_msg = json.loads(message)
                        except json.JSONDecodeError:
                            continue

                        # 1. Handle top-level WSEvent wrapper vs flat telemetry objects
                        event_type_str = raw_msg.get("event_type")

                        if event_type_str and event_type_str not in ("telemetry_trace", "agent_log"):
                            # Ignore non-telemetry websocket frames (e.g., overseer reports, task updates)
                            continue

                        payload = raw_msg.get("data", raw_msg)

                        if event_type_str == "agent_log":
                            chunk = payload.get("message", "")
                            if chunk:
                                # Create a synthetic TraceEvent so your existing on_event() logic handles it perfectly
                                event = TraceEvent(
                                    agent_name=viewer.active_agent,
                                    event_type=TraceEventType.THINKING,
                                    action=viewer.current_action,
                                    reasoning_chunk=chunk,
                                    details={},
                                )
                                viewer.on_event(event)
                            continue  # Skip the rest of the parsing since we handled it

                        # 2. Extract inner trace event type (e.g. THINKING, EXECUTION, HANDOFF)
                        raw_trace_type = payload.get("event_type", payload.get("type", "THINKING"))
                        if isinstance(raw_trace_type, str):
                            raw_trace_type = raw_trace_type.upper()

                        # 3. Match against TraceEventType Enum safely
                        try:
                            if hasattr(TraceEventType, "__members__") and raw_trace_type in TraceEventType.__members__:
                                event_type_enum = TraceEventType[raw_trace_type]
                            else:
                                event_type_enum = TraceEventType(raw_trace_type)
                        except (ValueError, KeyError):
                            event_type_enum = TraceEventType.THINKING

                        # 4. Extract reasoning chunk across possible field variations
                        reasoning_chunk = (
                            payload.get("reasoning_chunk")
                            or payload.get("thought")
                            or payload.get("chunk")
                            or payload.get("details", {}).get("reasoning_chunk")
                        )

                        # 5. Construct TraceEvent cleanly and notify viewer
                        event = TraceEvent(
                            agent_name=payload.get("agent_name", "Coordinator"),
                            event_type=event_type_enum,
                            action=payload.get("action", ""),
                            reasoning_chunk=reasoning_chunk,
                            details=payload.get("details", {}),
                            duration_ms=payload.get("duration_ms"),
                        )

                        # Retain timestamp if sent across WS
                        if "timestamp" in payload:
                            event.timestamp = payload["timestamp"]

                        viewer.on_event(event)

            except (websockets.ConnectionClosed, OSError) as exc:
                viewer.current_action = f"Disconnected ({exc}). Reconnecting in {reconnect_delay:.1f}s..."
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, 10.0)

    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        viewer.stop()


def main() -> None:
    """Entry point for telemetry viewer CLI launcher."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(lambda: asyncio.run(async_main()))
                future.result()
        else:
            asyncio.run(async_main())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()

```

────────────────────────────────────────────────────────────────────────────────

