"""
charon/gateway/routes/websocket.py
System Version: v3.2.3 | File Revision: 3.2.3

Module: Full-duplex WebSocket stream facade for IPC, telemetry, desktop HUD overlays,
and avatar animations. Multi-mounted across legacy and HUD route paths.
"""

import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from charon.config import API_KEY_HEADER_NAME, CHARON_API_KEY
from charon.gateway.models import WSEvent
from charon.gateway.ws import manager
from charon.gateway.dispatch import handle_incoming_ws_frame

logger = logging.getLogger("Charon.Gateway.Routes.WebSocket")
router = APIRouter(tags=["Concierge HUD Stream & Avatar Feed"])


def _extract_ws_token(websocket: WebSocket, query_api_key: Optional[str]) -> Optional[str]:
    custom_header = websocket.headers.get(API_KEY_HEADER_NAME.lower()) if API_KEY_HEADER_NAME else None
    if custom_header:
        return custom_header.strip()
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    if query_api_key:
        return query_api_key.strip()
    return None

@router.websocket("/v1/concierge/stream")
@router.websocket("/v1/avatar/stream")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
    api_key: Optional[str] = Query(None, alias="api_key"),
):
    """
    Unified full-duplex WebSocket endpoint serving legacy IPC `/v1/ws`, Concierge HUD `/v1/concierge/stream`,
    and GTK/Avatar `/v1/avatar/stream` on a single connection manager.
    """
    token = _extract_ws_token(websocket, api_key)
    if CHARON_API_KEY:
        if not token or not secrets.compare_digest(token, CHARON_API_KEY):
            logger.warning(f"[WS STREAM AUTH REJECT] Connection rejected for client '{client_id}'")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await manager.connect(websocket, client_id=client_id)
    websocket.client_id = client_id
    logger.info(
        f"[WS STREAM CONNECT] Connected client_id='{client_id}' | "
        f"Socket ID={id(websocket)} | Manager active_connections count={len(manager.active_connections)}"
    )

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
            await handle_incoming_ws_frame(websocket, raw_data, client_id, manager)

    except WebSocketDisconnect:
        logger.info(f"[WS STREAM DISCONNECT] Client disconnected: '{client_id}' | Socket ID={id(websocket)}")
    except Exception as e:
        logger.error(f"[WS STREAM ERROR] Loop error for '{client_id}': {e}")
    finally:
        manager.disconnect(websocket)
        logger.info(f"[WS STREAM CLEANUP] Socket removed. Manager active_connections count={len(manager.active_connections)}")