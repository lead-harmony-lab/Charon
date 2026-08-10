"""
charon/gateway/routes.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: REST API and WebSocket ingress endpoints.
Handles health checks, task queueing, Gatekeeper approval handshakes, WS IPC,
Skill Blueprint inspection & human-in-the-loop Gemini prompt generation,
and mounts sub-routers (Router Control API).
"""

import json
import logging
from pathlib import Path
import secrets
from typing import Any, Dict, Optional
import uuid

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from charon.config import API_KEY_HEADER_NAME, CHARON_API_KEY
from charon.gateway.models import GatekeeperDecision, TaskRequest, TaskResponse, WSEvent
from charon.gateway.routes_router import router as router_control_api
from charon.gateway.ws import manager

logger = logging.getLogger("Charon.Gateway.Routes")

router = APIRouter()

# Mount Sub-Routers
router.include_router(router_control_api)


class SkillRegisterRequest(BaseModel):
    """Payload for registering manually verified skill code generated via Gemini Chat."""
    skill_name: str = Field(..., description="Name of the skill class/module (e.g. dynamic_csv_exporter)")
    action_name: str = Field(..., description="Action name handled by skill (e.g. export_csv_report)")
    code: str = Field(..., description="Python source code implementation for the skill")
    description: str = Field(default="", description="Optional description of skill capabilities")


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


# ============================================================================
# Core Ingress & Health Endpoints
# ============================================================================

@router.get("/v1/health")
async def health_check(request: Request):
    """Returns runtime state, active connection count, and task queue depth."""
    daemon = getattr(request.app.state, "daemon", None)
    queue_depth = 0
    if daemon and hasattr(daemon, "queue") and hasattr(daemon.queue, "qsize"):
        try:
            queue_depth = daemon.queue.qsize()
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
    if not daemon or not hasattr(daemon, "queue"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Daemon or Task Queue is currently initializing.",
        )

    task_id = f"task_{uuid.uuid4().hex[:8]}"

    await daemon.queue.put({
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


# ============================================================================
# Skill Gap Registry & Blueprint Endpoints (Human-in-the-Loop Gemini Workflow)
# ============================================================================

@router.get("/v1/skills/gaps")
async def get_skill_gaps(request: Request):
    """Returns frequency metrics for tracked diagnostic gaps."""
    registry = getattr(request.app.state, "gap_registry", None)
    if not registry:
        return {"status": "success", "metrics": {}}

    metrics = registry.get_gap_metrics() if hasattr(registry, "get_gap_metrics") else {}
    return {
        "status": "success",
        "metrics": metrics,
    }


@router.get("/v1/skills/blueprints")
async def get_pending_blueprints(request: Request):
    """Returns all queued SkillBlueprint artifacts ready for manual review/forging."""
    registry = getattr(request.app.state, "gap_registry", None)
    if not registry or not hasattr(registry, "list_pending_blueprints"):
        return {"status": "success", "count": 0, "blueprints": []}

    blueprints = registry.list_pending_blueprints()
    dumped = []
    for bp in blueprints:
        if hasattr(bp, "model_dump"):
            dumped.append(bp.model_dump())
        elif hasattr(bp, "dict"):
            dumped.append(bp.dict())
        elif isinstance(bp, dict):
            dumped.append(bp)

    return {
        "status": "success",
        "count": len(dumped),
        "blueprints": dumped,
    }


@router.get("/v1/skills/blueprints/{action_name}/prompt")
async def get_gemini_prompt_for_blueprint(action_name: str, request: Request):
    """
    Formats a SkillBlueprint into a structured Gemini Chat prompt ready to copy-paste.
    Designed for dev environments without direct LLM API keys.
    """
    registry = getattr(request.app.state, "gap_registry", None)
    if not registry or not hasattr(registry, "get_blueprint"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Skill Gap Registry unavailable.",
        )

    blueprint = registry.get_blueprint(action_name)
    if not blueprint:
        raise HTTPException(
            status_code=404,
            detail=f"No pending SkillBlueprint found for action '{action_name}'.",
        )

    consumed = ", ".join(blueprint.consumed_artifacts) if getattr(blueprint, "consumed_artifacts", None) else "None"
    produced = ", ".join(blueprint.produced_artifacts) if getattr(blueprint, "produced_artifacts", None) else "None"
    code_draft = getattr(blueprint, "code_draft", None) or "# No dynamic draft recorded."

    ticks = "```"
    formatted_prompt = (
        "You are an expert Python engineer crafting a dynamic skill for the Charon AI Agent Ecosystem.\n\n"
        f"### Target Action Name:\n`{blueprint.action_name}`\n\n"
        "### Skill Blueprint Specifications:\n"
        f"* **Suggested Skill Class Name:** `{getattr(blueprint, 'suggested_skill_name', 'DynamicSkill')}`\n"
        f"* **Description:** {getattr(blueprint, 'description', '')}\n"
        f"* **Consumed Context Inputs:** {consumed}\n"
        f"* **Produced Output Artifacts:** {produced}\n"
        f"* **Sample Dynamic Call:** `{getattr(blueprint, 'sample_call', '')}`\n\n"
        "### Initial Working Code Prototype:\n"
        f"{ticks}python\n{code_draft}\n{ticks}\n\n"
        "### Implementation Requirements:\n"
        "1. Write a clean, complete, and production-ready Python skill module.\n"
        "2. Provide standard input/output validation.\n"
        "3. Ensure it runs statelessly and handles execution exceptions gracefully.\n"
        "4. Return ONLY valid Python code enclosed in a ```python markdown code block."
    )

    return {
        "status": "success",
        "action_name": action_name,
        "copy_paste_prompt": formatted_prompt,
    }


@router.delete("/v1/skills/gaps/{action_name}")
async def reset_skill_gap(action_name: str, request: Request):
    """Resets the failure counter and removes pending blueprint for an action."""
    registry = getattr(request.app.state, "gap_registry", None)
    if registry and hasattr(registry, "reset_gap_counter"):
        registry.reset_gap_counter(action_name)
    return {
        "status": "success",
        "message": f"Gap counter and pending blueprint reset for action '{action_name}'.",
    }


@router.post("/v1/skills/register")
async def register_manual_skill(skill_req: SkillRegisterRequest, request: Request):
    """
    Accepts Python code generated via Gemini Chat, saves it to disk in charon/skills/dynamic/,
    triggers a live scan in SkillLibrarian, and resets the gap counter in SkillGapRegistry.
    """
    registry = getattr(request.app.state, "gap_registry", None)
    if registry and hasattr(registry, "reset_gap_counter"):
        registry.reset_gap_counter(skill_req.action_name)

    skills_dir = Path("charon/skills/dynamic")
    skills_dir.mkdir(parents=True, exist_ok=True)

    file_path = skills_dir / f"{skill_req.skill_name.lower()}.py"
    file_path.write_text(skill_req.code, encoding="utf-8")

    engine = getattr(request.app.state, "engine", None)
    if engine and hasattr(engine, "librarian") and engine.librarian:
        try:
            if hasattr(engine.librarian, "scan_and_register_dynamic_skills"):
                engine.librarian.scan_and_register_dynamic_skills()
        except Exception as err:
            logger.warning(f"Live librarian reload notification skipped: {err}")

    logger.info(f"[Gateway] Skill '{skill_req.skill_name}' successfully ingested into {file_path}.")
    return {
        "status": "success",
        "action_name": skill_req.action_name,
        "skill_name": skill_req.skill_name,
        "saved_path": str(file_path),
        "message": f"Skill '{skill_req.skill_name}' successfully ingested, written to {file_path}, and registered.",
    }


# ============================================================================
# WebSocket Stream
# ============================================================================

@router.websocket("/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
    api_key: Optional[str] = Query(None, alias="api_key"),
):
    """Full-duplex WebSocket stream for desktop extension, CLI, and real-time telemetry."""
    token = _extract_ws_token(websocket, api_key)

    # Validate token if CHARON_API_KEY is defined
    if CHARON_API_KEY:
        if not token or not secrets.compare_digest(token, CHARON_API_KEY):
            logger.warning(f"WebSocket connection rejected for client '{client_id}': Unauthorized.")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await manager.connect(websocket, client_id=client_id)
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
                    "message": "Connected to Charon Gateway Stream",
                },
            ),
        )

        while True:
            raw_data = await websocket.receive_text()
            if not raw_data.strip():
                continue

            try:
                msg = json.loads(raw_data)
                action = msg.get("action") or msg.get("event_type")
                daemon = getattr(websocket.app.state, "daemon", None)

                if action in ("ping", "heartbeat"):
                    await manager.send_event(
                        websocket,
                        WSEvent.model_construct(
                            event_type="status_change",
                            agent_name="System",
                            client_id=client_id,
                            data={"status": "alive", "client_id": client_id},
                        ),
                    )
                elif action == "submit_task":
                    task_id = f"task_{uuid.uuid4().hex[:8]}"
                    effective_client_id = client_id or msg.get("client_id")
                    if daemon and hasattr(daemon, "queue"):
                        await daemon.queue.put({
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

            except json.JSONDecodeError:
                logger.debug(f"Received non-JSON raw WS frame: {raw_data[:50]}")
            except Exception as e:
                logger.error(f"Error handling WS frame from client '{client_id}': {e}", exc_info=True)

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: '{client_id}'")
    except Exception as e:
        logger.error(f"Unexpected WebSocket loop closure for client '{client_id}': {e}")
    finally:
        manager.disconnect(websocket)