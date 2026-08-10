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