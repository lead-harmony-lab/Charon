"""
charon/gateway/routes_router.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Gateway Router Control endpoints.
Provides APIs for managing dynamic triage prompts, priority weighting, tool toggles,
hard routing rules, and triage telemetry debugging.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status

from charon.gateway.models import (
    AgentManifestResponse,
    AgentUpdateRequest,
    DynamicRuleRequest,
    ToolPatchRequest,
    WSEvent,
)
from charon.gateway.ws import manager

logger = logging.getLogger("Charon.Gateway.RoutesRouter")

router = APIRouter(prefix="/v1/router", tags=["Dynamic Router"])


def _get_engine(request: Request):
    """Helper to retrieve OrchestrationEngine or raise clean HTTP 503 error."""
    engine = getattr(request.app.state, "engine", None)
    if not engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OrchestrationEngine unavailable or still initializing.",
        )
    return engine


# ============================================================================
# Agent Manifest & Priority Weight Endpoints
# ============================================================================

@router.get("/agents", response_model=Dict[str, Any])
async def list_router_agents(request: Request):
    """
    Retrieves all registered agents, capability manifests, active tool schemas,
    priority weights, and keyword override triggers.
    """
    engine = _get_engine(request)
    if not hasattr(engine, "librarian") or not engine.librarian:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SkillLibrarian unavailable on Core Engine.",
        )

    manifests = engine.librarian.get_all_agent_manifests()
    return {
        "status": "success",
        "count": len(manifests),
        "agents": manifests,
    }


@router.get("/agents/{agent_id}", response_model=AgentManifestResponse)
async def get_router_agent(agent_id: str, request: Request):
    """Retrieves routing configuration details for a single agent."""
    engine = _get_engine(request)
    if not hasattr(engine, "librarian") or not engine.librarian:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SkillLibrarian unavailable on Core Engine.",
        )

    manifest = engine.librarian.get_agent_manifest(agent_id)
    if not manifest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found in registry.",
        )

    return manifest


@router.put("/agents/{agent_id}", response_model=Dict[str, Any])
async def update_router_agent(agent_id: str, update_req: AgentUpdateRequest, request: Request):
    """
    Updates an agent's dynamic description, system prompt, priority weight,
    or shortcut triggers in SQLite and hot-reloads the in-memory cache.
    """
    engine = _get_engine(request)
    librarian = engine.librarian

    existing = librarian.get_agent_manifest(agent_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found.",
        )

    if hasattr(update_req, "model_dump"):
        update_data = update_req.model_dump(exclude_unset=True)
    elif hasattr(update_req, "dict"):
        update_data = update_req.dict(exclude_unset=True)
    else:
        update_data = dict(update_req)

    success = librarian.update_agent_manifest(agent_id, update_data)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist update for agent '{agent_id}'.",
        )

    librarian.reload_agent_manifest(agent_id)

    await manager.broadcast(
        WSEvent.model_construct(
            event_type="router_agent_updated",
            agent_name="System",
            data={
                "agent_id": agent_id,
                "updated_fields": list(update_data.keys()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    )

    logger.info(f"[Router API] Hot-reloaded agent '{agent_id}' configuration.")
    return {
        "status": "success",
        "agent_id": agent_id,
        "message": f"Agent '{agent_id}' manifest updated and reloaded in runtime engine.",
        "updated_fields": update_data,
    }


# ============================================================================
# Dynamic Tool Schemas & Toggling Endpoints
# ============================================================================

@router.patch("/agents/{agent_id}/tools", response_model=Dict[str, Any])
async def toggle_agent_tool(agent_id: str, patch_req: ToolPatchRequest, request: Request):
    """Dynamically enables or disables a specific tool for an agent at runtime."""
    engine = _get_engine(request)
    librarian = engine.librarian

    updated = librarian.set_tool_status(
        agent_id=agent_id,
        tool_name=patch_req.tool_name,
        enabled=patch_req.enabled,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to set tool '{patch_req.tool_name}' status for agent '{agent_id}'.",
        )

    await manager.broadcast(
        WSEvent.model_construct(
            event_type="router_tool_toggled",
            agent_name="System",
            data={
                "agent_id": agent_id,
                "tool_name": patch_req.tool_name,
                "enabled": patch_req.enabled,
            },
        )
    )

    return {
        "status": "success",
        "agent_id": agent_id,
        "tool_name": patch_req.tool_name,
        "enabled": patch_req.enabled,
        "message": f"Tool '{patch_req.tool_name}' set to enabled={patch_req.enabled} for agent '{agent_id}'.",
    }


# ============================================================================
# Dynamic Shortcut & Hard Override Rules Endpoints
# ============================================================================

@router.get("/rules", response_model=Dict[str, Any])
async def list_routing_rules(request: Request):
    """Lists all active shortcut rule overrides (e.g., '#archivist' -> forced dispatch)."""
    engine = _get_engine(request)
    rules = engine.intent_parser.get_override_rules() if hasattr(engine, "intent_parser") else []

    return {
        "status": "success",
        "count": len(rules),
        "rules": rules,
    }


@router.post("/rules", response_model=Dict[str, Any])
async def create_routing_rule(rule_req: DynamicRuleRequest, request: Request):
    """Creates a new hard shortcut override rule in the IntentParser."""
    engine = _get_engine(request)

    if not hasattr(engine, "intent_parser"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="IntentParser missing from core engine.",
        )

    rule_id = engine.intent_parser.add_override_rule(
        trigger=rule_req.trigger,
        target_agent=rule_req.target_agent,
        description=rule_req.description,
    )

    return {
        "status": "success",
        "rule_id": rule_id,
        "trigger": rule_req.trigger,
        "target_agent": rule_req.target_agent,
        "message": f"Shortcut rule created: '{rule_req.trigger}' -> '{rule_req.target_agent}'",
    }


@router.delete("/rules/{rule_id}", response_model=Dict[str, Any])
async def delete_routing_rule(rule_id: str, request: Request):
    """Deletes an active hard shortcut override rule."""
    engine = _get_engine(request)

    if not hasattr(engine, "intent_parser"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="IntentParser missing from core engine.",
        )

    removed = engine.intent_parser.remove_override_rule(rule_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule ID '{rule_id}' not found.",
        )

    return {
        "status": "success",
        "rule_id": rule_id,
        "message": f"Shortcut rule '{rule_id}' removed.",
    }


# ============================================================================
# Triage Logs & Telemetry Endpoints
# ============================================================================

@router.get("/telemetry/recent", response_model=Dict[str, Any])
async def get_recent_triage_logs(request: Request, limit: int = 20):
    """
    Retrieves Pass 1 triage evaluation logs, including candidate scores and
    LLM confidence ratings for recent requests.
    """
    state_mgr = getattr(request.app.state, "state_manager", None) or getattr(request.app.state, "state_mgr", None)

    logs = []
    if state_mgr and hasattr(state_mgr, "get_recent_triage_evaluations"):
        try:
            logs = state_mgr.get_recent_triage_evaluations(limit=limit)
        except Exception as err:
            logger.warning(f"Failed to query recent triage evaluations: {err}")

    return {
        "status": "success",
        "count": len(logs),
        "logs": logs,
    }