"""
charon/cli/client.py
System Version: v0.1.0 | File Revision: 1.2.2

Module: Daemon integration client managing HTTP REST and WebSocket streaming.
"""

import json
import logging
import sys
import uuid
from typing import Optional, Set, Tuple

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
                            if isinstance(chunk, dict):
                                chunk = json.dumps(chunk, indent=2)
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

                        if isinstance(summary, dict):
                            if "constraint_revision" in summary:
                                summary = (
                                    summary["constraint_revision"].get("failure_summary")
                                    or json.dumps(summary, indent=2)
                                )
                            else:
                                summary = json.dumps(summary, indent=2)

                        if summary and not streamed_any_chunk:
                            console.print("\n[bold cyan]🛎️ CHARON:[/bold cyan] ", end="")
                            render_response(str(summary))
                        else:
                            console.print()
                        break

                    # Task Errors
                    elif event_type in ["task_error", "error"]:
                        self.spinner.stop()
                        error_msg = data.get("error") or data.get("message", "An unknown error occurred.")
                        if isinstance(error_msg, dict):
                            error_msg = json.dumps(error_msg, indent=2)
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

    async def get_concierge_briefing(self) -> str:
        """Fetch dynamic briefing greeting from daemon's Concierge service."""
        try:
            response = await self._http_client.get(
                f"{self.base_url}/api/v1/concierge/briefing",
                headers=self._headers,
                timeout=10.0,
            )
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
            response = await self._http_client.post(
                f"{self.base_url}/api/v1/concierge/evaluate",
                json=payload,
                headers=self._headers,
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("has_proposal"):
                    return data.get("proposal")
        except Exception as err:
            logger.warning(f"Failed to fetch concierge proposal: {err}")
        return None