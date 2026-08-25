"""
charon/gateway/routes/websocket.py
System Version: v3.2.1 | File Revision: 3.2.1

Module: Full-duplex WebSocket streaming server for real-time IPC, telemetry,
and autonomic Concierge HUD/Avatar events (proactive interjections, viseme streams, diagnostic alerts, and cursor motion).
"""

import datetime
import json
import logging
import secrets
from typing import Any, Dict, Optional
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from charon.config import API_KEY_HEADER_NAME, CHARON_API_KEY
from charon.gateway.models import WSEvent
from charon.gateway.ws import manager

logger = logging.getLogger("Charon.Gateway.Routes.WebSocket")

router = APIRouter(tags=["WebSocket IPC & Concierge HUD Stream"])


# ============================================================================
# Schemas & Helper Builders
# ============================================================================

class ConciergeStreamEvent(BaseModel):
    """Standardized multi-modal JSON schema for WebSocket HUD/Avatar broadcasts."""
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    type: str = Field(..., description="e.g. 'proactive_interjection', 'avatar_state_update', 'diagnostic_alert', 'cursor_motion'")
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
    """Utility function to construct formatted ConciergeStreamEvent payloads for desktop overlays."""
    event = ConciergeStreamEvent(
        type=event_type,
        payload={
            "text": text,
            "suggested_action": suggested_action,
            "avatar_state": {
                "emotion": emotion,
                "viseme_sequence": viseme_sequence or []
            },
            "hud_overlay": {
                "target_app": target_app,
                "urgency": urgency,
                "pointer_target": pointer_target
            }
        }
    )
    return event.model_dump() if hasattr(event, "model_dump") else event.dict()


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


async def _handle_incoming_ws_frame(websocket: WebSocket, raw_data: str, client_id: Optional[str]):
    """Processes incoming frames for IPC task queueing, Gatekeeper actions, and direct Concierge WS streams."""
    if not raw_data.strip():
        return

    try:
        msg = json.loads(raw_data)
        action = msg.get("action") or msg.get("event_type") or msg.get("type")

        daemon = getattr(websocket.app.state, "daemon", None)
        concierge = getattr(websocket.app.state, "concierge", None)

        if action in ("ping", "heartbeat"):
            await manager.send_event(
                websocket,
                WSEvent.model_construct(
                    event_type="status_change",
                    agent_name="System",
                    client_id=client_id,
                    data={"status": "alive", "client_id": client_id, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()},
                ),
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

        elif action in ("concierge_interact", "user_message"):
            user_text = msg.get("prompt") or msg.get("text", "")
            if concierge and user_text:
                response_text = await concierge.handle_user_message(user_text)
                event_payload = build_concierge_stream_event(
                    event_type="interact_response",
                    text=response_text,
                    emotion="speaking",
                    target_app=msg.get("target_app", "Desktop")
                )
                await websocket.send_json(event_payload)

        elif action == "push_context":
            context_type = msg.get("context_type", "window")
            payload = msg.get("payload", {})
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

        elif action == "cursor_motion":
            # Ingest desktop shell cursor motion telemetry for context awareness
            if concierge and hasattr(concierge, "sensor") and hasattr(concierge.sensor, "log_cursor_motion"):
                concierge.sensor.log_cursor_motion(
                    x=msg.get("x", 0.0),
                    y=msg.get("y", 0.0),
                    active_element=msg.get("active_element")
                )

        elif action == "pointer_telemetry":
            # Broadcast the telemetry to other connected clients (like the GTK overlay)
            if hasattr(manager, "active_connections"):
                for connection in manager.active_connections:
                    # Don't bounce the message back to the GNOME shell sender
                    if connection != websocket:
                        try:
                            await connection.send_text(raw_data)
                        except Exception as e:
                            logger.debug(f"Failed to broadcast telemetry to client: {e}")

        elif action == "desktop_ipc":
            # Target the specific client ID defined in the GNOME extension (api.js)
            target_client = "gnome_shell_extension"

            if hasattr(manager, "active_connections"):
                routed = False
                for connection in manager.active_connections:
                    # Check the attribute we attached during connection
                    if getattr(connection, "client_id", None) == target_client:
                        try:
                            # Forward the exact raw JSON frame received from the Dashboard
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


# ============================================================================
# Endpoints
# ============================================================================

@router.websocket("/v1/ws")
@router.websocket("/v1/concierge/stream")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
    api_key: Optional[str] = Query(None, alias="api_key"),
):
    """
    Full-duplex WebSocket stream for IPC, telemetry, desktop overlays, and avatar animations.
    Mounted on both `/v1/ws` and `/v1/concierge/stream`.
    """
    token = _extract_ws_token(websocket, api_key)

    if CHARON_API_KEY:
        if not token or not secrets.compare_digest(token, CHARON_API_KEY):
            logger.warning(f"WebSocket connection rejected for client '{client_id}': Unauthorized.")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await manager.connect(websocket, client_id=client_id)
    websocket.client_id = client_id
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
                    "message": "Connected to Charon Autonomic Stream Gateway",
                },
            ),
        )

        while True:
            raw_data = await websocket.receive_text()
            await _handle_incoming_ws_frame(websocket, raw_data, client_id)

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: '{client_id}'")
    except Exception as e:
        logger.error(f"Unexpected WebSocket loop closure for client '{client_id}': {e}")
    finally:
        manager.disconnect(websocket)