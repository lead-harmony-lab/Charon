"""
charon/gateway/routes/health.py
System Version: v3.2.0 | File Revision: 3.2.2

Module:
"""
import logging
from fastapi import APIRouter, Request

from charon.gateway.ws import manager

logger = logging.getLogger("Charon.Gateway.Routes.Health")

router = APIRouter(tags=["Core & Ingress"])


@router.get("/v1/health")
async def health_check(request: Request):
    """Returns runtime state, active connection count, and task queue depth."""
    daemon = getattr(request.app.state, "daemon", None)
    queue_depth = 0

    if daemon and hasattr(daemon, "journal") and hasattr(daemon.journal, "qsize"):
        try:
            queue_depth = daemon.journal.qsize()
        except Exception:
            queue_depth = 0

    return {
        "status": "online",
        "service": "Charon Gateway & Core Engine",
        "active_ws_clients": len(manager.active_connections),
        "registered_client_nodes": list(getattr(manager, "client_sockets", {}).keys()),
        "queue_depth": queue_depth,
    }