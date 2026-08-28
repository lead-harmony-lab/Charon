import asyncio
import json
import logging
import sys
import uuid
from typing import Any, Dict, Optional, Set, Tuple

import httpx
import websockets
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.panel import Panel

from charon.cli.ui import CharonSpinner, console, render_response

logger = logging.getLogger(__name__)

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

        # State tracked during an active stream
        self._streamed_any_chunk = False
        self._staged_prompt: Optional[str] = None
        self._active_ws: Optional[websockets.WebSocketClientProtocol] = None

        # Persistent HTTP client pool for stateless checks/Concierge APIs
        self.http_client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-API-Key": self.api_key}
        )

    async def close(self) -> None:
        """Gracefully close the underlying HTTP connection pool."""
        await self.http_client.aclose()

    async def ping_daemon(self) -> bool:
        """Checks if the Charon REST endpoint is healthy."""
        try:
            res = await self.http_client.get("/v1/health", timeout=3.0)
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
        self._streamed_any_chunk = False
        self._staged_prompt = None

        ws_uri = f"{self.ws_url}?client_id={self.client_id}&api_key={self.api_key}"
        task_id = None

        try:
            # Removed ping_interval and ping_timeout so the CLI won't drop the connection
            # when the daemon's event loop is blocked by heavy LLM inference.
            async with websockets.connect(
                ws_uri,
                additional_headers={"x-api-key": self.api_key},
                ping_interval=None,
                ping_timeout=None,
            ) as ws:
                self._active_ws = ws

                # 1. Post Task via WebSocket
                await ws.send(json.dumps({
                    "action": "submit_task",
                    "prompt": prompt,
                    "client_id": self.client_id,
                    "agent_override": agent_override,
                }))

                # 2. Consume WebSocket Event Stream
                while True:
                    raw_msg = await ws.recv()
                    event = json.loads(raw_msg)

                    event_type = event.get("event_type") or event.get("type")
                    event_task_id = event.get("task_id")
                    data = event.get("data", {}) if "data" in event else event

                    # 3. Capture dynamically generated task_id from queuing ack
                    if event_type == "status_change" and data.get("status") == "queued":
                        if not task_id and event_task_id:
                            task_id = event_task_id
                        continue

                    # Ignore events belonging to other active tasks
                    if self._should_ignore_event(event_task_id, task_id, event_type):
                        continue

                    # Route the event to the appropriate handler
                    is_complete, success = await self._route_event(event_type, data, session)
                    if is_complete:
                        return success, self._staged_prompt

        except websockets.exceptions.ConnectionClosed:
            self.spinner.stop()
            console.print("\n[dim][System]: Event stream disconnected.[/dim]")
            return False, None
        except asyncio.CancelledError:
            self.spinner.stop()
            console.print("\n[dim][System]: Stream cancelled by user.[/dim]")
            return False, None
        except Exception as e:
            self.spinner.stop()
            console.print(f"\n[bold red][System Error]: Stream error ({e})[/bold red]")
            return False, None
        finally:
            self._active_ws = None

    # --- Internal Stream Handlers ---

    def _should_ignore_event(self, event_task_id: Optional[str], task_id: Optional[str], event_type: str) -> bool:
        """Determines if an event belongs to a different task and should be dropped."""
        global_events = ["system_alert", "overseer_report"]
        return bool(event_task_id and task_id and event_task_id != task_id and event_type not in global_events)

    async def _route_event(self, event_type: str, data: Dict[str, Any], session: PromptSession) -> Tuple[bool, bool]:
        """
        Routes the event payload to specific handlers.
        Returns (is_complete, is_success).
        """
        heartbeat_events = ["task_heartbeat", "task_progress", "agent_status", "agent_action", "status", "telemetry", "step"]
        stream_events = ["agent_log", "task_stream", "content_chunk"]
        proposal_events = ["concierge_suggestion", "concierge_proposal", "proposal"]

        if event_type in heartbeat_events:
            self._handle_heartbeat(data)
        elif event_type in stream_events:
            self._handle_stream_chunk(event_type, data)
        elif event_type == "gatekeeper_intercept":
            await self._handle_gatekeeper(data, session)
        elif event_type in proposal_events:
            self._handle_proposal(data)
        elif event_type == "system_alert":
            self._handle_system_alert(data)
        elif event_type == "task_complete":
            self._handle_completion(data)
            return True, True
        elif event_type in ["task_error", "error"]:
            self._handle_error(data)
            return True, False

        return False, False

    def _handle_heartbeat(self, data: Dict[str, Any]) -> None:
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
            self.spinner.update(f"[{agent_label}] Tending to the arrangements... ({elapsed}s)")

    def _handle_stream_chunk(self, event_type: str, data: Dict[str, Any]) -> None:
        if data.get("is_step") or data.get("step"):
            step_text = data.get("step") or data.get("message", "")
            agent = data.get("active_agent") or data.get("agent")
            if step_text:
                display_text = f"[{agent}] {step_text}" if agent else str(step_text)
                self.spinner.update(display_text)
        else:
            chunk = data.get("message") or data.get("content", "")
            if isinstance(chunk, dict):
                chunk = json.dumps(chunk, indent=2)
            if chunk:
                if event_type in ["content_chunk", "task_stream"]:
                    self._streamed_any_chunk = True
                if self.spinner.running:
                    self.spinner.stop()
                sys.stdout.write(chunk)
                sys.stdout.flush()

    async def _handle_gatekeeper(self, data: Dict[str, Any], session: PromptSession) -> None:
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
            console.print(Panel(panel_msg, border_style="yellow", title="Authorization Required"))

        decision = await session.prompt_async(HTML("<ansiyellow><b>Authorization [proceed/cancel] > </b></ansiyellow>"))
        decision_str = decision.strip().lower()

        if self._active_ws:
            await self._active_ws.send(json.dumps({
                "action": "gatekeeper_respond",
                "approval_id": approval_id,
                "decision": decision_str,
                "client_id": self.client_id,
            }))

        self.spinner.start("Resuming task execution...")

    def _handle_proposal(self, data: Dict[str, Any]) -> None:
        if self.spinner.running:
            self.spinner.stop()

        phrase = data.get("phrase") or data.get("recommendation") or data.get("next_step")
        proposed_cmd = data.get("suggested_prompt") or data.get("proposed_command") or data.get("next_step")
        proposal_key = f"{phrase}:{proposed_cmd}"

        if phrase and proposal_key not in self._rendered_proposals:
            self._rendered_proposals.add(proposal_key)
            self._staged_prompt = proposed_cmd

            panel_body = (
                f"[bold italic cyan]\"{phrase}\"[/bold italic cyan]\n\n"
                f"[dim]Use [bold white]↑/↓[/bold white] arrows to select, press [bold white]Enter[/bold white] to confirm:[/dim]"
            )
            console.print()
            console.print(Panel(panel_body, title="[bold blue]🛎️ Concierge Proposal[/bold blue]", border_style="blue", expand=False))

    def _handle_system_alert(self, data: Dict[str, Any]) -> None:
        severity = data.get("severity", "INFO")
        title = data.get("title", "System Alert")
        msg = data.get("message", "")
        style = "bold red" if severity == "CRITICAL" else "bold yellow"
        border = "red" if severity == "CRITICAL" else "yellow"
        console.print(Panel(msg, title=f"[{style}]{title}[/{style}]", border_style=border))

    def _handle_completion(self, data: Dict[str, Any]) -> None:
        self.spinner.stop()
        summary = data.get("summary") or data.get("result") or data.get("output") or data.get("content", "")

        if isinstance(summary, dict):
            if "constraint_revision" in summary:
                summary = summary["constraint_revision"].get("failure_summary") or json.dumps(summary, indent=2)
            else:
                summary = json.dumps(summary, indent=2)

        if summary and not self._streamed_any_chunk:
            console.print("\n[bold cyan]🛎️ CHARON:[/bold cyan] ", end="")
            render_response(str(summary))
        else:
            console.print()

    def _handle_error(self, data: Dict[str, Any]) -> None:
        self.spinner.stop()
        error_msg = data.get("error") or data.get("message", "An unknown error occurred.")
        if isinstance(error_msg, dict):
            error_msg = json.dumps(error_msg, indent=2)
        console.print(f"\n[bold red][System Error]: {error_msg}[/bold red]")

    # --- REST Endpoints ---

    async def get_concierge_briefing(self) -> str:
        """Fetch dynamic briefing greeting from daemon's Concierge service."""
        try:
            response = await self.http_client.get("/api/v1/concierge/briefing", timeout=10.0)
            if response.status_code == 200:
                return response.json().get("greeting", "Welcome to The Continental.")
        except Exception as err:
            logger.warning(f"Failed to fetch concierge briefing from daemon: {err}")
        return "Welcome to The Continental. How may I be of service?"

    async def evaluate_concierge_proposal(
            self, user_query: str, completed_action: str, execution_result: str
    ) -> Optional[dict]:
        """Request task post-mortem proposal from daemon's Concierge service."""
        try:
            payload = {
                "user_query": user_query,
                "completed_action": completed_action,
                "execution_result": execution_result,
            }
            response = await self.http_client.post("/api/v1/concierge/evaluate", json=payload, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                if data.get("has_proposal"):
                    return data.get("proposal")
        except Exception as err:
            logger.warning(f"Failed to fetch concierge proposal: {err}")
        return None