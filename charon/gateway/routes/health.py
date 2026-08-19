"""
charon/gateway/routes/health.py
System Version: v3.0.0

Module: Ingress and health endpoints for daemon state, task queueing, and Gatekeeper approval handshakes.
"""

import logging
import uuid
from fastapi import APIRouter, HTTPException, Request, status

from charon.gateway.models import GatekeeperDecision, TaskRequest, TaskResponse
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
        "registered_client_nodes": list(manager.client_sockets.keys()),
        "queue_depth": queue_depth,
    }


@router.post("/v1/task", response_model=TaskResponse)
async def submit_task(request_data: TaskRequest, request: Request):
    """REST ingress endpoint for queuing execution tasks."""
    daemon = getattr(request.app.state, "daemon", None)

    if not daemon or not getattr(daemon, "is_ready", False) or not hasattr(daemon, "journal"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Daemon or Task Journal is currently initializing.",
        )

    task_id = f"task_{uuid.uuid4().hex[:8]}"

    await daemon.journal.record_and_enqueue({
        "task_id": task_id,
        "client_id": request_data.client_id,
        "prompt": request_data.prompt,
        "agent_override": request_data.agent_override,
        "context": request_data.context or {},
    })

    return TaskResponse(
        task_id=task_id,
        status="queued",
        assigned_agent=request_data.agent_override,
        message="Task accepted and queued for orchestration.",
    )


@router.post("/v1/gatekeeper/respond")
async def respond_to_gatekeeper(decision: GatekeeperDecision, request: Request):
    """
    Direct resolution endpoint for Gatekeeper Level 2/3 Escalation Matrix.
    Unblocks paused tasks in GatekeeperManager targeting approval_id.
    """
    daemon = getattr(request.app.state, "daemon", None)
    approval_id = decision.approval_id
    user_decision = decision.decision.strip().upper()

    resolved = False
    if daemon and hasattr(daemon, "gatekeeper") and daemon.gatekeeper:
        if hasattr(daemon.gatekeeper, "resolve_intercept"):
            resolved = daemon.gatekeeper.resolve_intercept(approval_id, user_decision)
        elif hasattr(daemon.gatekeeper, "submit_decision"):
            resolved = daemon.gatekeeper.submit_decision(approval_id, user_decision)

    if not resolved:
        logger.warning(f"Gatekeeper response for unknown/expired approval_id: {approval_id}")

    return {
        "status": "acknowledged" if resolved else "expired_or_not_found",
        "approval_id": approval_id,
        "decision": user_decision,
    }