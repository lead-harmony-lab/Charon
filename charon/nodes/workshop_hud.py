"""
charon/nodes/workshop_hud.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: nodes/workshop_hud.py
Module: Workshop HUD Node for Charon Engine.

Simulates a physical workbench HUD display that renders telemetry,
streams agent execution logs, displays proactive Concierge prompts,
and handles Gatekeeper operator authorization.
"""

import asyncio
import logging
import sys
from typing import Dict, Any

from charon.gateway.models import WSEvent
from charon.sdk import CharonClientNode

# Configure HUD logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("WorkshopHUD")


# ==============================================================================
# Terminal UI Formatting Helpers
# ==============================================================================
def print_banner(title: str, style_char: str = "=") -> None:
    width = 64
    print(f"\n{style_char * width}")
    print(f" {title.center(width - 2)}")
    print(f"{style_char * width}\n")


def print_hud_chip(header: str, content: str, alert_type: str = "INFO") -> None:
    symbols = {"INFO": "ℹ️", "ALERT": "🚨", "PROMPT": "🛎️", "SECURITY": "🛡️"}
    icon = symbols.get(alert_type, "📌")
    print(f"\n┌── {icon} [{header}] ───────────────────────────────────────────┐")
    for line in content.splitlines():
        print(f"│  {line}")
    print("└─────────────────────────────────────────────────────────────┘\n")


# ==============================================================================
# Node Initialization
# ==============================================================================
hud_node = CharonClientNode(
    client_id="workshop_hud_01",
    engine_url="http://localhost:8000",
    default_context={
        "node_type": "heads_up_display",
        "location": "main_workbench",
        "attached_hardware": ["3d_printer_01", "usb_cnc_mill"],
    },
)


# ==============================================================================
# Event Handlers (Targeted Node Bus)
# ==============================================================================
@hud_node.on("agent_log")
async def handle_agent_log(event: WSEvent) -> None:
    """Streams real-time execution logs from active Charon agents."""
    message = event.data.get("message", "")
    sys.stdout.write(message)
    sys.stdout.flush()


@hud_node.on("concierge_suggestion")
async def handle_concierge_suggestion(event: WSEvent) -> None:
    """Renders proactive suggestions evaluated by ConciergeService."""
    phrase = event.data.get("phrase", "")
    suggested_prompt = event.data.get("suggested_prompt", "")
    action_id = event.data.get("id", "unknown")

    formatted_msg = (
        f"{phrase}\n"
        f"► Quick Action [{action_id}]: '{suggested_prompt}'\n"
        f"  (Type 'yes' or 'execute' to accept)"
    )
    print_hud_chip("CONCIERGE PROACTIVE RECOMMENDATION", formatted_msg, alert_type="PROMPT")


@hud_node.on("gatekeeper_intercept")
async def handle_gatekeeper_intercept(event: WSEvent) -> None:
    """Displays safety intercept manifests requiring physical operator sign-off."""
    manifest = event.data.get("manifest", "")
    approval_id = event.data.get("approval_id", "")

    formatted_msg = (
        f"{manifest}\n\n"
        f"► Approval ID: {approval_id}\n"
        f"► Action Required: Reply 'proceed' to execute or 'cancel' to rescind."
    )
    print_hud_chip("GATEKEEPER SECURITY INTERCEPT", formatted_msg, alert_type="SECURITY")


@hud_node.on("task_complete")
async def handle_task_complete(event: WSEvent) -> None:
    """Renders task completion summaries."""
    summary = event.data.get("summary", "")
    print(f"\n✅ [TASK COMPLETE] {summary}\n")


@hud_node.on("overseer_report")
async def handle_overseer_report(event: WSEvent) -> None:
    """Updates HUD status bar with system telemetry."""
    data = event.data
    engine_status = "ONLINE" if data.get("engine_online") else "OFFLINE"
    queue_depth = data.get("queue_depth", 0)
    current_task = data.get("current_task", "Idle")

    # Log telemetry summary on HUD header line
    logger.debug(
        f"[TELEMETRY] Engine: {engine_status} | Queue: {queue_depth} | Active Task: {current_task}"
    )


@hud_node.on("system_alert")
async def handle_system_alert(event: WSEvent) -> None:
    """Renders high-priority broadcast alerts from daemon."""
    severity = event.data.get("severity", "INFO")
    title = event.data.get("title", "SYSTEM NOTICE")
    message = event.data.get("message", "")

    print_hud_chip(f"SYSTEM ALERT - {severity}: {title}", message, alert_type="ALERT")


# ==============================================================================
# Interactive Operator Console
# ==============================================================================
async def operator_input_loop(node: CharonClientNode) -> None:
    """Reads command inputs from the local workstation operator keyboard."""
    await asyncio.sleep(1.0)  # Wait for initial WS connection message
    print_banner("WORKSHOP HUD NODE 01 OPERATIONAL")
    print("Type a prompt or command to dispatch to Charon (e.g., 'compile firmware for project X').")
    print("Type 'exit' or 'quit' to shut down node.\n")

    loop = asyncio.get_running_loop()

    while True:
        try:
            # Read input asynchronously from stdin
            user_input = await loop.run_in_executor(None, input, "HUD> ")
            command = user_input.strip()

            if not command:
                continue

            if command.lower() in ["exit", "quit"]:
                logger.info("Shutdown requested by operator.")
                await node.disconnect()
                break

            # Send task to central daemon with client_id attached
            response = await node.submit_task(prompt=command)
            print(f"──► Task dispatched [ID: {response.task_id}] (Agent: {response.assigned_agent or 'Triage'})")

        except Exception as e:
            logger.error(f"Error handling operator input: {e}")
            await asyncio.sleep(0.5)


# ==============================================================================
# Main Entry Point
# ==============================================================================
async def main() -> None:
    # Initialize connection and background WS listener
    await hud_node.connect()

    # Run operator CLI concurrently with WS event listener loop
    try:
        await asyncio.gather(
            hud_node.listen_forever(),
            operator_input_loop(hud_node),
        )
    except asyncio.CancelledError:
        pass
    finally:
        if hud_node.is_connected:
            await hud_node.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nWorkshop HUD terminated.")
