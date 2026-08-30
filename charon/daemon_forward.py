# charon/daemon.py
# System Version: v3.6.5

"""
Module: Charon Daemon (`charond`) - Gateway Entry Point.
Integrates resident ConciergeService and core orchestration into the FastAPI lifespan.
"""

import asyncio
from contextlib import asynccontextmanager
import datetime
import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI  # Swapped from native ollama client
import uvicorn

from charon.config.logging import setup_logging
from charon.config.paths import ensure_ecosystem_directories
from charon.config.settings import OLLAMA_HOST
from charon.concierge.core import ConciergeService
from charon.core.orchestration import OrchestrationEngine
from charon.gateway.core import CharonDaemon
from charon.gateway.middleware import APIKeyMiddleware
from charon.gateway.models import WSEvent
from charon.gateway.routes import router as master_api_router
from charon.gateway.ws import manager
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

# 1. Ensure runtime paths exist and logging handlers are configured
ensure_ecosystem_directories()
setup_logging(debug=True)

logger = logging.getLogger("Charon.Daemon")

# NOTE: Heavy instantiations (llm_client, engine, daemon, concierge_service)
# have been moved inside the lifespan below to prevent Uvicorn double-initialization.

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "[Charon.Daemon] Initializing Charon FastAPI Gateway, Core Engine, Persistent Journal, and Concierge..."
    )

    # 1. Initialize an OpenAI-compatible client pointing to Ollama's local server
    # Ensure OLLAMA_HOST doesn't have a trailing slash before appending /v1
    base_url = f"{OLLAMA_HOST.rstrip('/')}/v1"

    llm_client = AsyncOpenAI(
        base_url=base_url,
        api_key="ollama"  # Required by the OpenAI client library, but ignored by Ollama
    )

    concierge_service = ConciergeService(llm_client=llm_client)

    # 2. Inject Concierge directly into the Orchestrator (the Harness owner)
    engine = OrchestrationEngine(
        llm_client=llm_client,
        concierge=concierge_service
    )

    # 3. Initialize Gateway Daemon wrapper
    daemon = CharonDaemon(engine=engine)

    # 4. Await daemon/journal initialization prior to exposing state and serving traffic
    if hasattr(daemon, "initialize"):
        await daemon.initialize()
    elif hasattr(daemon, "journal") and hasattr(daemon.journal, "initialize"):
        await daemon.journal.initialize()

    # -------------------------------------------------------------
    # Crash handler wrapper for asyncio background tasks
    # -------------------------------------------------------------
    def _handle_task_crash(task: asyncio.Task) -> None:
        try:
            if not task.cancelled() and task.exception():
                logger.critical(
                    f"[Charon.Daemon] Background Task '{task.get_name()}' crashed fatally: {task.exception()}",
                    exc_info=task.exception()
                )
        except asyncio.CancelledError:
            pass

    # 5. Bind Unified WebSocket Manager and Awaken resident Concierge
    concierge_service.bind_ws_manager(manager)
    await concierge_service.awaken()
    daemon.concierge = concierge_service

    # Explicitly bind Gateway contexts back to OrchestrationEngine & Coordinator
    engine.bind_gateway_context(
        emitter=getattr(daemon, "emitter", None),
        concierge=concierge_service,
        state_manager=getattr(daemon, "state_mgr", None),
        ledger=getattr(daemon, "ledger", None),
    )
    logger.info("[Charon.Daemon] Gateway and Concierge contexts successfully bound to OrchestrationEngine.")

    # Grab the running loop here so all sync callbacks can dispatch websocket events
    loop = asyncio.get_running_loop()

    # -------------------------------------------------------------
    # Setup HIL / Gatekeeper WebSocket Broadcast
    # -------------------------------------------------------------
    def broadcast_gatekeeper_intercept(action_data: dict):
        """
        Pushes HIL pauses to the GNOME extension via WebSocket,
        triggering the approval prompt.
        """
        logger.info("[Charon.Daemon] Broadcasting Gatekeeper intercept to UI.")
        event = WSEvent.model_construct(
            event_type="gatekeeper_intercept",
            data=action_data,
            client_id="desktop_concierge"
        )
        asyncio.run_coroutine_threadsafe(manager.broadcast(event), loop)

    # Bind the HIL event to the WebSocket broadcast
    if hasattr(daemon, "gatekeeper") and daemon.gatekeeper:
        daemon.gatekeeper.on_intercept = broadcast_gatekeeper_intercept

    # Expose runtime instances on FastAPI app.state for HTTP and WS route handlers
    app.state.daemon = daemon
    app.state.engine = daemon.engine
    app.state.emitter = daemon.emitter
    app.state.gatekeeper = daemon.gatekeeper
    app.state.concierge = concierge_service  # Solves the lifespan duplicate injection
    app.state.state_mgr = daemon.state_mgr
    app.state.ledger = daemon.ledger
    app.state.workspace_mgr = daemon.workspace_mgr
    app.state.queue = daemon.journal

    # Set explicit readiness flag on daemon context
    if hasattr(daemon, "is_ready"):
        daemon.is_ready = True

    # Bridge central TelemetryBus & Agent Progress Callbacks -> Daemon WebSocket Emitter
    # Direct UI Telemetry Bridge for Injected Agent Callbacks
    def ui_telemetry_bridge(payload: dict) -> None:
        """Callback injected into agents to push live progress updates directly to the GNOME HUD via WebSocket."""
        try:
            logger.debug(f"[Daemon.Bridge] Telemetry payload received: {payload.get('type')}")
            ws_event = WSEvent.model_construct(
                event_type=payload.get("type", "task_progress"),
                agent_name=payload.get("agent_name", "System"),
                client_id="desktop_concierge",
                data=payload.get("data", {}),
            )
            asyncio.run_coroutine_threadsafe(manager.broadcast(ws_event), loop)
        except Exception as err:
            logger.error(f"[Daemon] UI Telemetry Bridge error: {err}")

    # Inject the callback into the Coordinator paradigm
    if hasattr(engine, "coordinator") and engine.coordinator:
        engine.coordinator.agent_telemetry_callback = ui_telemetry_bridge
        logger.info(
            "[Charon.Daemon] Coordinator injected with ui_telemetry_bridge callback."
        )
    elif hasattr(engine, "dispatcher") and engine.dispatcher:
        engine.dispatcher.agent_telemetry_callback = ui_telemetry_bridge
        logger.info(
            "[Charon.Daemon] AgentDispatcher injected with ui_telemetry_bridge callback."
        )

    def bridge_telemetry_event(event) -> None:
        """Callback that forwards internal TelemetryBus TraceEvents and Gap Alerts to WebSocket emitter."""
        try:
            if hasattr(event, "model_dump"):
                event_dict = event.model_dump(mode="json")
            elif hasattr(event, "dict"):
                event_dict = event.dict()
            elif isinstance(event, dict):
                event_dict = event
            else:
                event_dict = vars(event)

            raw_event_type = event_dict.get("event_type", "THINKING")
            event_type_str = (
                raw_event_type.value
                if hasattr(raw_event_type, "value")
                else str(raw_event_type)
            )

            # Drop DAG and execution traces (these now route to your new dashboard)
            # as well as noisy internal loop states that the GNOME extension doesn't need.
            if event_type_str in ["telemetry_trace", "dag_node_start", "dag_node_complete", "agent_progress", "THINKING", "ACTION", "OBSERVATION"]:
                return

            details = event_dict.get("details") or {}
            safe_details = {str(k): str(v) for k, v in details.items()}
            agent_name_str = event_dict.get("agent_name", "Coordinator")

            # Forward remaining relevant global states
            ws_event = WSEvent.model_construct(
                event_type=event_type_str,
                task_id=str(details.get("task_id", "system")),
                client_id="desktop_concierge",
                agent_name=agent_name_str,
                data={
                    "event_type": event_type_str,
                    "agent_name": agent_name_str,
                    "action": event_dict.get("action"),
                    "reasoning_chunk": event_dict.get("reasoning_chunk"),
                    "timestamp": event_dict.get("timestamp"),
                    "duration_ms": event_dict.get("duration_ms"),
                    "details": safe_details,
                },
            )

            asyncio.run_coroutine_threadsafe(
                manager.broadcast(ws_event),
                loop,
            )

            if details.get("diagnostics"):
                gap_event = WSEvent.model_construct(
                    event_type="skill_gap_detected",
                    task_id=str(details.get("task_id", "system")),
                    client_id="desktop_concierge",
                    agent_name=agent_name_str,
                    data={
                        "agent_name": agent_name_str,
                        "action": event_dict.get("action"),
                        "diagnostics": str(details.get("diagnostics")),
                    },
                )
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast(gap_event), loop
                )

        except Exception as err:
            logger.error(
                f"[Daemon] FATAL Telemetry bridge error: {err}", exc_info=True
            )

    telemetry_bus.subscribe(bridge_telemetry_event)
    logger.info(
        "[Charon.Daemon] TelemetryBus subscriber bridged to WebSocket Emitter."
    )

    async def active_task_heartbeat_worker():
        """Periodic background tick emitting heartbeats for active in-flight tasks."""
        while True:
            try:
                await asyncio.sleep(2)
                if hasattr(daemon, "get_active_tasks"):
                    active_tasks = daemon.get_active_tasks()
                    for task in active_tasks:
                        if hasattr(daemon, "emitter") and daemon.emitter:
                            await daemon.emitter.emit(
                                event_type="task_heartbeat",
                                task_id=task.get("id"),
                                client_id=task.get("client_id"),
                                data={
                                    "status": task.get("status", "processing"),
                                    "active_agent": task.get(
                                        "assigned_agent", "Orchestrator"
                                    ),
                                    "elapsed_seconds": task.get("elapsed", 0),
                                },
                            )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(
                    f"Task heartbeat worker encountered an anomaly: {e}"
                )

    # Spawn background task workers with crash handlers
    queue_task = asyncio.create_task(
        daemon.process_queue(), name="queue_worker"
    )
    queue_task.add_done_callback(_handle_task_crash)

    overseer_task = asyncio.create_task(
        daemon.start_overseer_reporter(interval=30), name="overseer_reporter"
    )
    overseer_task.add_done_callback(_handle_task_crash)

    heartbeat_task = asyncio.create_task(
        active_task_heartbeat_worker(), name="task_heartbeat_worker"
    )
    heartbeat_task.add_done_callback(_handle_task_crash)

    logger.info("[Charon.Daemon] Gateway, Task Queue, and Concierge fully ready for operation.")
    yield

    # Teardown
    logger.info("[Charon.Daemon] Shutting down Charon Daemon background tasks and core subsystems...")

    # Stand down resident Concierge background clock routines
    await concierge_service.sleep()

    if hasattr(telemetry_bus, "unsubscribe"):
        telemetry_bus.unsubscribe(bridge_telemetry_event)

    queue_task.cancel()
    overseer_task.cancel()
    heartbeat_task.cancel()

    await asyncio.gather(
        queue_task, overseer_task, heartbeat_task, return_exceptions=True
    )

    if hasattr(engine, "shutdown"):
        await engine.shutdown()

    logger.info("[Charon.Daemon] Daemon shutdown complete.")


app = FastAPI(
    title="Charon Engine API Gateway",
    version="3.1.0",
    description="FastAPI Network Gateway, State Engine, and Orchestration Core for Charon.",
    lifespan=lifespan,
)

app.add_middleware(APIKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core API routes and Control Plane endpoints
app.include_router(master_api_router)

# Serve Dashboard V2 compiled static assets from dist/
current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "gateway", "static", "dashboard_v2", "dist")

if not os.path.exists(static_dir):
    logger.error(f"[Charon.Daemon] CRITICAL: Static dist directory not found at {static_dir}. Run 'npm run build' in dashboard_v2.")
else:
    logger.info(f"[Charon.Daemon] Serving production static bundle from: {static_dir}")

# Mount /assets explicitly for minified JS and CSS bundles
assets_dir = os.path.join(static_dir, "assets")
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# SPA catch-all: returns requested physical file or falls back to index.html
@app.get("/{catchall:path}")
async def serve_spa(catchall: str):
    # 1. Reject API routes immediately so they return proper 404 JSON errors
    if catchall.startswith("v1/") or catchall.startswith("api/"):
        raise HTTPException(status_code=404, detail="API Route Not Found")

    # 2. Serve static files or fallback to index.html
    file_path = os.path.join(static_dir, catchall)
    if catchall and os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(os.path.join(static_dir, "index.html"))

def main():
    uvicorn.run(
        "charon.daemon:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        ws_ping_interval=20.0,
        ws_ping_timeout=20.0
    )

if __name__ == "__main__":
    main()