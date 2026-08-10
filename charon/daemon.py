"""
charon/daemon.py
System Version: v0.1.0 | File Revision: 1.5.0

Module: Charon Daemon (`charond`) - Gateway Entry Point.

Wires FastAPI network routes, static dashboard serving, persistent queue processing,
state SQLite tables, execution workspace handling, live telemetry bus forwarding,
SkillGapRegistry integration, agent progress callbacks, and proactive task heartbeats
to the central OrchestrationEngine execution loop.
"""

import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from charon.config.logging import setup_logging
from charon.config.paths import ensure_ecosystem_directories
from charon.core.engine import OrchestrationEngine
from charon.core.registry import SkillGapRegistry
from charon.gateway.core import CharonDaemon
from charon.gateway.middleware import APIKeyMiddleware
from charon.gateway.models import WSEvent
from charon.gateway.routes import router as api_router
from charon.gateway.ws import manager
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

# 1. Ensure runtime paths exist and logging handlers are configured
ensure_ecosystem_directories()
setup_logging()

logger = logging.getLogger("Charon.Daemon")

# 2. Initialize engine, gateway daemon wrapper, and central gap registry
engine = OrchestrationEngine()
daemon = CharonDaemon(engine=engine)
gap_registry = SkillGapRegistry.get_instance()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Initializing Charon FastAPI Gateway, Core Engine, Gap Registry, and Persistent Queue..."
    )

    # Expose runtime instances on FastAPI app.state for HTTP and WS route handlers
    app.state.daemon = daemon
    app.state.engine = daemon.engine
    app.state.emitter = daemon.emitter
    app.state.gatekeeper = daemon.gatekeeper
    app.state.concierge = daemon.concierge
    app.state.state_mgr = daemon.state_mgr
    app.state.ledger = daemon.ledger
    app.state.workspace_mgr = daemon.workspace_mgr
    app.state.queue = daemon.queue
    app.state.gap_registry = gap_registry

    # Bridge central TelemetryBus & Agent Progress Callbacks -> Daemon WebSocket Emitter
    loop = asyncio.get_running_loop()

    # =====================================================================
    # ---> Direct UI Telemetry Bridge for Injected Agent Callbacks <---
    def ui_telemetry_bridge(payload: dict) -> None:
        """Callback injected into agents to push live progress updates directly to the GNOME HUD via WebSocket."""
        try:
            ws_event = WSEvent.model_construct(
                event_type=payload.get("type", "task_progress"),
                agent_name=payload.get("agent_name", "System"),
                client_id="desktop_concierge",
                data=payload.get("data", {}),
            )
            # Safely drop the synchronous agent update onto the async WS queue across thread boundary
            asyncio.run_coroutine_threadsafe(manager.broadcast(ws_event), loop)
        except Exception as err:
            logger.error(f"[Daemon] UI Telemetry Bridge error: {err}")

    # Inject the callback into the Dispatcher so it gets bound to every resolved Agent
    if hasattr(engine, "dispatcher") and engine.dispatcher:
        engine.dispatcher.agent_telemetry_callback = ui_telemetry_bridge
        logger.info(
            "[Charon.Daemon] AgentDispatcher injected with ui_telemetry_bridge callback."
        )
    # =====================================================================

    def bridge_telemetry_event(event) -> None:
        """Callback that forwards internal TelemetryBus TraceEvents and Gap Alerts to WebSocket emitter."""
        try:
            # 1. Normalize the event payload (handles both Pydantic models and raw dicts)
            if hasattr(event, "model_dump"):
                event_dict = event.model_dump(mode="json")
            elif hasattr(event, "dict"):
                event_dict = event.dict()
            elif isinstance(event, dict):
                event_dict = event
            else:
                event_dict = vars(event)

            # Safely extract dictionaries and normalize Enum values
            details = event_dict.get("details") or {}
            safe_details = {str(k): str(v) for k, v in details.items()}

            raw_event_type = event_dict.get("event_type", "THINKING")
            event_type_str = (
                raw_event_type.value
                if hasattr(raw_event_type, "value")
                else str(raw_event_type)
            )
            agent_name_str = event_dict.get("agent_name", "Coordinator")

            # 2. Construct the WSEvent
            ws_event = WSEvent.model_construct(
                event_type="telemetry_trace",
                task_id=str(details.get("task_id", "system")),
                client_id="telemetry_viewer",
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

            # 3. Broadcast to all active clients (including the telemetry viewer)
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(ws_event),
                loop,
            )

            # Proactive Skill Blueprint Ready Broadcast
            if details.get("has_blueprint"):
                blueprint_event = WSEvent.model_construct(
                    event_type="skill_blueprint_ready",
                    task_id=str(details.get("task_id", "system")),
                    client_id="telemetry_viewer",
                    agent_name=agent_name_str,
                    data={
                        "agent_name": agent_name_str,
                        "action": event_dict.get("action"),
                        "pending_blueprints": len(
                            gap_registry.get_pending_blueprints()
                        ),
                        "message": "Recurring skill gap threshold met. SkillBlueprint ready for code generation.",
                    },
                )
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast(blueprint_event), loop
                )

            # Diagnostic Gap Detected Broadcast
            if details.get("diagnostics"):
                gap_event = WSEvent.model_construct(
                    event_type="skill_gap_detected",
                    task_id=str(details.get("task_id", "system")),
                    client_id="telemetry_viewer",
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

    # Register subscription handler to live telemetry bus
    telemetry_bus.subscribe(bridge_telemetry_event)
    logger.info(
        "[Charon.Daemon] TelemetryBus subscriber & SkillGap notifier bridged to WebSocket Emitter."
    )

    async def active_task_heartbeat_worker():
        """Periodic background tick emitting heartbeats for active in-flight tasks."""
        while True:
            try:
                await asyncio.sleep(2)
                if hasattr(daemon, "get_active_tasks"):
                    active_tasks = daemon.get_active_tasks()
                    for task in active_tasks:
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

    # Spawn background task workers
    queue_task = asyncio.create_task(
        daemon.process_queue(), name="queue_worker"
    )
    overseer_task = asyncio.create_task(
        daemon.start_overseer_reporter(interval=30), name="overseer_reporter"
    )
    heartbeat_task = asyncio.create_task(
        active_task_heartbeat_worker(), name="task_heartbeat_worker"
    )

    yield

    # =====================================================================
    # ---> TEARDOWN SEQUENCE <---
    # =====================================================================
    logger.info(
        "Shutting down Charon Daemon background tasks and core subsystems..."
    )

    # 1. Unsubscribe from global telemetry bus to prevent memory leaks/dangling callbacks
    if hasattr(telemetry_bus, "unsubscribe"):
        telemetry_bus.unsubscribe(bridge_telemetry_event)
        logger.info("[Charon.Daemon] Unsubscribed from TelemetryBus.")

    # 2. Cancel the background worker loops
    queue_task.cancel()
    overseer_task.cancel()
    heartbeat_task.cancel()
    await asyncio.gather(
        queue_task, overseer_task, heartbeat_task, return_exceptions=True
    )
    logger.info("[Charon.Daemon] Async background workers halted.")

    # 3. Trigger Core Engine / Daemon graceful shutdown
    if hasattr(engine, "shutdown"):
        await engine.shutdown()
        logger.info(
            "[Charon.Daemon] Core OrchestrationEngine safely shut down."
        )

    logger.info("Charon Daemon shutdown complete.")


app = FastAPI(
    title="Charon Engine API Gateway",
    version="3.1.0",
    description="FastAPI Network Gateway, State Engine, and Orchestration Core for Charon.",
    lifespan=lifespan,
)

# Middleware Configuration
app.add_middleware(APIKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST & WebSocket API Routes
app.include_router(api_router)

# Mount Static Dashboard Interface
app.mount(
    "/dashboard",
    StaticFiles(directory="charon/gateway/static/dashboard", html=True),
    name="dashboard",
)


def main():
    uvicorn.run("charon.daemon:app", host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()