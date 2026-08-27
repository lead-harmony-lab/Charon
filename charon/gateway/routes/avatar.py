"""
charon/gateway/routes/avatar.py
System Version: v3.4.0 | File Revision: 3.4.2

Module: Live WebSockets pipeline for the Desktop Avatar HUD.
Provides the bidirectional stream required for the Concierge to push spontaneous
speech, visemes, and state changes directly to the user's desktop, and handles
upstream UI interaction events.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("Charon.Gateway.Routes.Avatar")

router = APIRouter(prefix="/v1/avatar", tags=["Avatar Live Feed"])


class AvatarConnectionManager:
    """Manages persistent WebSocket connections to the GNOME desktop extension and GTK overlay."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("Avatar HUD connected to Concierge live feed.")

        # Push initial connection state
        await self.push_event("system_state", {"status": "connected", "persona": "Charon"})

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("Avatar HUD disconnected from live feed.")

    async def push_event(self, event_type: str, payload: Dict[str, Any]):
        """
        The autonomic push method.
        Called by AutonomicSystem or Concierge to send speech, visual states, or HUD cards.
        """
        if not self.active_connections:
            logger.debug(f"Dropped {event_type} event: No Avatar currently connected.")
            return

        message = {"type": event_type, "payload": payload}

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to push {event_type} to Avatar: {e}")
                self.disconnect(connection)

    async def broadcast(self, event: Any):
        """
        Broadcasts a WSEvent model or raw dictionary to all connected clients.
        """
        if not self.active_connections:
            logger.debug("Dropped broadcast event: No Avatar currently connected.")
            return

        # Support Pydantic v2 (model_dump), v1 (dict), or raw dictionaries
        if hasattr(event, "model_dump"):
            message = event.model_dump()
        elif hasattr(event, "dict"):
            message = event.dict()
        else:
            message = event

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to broadcast to Avatar: {e}")
                self.disconnect(connection)

    async def handle_upstream_event(self, websocket: WebSocket, event_data: Dict[str, Any]):
        """
        Routes incoming HUD events (UI clicks, proposal resolutions, user voice/text triggers)
        back into Charon's active Concierge and Autonomic state, and broadcasts UI telemetry.
        """
        event_type = event_data.get("type")
        payload = event_data.get("payload", {})
        app = getattr(websocket, "app", None)

        if not app:
            logger.warning("WebSocket application context unavailable for upstream dispatch.")
            return

        concierge = getattr(app.state, "concierge", None)
        autonomic = getattr(app.state, "autonomic", None)

        logger.info(f"Processing upstream Avatar HUD event: '{event_type}'")

        # --------------------------------------------------------------------
        # 1. WAYLAND COORDINATE BROADCAST (GTK -> Server -> GNOME Shell)
        # --------------------------------------------------------------------
        if event_type == "window_moved":
            logger.debug(f"Broadcasting window coordinates: {payload}")
            asyncio.create_task(self.broadcast(event_data))

        # --------------------------------------------------------------------
        # 2. CONCIERGE PERCEPTION ROUTING
        # --------------------------------------------------------------------
        elif event_type == "context_window" and concierge:
            if hasattr(concierge.sensor, "log_window_context"):
                concierge.sensor.log_window_context(
                    app_name=payload.get("app_name", ""),
                    window_title=payload.get("window_title", ""),
                    active_file_path=payload.get("active_file_path"),
                    pid=payload.get("pid"),
                )

        elif event_type == "context_ide" and concierge:
            if hasattr(concierge.sensor, "log_ide_context"):
                concierge.sensor.log_ide_context(
                    editor=payload.get("editor", "VSCode"),
                    file_path=payload.get("file_path", ""),
                    language=payload.get("language", "python"),
                    selection_or_diff=payload.get("selection_or_diff"),
                    diagnostics=payload.get("diagnostics"),
                )

        # --------------------------------------------------------------------
        # 3. PROPOSAL & DIALOGUE ROUTING
        # --------------------------------------------------------------------
        elif event_type == "proposal_action":
            # Handled when user clicks an action button on a HUD Proposal Card
            action_event = payload.get("event")
            alert_id = payload.get("alert_id")

            if action_event == "dismiss":
                logger.info(f"User dismissed alert '{alert_id}'. Marking resolved.")
                if autonomic and hasattr(autonomic, "memory_collection") and autonomic.memory_collection:
                    try:
                        autonomic.memory_collection.update(
                            ids=[f"alert_state_{alert_id}"],
                            metadatas=[{"status": "dismissed_by_user"}]
                        )
                    except Exception as err:
                        logger.error(f"Failed to update alert status in memory: {err}")

            elif action_event == "fix_ide_errors" and concierge:
                # Trigger an autonomic resolution interaction sequence
                prompt = "Please inspect and offer a resolution context for the active IDE compilation errors."
                asyncio.create_task(concierge.handle_user_message(prompt))

        elif event_type == "user_input" and concierge:
            # Direct text/voice submission from HUD prompt bar
            user_text = payload.get("text", "")
            if user_text:
                asyncio.create_task(concierge.handle_user_message(user_text))

        elif event_type == "ping":
            await websocket.send_json({"type": "pong", "payload": {}})

        else:
            logger.debug(f"Unhandled upstream Avatar event payload: {event_data}")


# Global singleton to be imported across the service
avatar_stream = AvatarConnectionManager()

@router.websocket("/stream")
async def avatar_websocket_endpoint(websocket: WebSocket):
    """
    The persistent pipeline. Clients (GNOME extension, GTK Overlay) connect here on startup,
    listen for server-pushed events, and send back user interactions or telemetry.
    """
    await avatar_stream.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                parsed_data = json.loads(data)
                await avatar_stream.handle_upstream_event(websocket, parsed_data)
            except json.JSONDecodeError:
                logger.warning("Received malformed JSON payload from Avatar HUD.")

    except WebSocketDisconnect:
        avatar_stream.disconnect(websocket)