"""
charon/gateway/dispatch.py
System Version: v3.6.4

Module: Central WebSocket Event Dispatcher.
Parses incoming JSON frames from any WebSocket client (GNOME, GTK, Avatar HUD) and routes
them to the appropriate Autonomic, Concierge, or Daemon backend systems.
"""

import datetime
import json
import logging
import uuid
import asyncio
from typing import Any, Dict, Optional

from fastapi import WebSocket
from pydantic import BaseModel, Field

from charon.gateway.models import WSEvent

logger = logging.getLogger("Charon.Gateway.Dispatch")


class ConciergeStreamEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    type: str = Field(..., description="e.g. 'proactive_interjection'")
    payload: Dict[str, Any] = Field(default_factory=dict)


def build_concierge_stream_event(
    event_type: str,
    text: str,
    suggested_action: Optional[str] = None,
    emotion: str = "attentive",
    viseme_sequence: Optional[list] = None,
    target_app: Optional[str] = None,
    urgency: str = "medium",
    pointer_target: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    event = ConciergeStreamEvent(
        type=event_type,
        payload={
            "text": text,
            "suggested_action": suggested_action,
            "avatar_state": {"emotion": emotion, "viseme_sequence": viseme_sequence or []},
            "hud_overlay": {"target_app": target_app, "urgency": urgency, "pointer_target": pointer_target}
        }
    )
    return event.model_dump() if hasattr(event, "model_dump") else event.dict()


async def handle_incoming_ws_frame(websocket: WebSocket, raw_data: str, client_id: Optional[str], manager: Any):
    """Processes incoming frames with full telemetry routing diagnostics and unified Avatar event dispatch."""
    if not raw_data.strip():
        return

    try:
        msg = json.loads(raw_data)
        action = msg.get("action") or msg.get("event_type") or msg.get("type")
        payload = msg.get("payload", msg)

        daemon = getattr(websocket.app.state, "daemon", None)
        concierge = getattr(websocket.app.state, "concierge", None)
        autonomic = getattr(websocket.app.state, "autonomic", None)

        # --------------------------------------------------------------------
        # 1. SYSTEM & TASK MANAGEMENT
        # --------------------------------------------------------------------
        if action in ("ping", "heartbeat"):
            await manager.send_event(
                websocket,
                WSEvent.model_construct(
                    event_type="status_change",
                    agent_name="System",
                    client_id=client_id,
                    data={
                        "status": "alive",
                        "client_id": client_id,
                        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    }
                )
            )

        elif action == "submit_task":
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            effective_client_id = client_id or msg.get("client_id")
            if daemon and hasattr(daemon, "journal"):
                await daemon.journal.record_and_enqueue({
                    "task_id": task_id,
                    "client_id": effective_client_id,
                    "prompt": msg.get("prompt", ""),
                    "agent_override": msg.get("agent_override"),
                    "context": msg.get("context", {})
                })
                await manager.send_event(
                    websocket,
                    WSEvent.model_construct(
                        event_type="status_change",
                        task_id=task_id,
                        agent_name="System",
                        client_id=effective_client_id,
                        data={"status": "queued", "task_id": task_id}
                    )
                )

        elif action in ("gatekeeper_respond", "approval_response"):
            approval_id = msg.get("approval_id")
            decision_str = msg.get("decision", "REJECTED").upper()
            if daemon and hasattr(daemon, "gatekeeper") and daemon.gatekeeper and approval_id:
                if hasattr(daemon.gatekeeper, "resolve_intercept"):
                    daemon.gatekeeper.resolve_intercept(approval_id, decision_str)
                elif hasattr(daemon.gatekeeper, "submit_decision"):
                    daemon.gatekeeper.submit_decision(approval_id, decision_str)

        # --------------------------------------------------------------------
        # 2. CONCIERGE PERCEPTION & INTERACTION
        # --------------------------------------------------------------------
        elif action in ("concierge_interact", "user_message", "user_input"):
            user_text = msg.get("prompt") or msg.get("text", "") or payload.get("text", "")
            if concierge and user_text:
                if action == "user_input":
                    # Fire-and-forget background task for upstream HUD user inputs
                    asyncio.create_task(concierge.handle_user_message(user_text))
                else:
                    response_text = await concierge.handle_user_message(user_text)
                    await websocket.send_json(
                        build_concierge_stream_event(
                            "interact_response",
                            response_text,
                            emotion="speaking",
                            target_app=msg.get("target_app", "Desktop")
                        )
                    )

        elif action in ("push_context", "context_window", "context_ide"):
            context_type = msg.get("context_type") or ("ide" if action == "context_ide" else "window")
            if concierge and hasattr(concierge, "sensor"):
                if context_type == "window":
                    concierge.sensor.log_window_context(
                        app_name=payload.get("app_name", "Unknown"),
                        window_title=payload.get("window_title", ""),
                        active_file_path=payload.get("active_file_path"),
                        pid=payload.get("pid")
                    )
                elif context_type == "ide":
                    concierge.sensor.log_ide_context(
                        editor=payload.get("editor", "VSCode"),
                        file_path=payload.get("file_path", ""),
                        language=payload.get("language", "python"),
                        selection_or_diff=payload.get("selection_or_diff"),
                        diagnostics=payload.get("diagnostics")
                    )

        elif action == "proposal_action":
            action_event = payload.get("event")
            alert_id = payload.get("alert_id")

            if action_event == "dismiss" and autonomic and hasattr(autonomic, "memory_collection"):
                try:
                    autonomic.memory_collection.update(
                        ids=[f"alert_state_{alert_id}"],
                        metadatas=[{"status": "dismissed_by_user"}]
                    )
                    logger.info(f"Alert '{alert_id}' dismissed by user.")
                except Exception as e:
                    logger.error(f"Failed to update alert status in memory: {e}")

            elif action_event == "fix_ide_errors" and concierge:
                prompt = "Please inspect and offer a resolution context for the active IDE compilation errors."
                asyncio.create_task(concierge.handle_user_message(prompt))

        elif action == "cursor_motion":
            if concierge and hasattr(concierge, "sensor") and hasattr(concierge.sensor, "log_cursor_motion"):
                concierge.sensor.log_cursor_motion(
                    x=msg.get("x", 0.0),
                    y=msg.get("y", 0.0),
                    active_element=msg.get("active_element")
                )

        # --------------------------------------------------------------------
        # 3. NETWORK TELEMETRY BROADCASTS & DESKTOP IPC
        # --------------------------------------------------------------------
        elif action == "pointer_telemetry":
            if hasattr(manager, "active_connections"):
                total_conns = len(manager.active_connections)
                recipients = [c for c in manager.active_connections if c != websocket]

                if not recipients:
                    logger.warning("[TELEMETRY WARNING] Telemetry received but NO other sockets exist to receive it!")

                for connection in recipients:
                    try:
                        await connection.send_text(raw_data)
                        logger.debug(f"[TELEMETRY SUCCESS] Sent frame to socket {id(connection)} (client_id: '{getattr(connection, 'client_id', None)}')")
                    except Exception as e:
                        logger.error(f"[TELEMETRY ERROR] Failed to send to socket {id(connection)}: {e}")

        elif action == "window_moved":
            if hasattr(manager, "active_connections"):
                for connection in manager.active_connections:
                    if connection != websocket:
                        try:
                            await connection.send_text(raw_data)
                        except Exception as e:
                            logger.debug(f"Failed to route window_moved to client: {e}")

        elif action == "desktop_ipc":
            target_client = "gnome_shell_extension"
            if hasattr(manager, "active_connections"):
                routed = False
                for connection in manager.active_connections:
                    if getattr(connection, "client_id", None) == target_client:
                        try:
                            await connection.send_text(raw_data)
                            routed = True
                        except Exception as e:
                            logger.error(f"Failed to route IPC to {target_client}: {e}")
                if routed:
                    logger.debug(f"Successfully routed desktop_ipc frame from '{client_id}' to '{target_client}'.")
                else:
                    logger.warning(f"Dropped desktop_ipc frame: Target '{target_client}' is not currently connected.")

    except json.JSONDecodeError:
        logger.debug(f"Received non-JSON raw WS frame: {raw_data[:50]}")
    except Exception as e:
        logger.error(f"Error handling WS frame from client '{client_id}': {e}", exc_info=True)