"""
charon/cli/librarian/tui/controller.py
System Version: v0.2.1 | File Revision: 3.3.0

Module: Main TUI Controller loop for Charon Librarian Capability Control Center.
Orchestrates live auto-refresh header telemetry, SQLite database connections,
PEC policy management views, and PEC security denial metrics.
"""

import logging
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import psutil
from rich.console import Console
from rich.prompt import Prompt

from charon.cli.librarian.tui.components import (
    render_header,
    render_staged_skills_preview,
)
from charon.cli.librarian.tui.views_cbac import display_cbac_management_view

logger = logging.getLogger(__name__)
console = Console()

DEFAULT_DB_PATH = Path("charon.db")


class SystemTelemetryState:
    """Thread-safe state container for real-time system metrics, DB counts, and PEC violations."""

    def __init__(self):
        self._lock = threading.Lock()
        self.cpu: float = 0.0
        self.ram: float = 0.0
        self.disk: float = 0.0
        self.skill_count: int = 0
        self.agent_count: int = 0
        self.broken_deps: int = 0
        self.orphan_count: int = 0
        self.open_gaps: int = 0
        self.resolved_gaps: int = 0
        self.pec_violations: int = 0

    def update_metrics(
        self,
        cpu: float,
        ram: float,
        disk: float,
        counts: Tuple[int, int, int, int, int, int, int],
    ) -> None:
        with self._lock:
            self.cpu = cpu
            self.ram = ram
            self.disk = disk
            (
                self.skill_count,
                self.agent_count,
                self.broken_deps,
                self.orphan_count,
                self.open_gaps,
                self.resolved_gaps,
                self.pec_violations,
            ) = counts

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "cpu": self.cpu,
                "ram": self.ram,
                "disk": self.disk,
                "skill_count": self.skill_count,
                "agent_count": self.agent_count,
                "broken_deps": self.broken_deps,
                "orphan_count": self.orphan_count,
                "open_gaps": self.open_gaps,
                "resolved_gaps": self.resolved_gaps,
                "pec_violations": self.pec_violations,
            }


def _fetch_db_counts(db_conn: Optional[sqlite3.Connection]) -> Tuple[int, int, int, int, int, int, int]:
    """Queries operational counts and total PEC policy violation denials from SQLite."""
    if not db_conn:
        return 0, 0, 0, 0, 0, 0, 0

    try:
        cursor = db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM contract_policies WHERE is_active = 1")
        active_pec = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT agent_id) FROM contract_policies")
        agent_count = cursor.fetchone()[0]

        # Fetch total PEC violation denials
        pec_violations = 0
        try:
            cursor.execute("SELECT COUNT(*) FROM pec_violations")
            pec_violations = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            pec_violations = 0

        return active_pec, agent_count, 0, 0, 0, 0, pec_violations
    except sqlite3.Error as err:
        logger.error(f"Error querying telemetry DB counts: {err}")
        return 0, 0, 0, 0, 0, 0, 0


def start_telemetry_loop(
    state: SystemTelemetryState,
    db_conn: Optional[sqlite3.Connection],
    stop_event: threading.Event,
    interval_sec: float = 1.0,
) -> threading.Thread:
    """Spawns background daemon thread to sample CPU, RAM, Disk, DB statistics, and PEC metrics."""

    def _telemetry_worker():
        while not stop_event.is_set():
            try:
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                disk = psutil.disk_usage("/").percent
                counts = _fetch_db_counts(db_conn)
                state.update_metrics(cpu, ram, disk, counts)
            except Exception as exc:
                logger.warning(f"Telemetry sampling error: {exc}")

            stop_event.wait(interval_sec)

    thread = threading.Thread(target=_telemetry_worker, daemon=True)
    thread.start()
    return thread


def run_librarian_tui(
    db_path: Path = DEFAULT_DB_PATH,
    cbac_mode: str = "ENFORCING",
    refresh_interval: float = 1.0,
) -> None:
    """Main interactive TUI loop with live auto-refresh telemetry header and PEC violation tracking."""
    db_conn: Optional[sqlite3.Connection] = None

    try:
        db_conn = sqlite3.connect(db_path, check_same_thread=False)
    except sqlite3.Error as exc:
        console.print(f"[bold red]Database connection failed for '{db_path}': {exc}[/bold red]")

    # Initialize shared state and background tick loop
    telemetry_state = SystemTelemetryState()
    stop_telemetry = threading.Event()
    start_telemetry_loop(telemetry_state, db_conn, stop_telemetry, interval_sec=refresh_interval)

    # Initial sampling burst
    time.sleep(0.1)

    while True:
        snap = telemetry_state.snapshot()

        render_header(
            skill_count=snap["skill_count"],
            agent_count=snap["agent_count"],
            broken_deps_count=snap["broken_deps"],
            orphan_count=snap["orphan_count"],
            open_gaps=snap["open_gaps"],
            resolved_gaps=snap["resolved_gaps"],
            cbac_mode=cbac_mode,
            cpu_usage=snap["cpu"],
            ram_usage=snap["ram"],
            disk_usage=snap["disk"],
            pec_violations=snap["pec_violations"],
        )

        console.print("[bold cyan]\n📋 LIBRARIAN MAIN NAVIGATION[/bold cyan]")
        console.print("  [1] Index & Review Registered Skills")
        console.print("  [2] Manage Agent Permissions & PEC Policies")
        console.print("  [3] Diagnostic Suite & Gap Maintenance")
        console.print("  [4] Preview Staged & Quarantined Packages")
        console.print("  [0] Exit Control Center\n")

        choice = Prompt.ask("Select option", choices=["1", "2", "3", "4", "0"], default="2")

        if choice == "2":
            display_cbac_management_view(db_conn=db_conn)
        elif choice == "4":
            render_staged_skills_preview()
            Prompt.ask("[dim]Press Enter to return to Main Menu[/dim]", default="")
        elif choice == "0":
            stop_telemetry.set()
            console.print("\n[bold yellow]Exiting Librarian Control Center. Goodbye![/bold yellow]\n")
            if db_conn:
                db_conn.close()
            sys.exit(0)
        else:
            console.print("\n[dim yellow]Module section under construction...[/dim yellow]")
            Prompt.ask("[dim]Press Enter to continue[/dim]", default="")


if __name__ == "__main__":
    run_librarian_tui()