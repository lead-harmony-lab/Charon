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
