"""
charon/cli/main.py
System Version: v3.1.0 | File Revision: 2.0.0

Module: Thin CLI entrypoint and interactive shell loop execution.
Includes direct launcher support for real-time TelemetryBus trace monitoring,
Skill Librarian permission & registry management, and Human-in-the-Loop Skill Forge.
Queries the daemon-resident Concierge Service via HTTP API for dynamic briefings and proposals.
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
  charon telemetry           Launch live Rich terminal telemetry trace monitor.

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

        # -------------------------------------------------------------------------
        # Request Dynamic Greeting from Daemon Concierge Service
        # -------------------------------------------------------------------------
        if not args.non_interactive and not args.command:
            with console.status("[dim]Consulting the ledger...[/dim]", spinner="dots"):
                greeting_text = await client.get_concierge_briefing()

            console.print(
                Panel(
                    f"[bold blue]{greeting_text}[/bold blue]",
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
                    console.print("\n[bold blue]A wise decision. Good evening.[/bold blue]")
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
        # Gracefully close underlying HTTP sessions
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