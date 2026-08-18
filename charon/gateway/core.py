"""
charon/gateway/core.py
System Version: v0.1.1 | File Revision: 2.1.4

Module: Charon Core Daemon Orchestrator.

Central daemon managing lifecycle execution state, persistent task queue processing,
workspace isolation, Gatekeeper authorization resolution, and client event broadcasting.
"""

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.config import (
    DEFAULT_CONCIERGE_MIN_CONFIDENCE,
    DEFAULT_HEAVY_MODEL,
    DEFAULT_TRIAGE_MODEL,
    PROJECT_MEMORY_DIR,
    ensure_ecosystem_directories,
)
from charon.ux.concierge import ConciergeService
from charon.core.orchestration import OrchestrationEngine
from charon.telemetry.ledger import ExecutionLedger
from charon.gateway.journal import GatewayJournal
from charon.core.session import SessionGateway
from charon.core.state import StateManager, TaskStatus
from charon.core.workspace import WorkspaceManager
from charon.gateway.emitter import EventEmitter
from charon.gateway.gatekeeper import GatekeeperManager
from charon.gateway.models import WSEvent
from charon.gateway.telemetry import TelemetryReporter

logger = logging.getLogger("Charon.Gateway.Core")


class DaemonLogInterceptor(logging.Handler):
    """
    Taps into internal python loggers (Charon and CHAROND) during task execution
    and converts structural log events into real-time WebSocket progress frames.
    """

    def __init__(self, daemon: "CharonDaemon", main_loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.daemon = daemon
        self.main_loop = main_loop

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Only intercept log records from Charon core modules and domain agents
            if not (record.name.startswith("Charon") or record.name.startswith("CHAROND")):
                return

            task_id = getattr(self.daemon.emitter, "current_task_id", None)
            client_id = getattr(self.daemon.emitter, "current_client_id", None)
            if not task_id or not client_id:
                return

            msg = record.getMessage()

            # Ignore network/polling HTTP noise
            if "httpx" in record.name or "HTTP Request" in msg or "WebSocket" in msg:
                return

            event_type = "task_progress"
            data: Dict[str, Any] = {
                "message": msg,
                "logger": record.name,
                "level": record.levelname,
            }

            # Map domain log events to CLI-understood WebSocket events
            if "Parser" in record.name and "routed task to:" in msg:
                target_agent = msg.split("routed task to:")[-1].strip()
                event_type = "agent_action"
                data.update({
                    "agent": target_agent,
                    "action": f"Task routed to {target_agent}",
                    "phase": "triage",
                })
            elif "Coordinator" in record.name:
                event_type = "agent_action"
                data.update({
                    "agent": "Coordinator",
                    "action": msg,
                    "phase": "reflection_loop",
                })
            elif "Dispatcher" in record.name and "Executing task:" in msg:
                event_type = "agent_action"
                data.update({
                    "action": msg,
                    "phase": "dispatch",
                })
            elif any(domain in record.name for domain in
                     ["Quartermaster", "Generalist", "Engineer", "Archivist", "Steward", "Spark", "Machinist"]):
                event_type = "step"
                data.update({"step": msg})

            event = WSEvent(
                event_type=event_type,
                task_id=task_id,
                data=data,
            )

            # Schedule emission on the main event loop across thread boundaries without blocking
            try:
                asyncio.run_coroutine_threadsafe(
                    self.daemon.emitter.emit_targeted(event),
                    self.main_loop
                )
            except Exception:
                pass
        except Exception:
            self.handleError(record)


class CharonDaemon:
    """Central orchestrator daemon managing persistent journals, state tables, and dispatch execution."""

    def __init__(
        self,
        engine: Optional[OrchestrationEngine] = None,
        heavy_model: str = DEFAULT_HEAVY_MODEL,
        triage_model: str = DEFAULT_TRIAGE_MODEL,
        db_path: Optional[Union[str, Path]] = None,
        concierge_min_confidence: float = DEFAULT_CONCIERGE_MIN_CONFIDENCE,
    ):
        ensure_ecosystem_directories()
        self.db_path: Path = Path(db_path) if db_path else PROJECT_MEMORY_DIR

        # Explicit readiness flag used by API routes to check availability
        self.is_ready: bool = False

        # Initialize SQLite State, Ledger, and Workspace Managers
        self.state_mgr = StateManager()
        self.ledger = ExecutionLedger()
        self.workspace_mgr = WorkspaceManager()

        # Replaced CoordinatorJournal with GatewayJournal
        self.journal = GatewayJournal(state_manager=self.state_mgr)

        if engine:
            self.engine = engine
            self.orchestrator = SessionGateway(engine=self.engine, journal=self.journal)
        else:
            self.engine = OrchestrationEngine(
                heavy_model=heavy_model,
                triage_model=triage_model,
                state_manager=self.state_mgr,
                ledger=self.ledger,
            )
            self.orchestrator = SessionGateway(engine=self.engine, journal=self.journal)

        # Initialize Concierge with confidence threshold guardrails and required LLM client
        llm_instance = getattr(self.engine, "llm_client", getattr(self.engine, "llm", self.engine))
        self.concierge = ConciergeService(
            llm_client=llm_instance,
            min_confidence=concierge_min_confidence
        )

        self.emitter = EventEmitter()
        self.gatekeeper = GatekeeperManager()

        # Bind gateway components directly to engine context
        self.engine.bind_gateway_context(
            emitter=self.emitter,
            state_manager=self.state_mgr,
            ledger=self.ledger,
        )

        # Updated TelemetryReporter instantiation pointing to the new journal
        self.telemetry = TelemetryReporter(
            queue_provider=self.journal.qsize if hasattr(self.journal, "qsize") else lambda: 0,
            gatekeeper_status_provider=lambda: self.gatekeeper.awaiting_approval,
            task_provider=lambda: self.emitter.current_task_id,
            state_manager=self.state_mgr,
        )

        # Retrieve the main event loop to safely pass to the background logger
        try:
            self.main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self.main_loop = asyncio.get_event_loop()

        # Attach real-time log interceptor to root logger hierarchy
        self.log_interceptor = DaemonLogInterceptor(self, self.main_loop)
        logging.getLogger().addHandler(self.log_interceptor)

    @property
    def awaiting_gatekeeper(self) -> bool:
        """Backward compatibility helper for gatekeeper state."""
        return self.gatekeeper.awaiting_approval

    async def verify_engine(self, retries: int = 3, delay: float = 3.0) -> bool:
        """Verify inference engine availability."""
        return await self.telemetry.verify_engine(retries=retries, delay=delay)

    async def evaluate_and_emit_concierge(
        self,
        user_input: str,
        result_text: str,
        completed_action: str = "",
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Flexible Concierge evaluator with dynamic parameter inspection and authorization guards."""
        if not self.concierge or not self.emitter:
            return

        # Explicit Authorization Guardrail: Suppress suggestions if result indicates gatekeeper intercept
        if result_text and str(result_text).startswith("[Awaiting Authorization]"):
            logger.debug("[CONCIERGE] Task result awaiting authorization. Suppressing evaluation.")
            return

        # Notify UI that Concierge is evaluating follow-ups
        await self.emitter.emit_targeted(
            WSEvent(
                event_type="agent_action",
                task_id=self.emitter.current_task_id,
                data={
                    "agent": "Concierge",
                    "action": "Evaluating proactive proposals...",
                    "phase": "concierge_eval",
                },
            )
        )

        try:
            eval_fn = getattr(
                self.concierge,
                "evaluate_next_step",
                getattr(self.concierge, "get_next_step", None),
            )
            if not eval_fn:
                logger.warning("Concierge instance has no valid evaluation method.")
                return

            sig = inspect.signature(eval_fn)
            fn_params = sig.parameters

            kwargs: Dict[str, Any] = {}
            if "user_query" in fn_params:
                kwargs["user_query"] = user_input
            elif "query" in fn_params:
                kwargs["query"] = user_input
            elif "prompt" in fn_params:
                kwargs["prompt"] = user_input

            if "completed_action" in fn_params:
                kwargs["completed_action"] = completed_action
            elif "action" in fn_params:
                kwargs["action"] = completed_action

            if "execution_result" in fn_params:
                kwargs["execution_result"] = str(result_text)
            elif "result" in fn_params:
                kwargs["result"] = str(result_text)

            if "params" in fn_params:
                kwargs["params"] = params or {}

            if kwargs:
                coro_or_res = eval_fn(**kwargs)
            else:
                coro_or_res = eval_fn(user_input, completed_action, str(result_text))

            suggestion = (
                await coro_or_res if inspect.iscoroutine(coro_or_res) else coro_or_res
            )

            if suggestion:
                logger.info(f"Concierge generated proposal: {suggestion}")
                await self.emitter.emit_concierge(suggestion)
            else:
                logger.debug("Concierge evaluated task context and returned no proposal.")

        except Exception as concierge_err:
            logger.warning(f"Concierge evaluation error: {concierge_err}", exc_info=True)

    async def start_overseer_reporter(self, interval: int = 5) -> None:
        """Start background telemetry reporting task."""
        await self.telemetry.start_loop(interval=interval)

    async def process_queue(self) -> None:
        """Primary queue processing loop for incoming task directives and gatekeeper decisions."""
        while not await self.verify_engine():
            logger.warning("Inference engine unavailable. Retrying verification in 10s...")
            await asyncio.sleep(10)

        logger.info("Inference engine verification complete. Gateway daemon active.")

        # Recover pending or interrupted tasks from SQLite state DB upon daemon startup
        if hasattr(self.journal, "initialize_and_recover"):
            recovered_count = await self.journal.initialize_and_recover()
            logger.info(
                f"Charon daemon persistent journal processor operational. "
                f"Recovered {recovered_count} task(s) from persistent state storage."
            )

        # Update readiness flag after engine check and recovery sequence resolve
        self.is_ready = True
        logger.info("Daemon state updated: is_ready = True")

        # Emit gateway initialization complete event
        await self.emitter.emit_targeted(
            WSEvent(
                event_type="gateway_ready",
                data={
                    "status": "ready",
                    "message": "Engine check complete. Task queue initialized and ready to receive requests."
                },
            )
        )

        while True:
            try:
                item = await self.journal.get()
            except asyncio.CancelledError:
                break

            # Safely handle both legacy dictionary payloads and new typed JournalEntry objects
            if isinstance(item, dict):
                task_id = item.get("task_id")
                client_id = item.get("client_id")
                user_input = str(item.get("prompt", "")).strip()
                agent_override_str = item.get("target_role", item.get("agent_override"))
                routing_hint_payload = item.get("routing_hint")
                approval_id = item.get("approval_id")
                decision = item.get("decision")
            else:
                task_id = getattr(item, "task_id", None)
                client_id = getattr(item, "client_id", None)
                user_input = str(getattr(item, "prompt", "")).strip()
                agent_override_str = getattr(item, "target_role", getattr(item, "agent_override", None))
                routing_hint_payload = getattr(item, "routing_hint", None)
                approval_id = getattr(item, "approval_id", None)
                decision = getattr(item, "decision", None)

            try:
                self.emitter.set_context(task_id=task_id, client_id=client_id)

                # 1. Direct Gatekeeper Approval/Denial Payload
                if approval_id and decision:
                    logger.info(f"Processing Gatekeeper decision '{decision}' for intercept {approval_id}")
                    if hasattr(self.gatekeeper, "resolve_intercept"):
                        self.gatekeeper.resolve_intercept(approval_id, decision)
                    elif hasattr(self.gatekeeper, "submit_decision"):
                        self.gatekeeper.submit_decision(approval_id, decision)

                    if task_id:
                        await self.ledger.log_event(
                            task_id=task_id,
                            event_type="gatekeeper_decision",
                            data={"approval_id": approval_id, "decision": decision},
                        )
                    continue

                # 2. String Command Approval Fallback
                if self.gatekeeper.awaiting_approval and user_input.lower() in [
                    "proceed", "yes", "approve", "cancel", "abort", "no"
                ]:
                    cmd = user_input.lower()
                    dec = "APPROVED" if cmd in ["proceed", "yes", "approve"] else "REJECTED"
                    active_id = getattr(self.gatekeeper, "active_approval_id", None)
                    if active_id and hasattr(self.gatekeeper, "resolve_intercept"):
                        self.gatekeeper.resolve_intercept(active_id, dec)
                        if task_id:
                            await self.ledger.log_event(
                                task_id=task_id,
                                event_type="gatekeeper_string_response",
                                data={"approval_id": active_id, "decision": dec},
                            )

                        # FIX 3: Acknowledge the user's command before continuing
                        await self.emitter.emit_completed(f"[Authorization {dec}]")
                        continue

                # 3. Standard Request Execution Phase
                if task_id:
                    self.workspace_mgr.get_task_workspace(task_id, create=True)
                    await self.state_mgr.update_status(task_id, TaskStatus.RUNNING)
                    await self.ledger.log_event(
                        task_id=task_id,
                        event_type="task_started",
                        data={
                            "prompt": user_input,
                            "agent_override": agent_override_str,
                            "has_routing_hint": bool(routing_hint_payload),
                        },
                    )

                # Initial status notification
                await self.emitter.emit_targeted(
                    WSEvent(
                        event_type="status_change",
                        task_id=task_id,
                        data={"status": "executing", "prompt": user_input},
                    )
                )

                # Emit initial Triage Router progress event
                await self.emitter.emit_targeted(
                    WSEvent(
                        event_type="agent_action",
                        task_id=task_id,
                        data={
                            "agent": "Triage Router",
                            "action": "Analyzing intent & selecting agent...",
                            "phase": "triage_start",
                        },
                    )
                )

                def stream_cb(msg: str):
                    """Callback bridging streamed model outputs & progress indicators to WS."""
                    asyncio.create_task(self.emitter.emit_stream(msg))

                    if msg.startswith("[") and "]" in msg and ":" in msg:
                        try:
                            tag_content = msg[1:msg.find("]")]
                            agent_name, action_text = [s.strip() for s in tag_content.split(":", 1)]
                            asyncio.create_task(
                                self.emitter.emit_targeted(
                                    WSEvent(
                                        event_type="agent_action",
                                        task_id=task_id,
                                        data={
                                            "agent": agent_name,
                                            "action": action_text,
                                            "phase": "execution",
                                        },
                                    )
                                )
                            )
                        except Exception:
                            pass

                result = await self.engine.process_request(
                    user_input=user_input,
                    stream_cb=stream_cb,
                    agent_override=agent_override_str,
                    task_id=task_id,
                    routing_hint=routing_hint_payload,
                )

                # FIX 1 & 2: Structural conditionals logic mapping the event emitter
                if result:
                    if not str(result).startswith("[Awaiting Authorization]"):
                        if task_id:
                            await self.state_mgr.update_status(task_id, TaskStatus.COMPLETED)
                            await self.ledger.log_event(
                                task_id=task_id,
                                event_type="task_completed",
                                data={"result_summary": str(result)[:300]},
                            )
                        if hasattr(self.orchestrator, "memory"):
                            self.orchestrator.memory.add_system_message(str(result))

                        await self.evaluate_and_emit_concierge(
                            user_input=user_input,
                            result_text=result,
                            completed_action=agent_override_str or "task_execution",
                            params=item if isinstance(item, dict) else item.__dict__ if hasattr(item, "__dict__") else None,
                        )

                        # Emit standard success
                        await self.emitter.emit_completed(result)

                    else:
                        if task_id:
                            await self.state_mgr.update_status(
                                task_id,
                                TaskStatus.AWAITING_APPROVAL,
                                approval_id=getattr(self.gatekeeper, "active_approval_id", None),
                            )
                            await self.ledger.log_event(
                                task_id=task_id,
                                event_type="task_intercepted",
                                data={"reason": result},
                            )

                        # FIX 1: Actually emit the authorization request to the user
                        await self.emitter.emit_completed(result)
                else:
                    # FIX 2: Catch-all for engine returning None or empty strings
                    msg = "[System Notice] Engine returned an empty response."
                    if task_id:
                        await self.state_mgr.update_status(task_id, TaskStatus.FAILED, error_message=msg)
                    await self.emitter.emit_completed(msg)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error processing journal entry for task '{task_id}': {e}", exc_info=True)
                if task_id:
                    await self.state_mgr.update_status(
                        task_id, TaskStatus.FAILED, error_message=str(e)
                    )
                    await self.ledger.log_event(
                        task_id=task_id,
                        event_type="task_failed",
                        data={"error": str(e)},
                    )
                await self.emitter.emit_completed(f"[System Error]: {str(e)}")
            finally:
                self.emitter.clear_context()
                if hasattr(self.journal, "task_done"):
                    self.journal.task_done()

    async def shutdown(self) -> None:
        """
        Gracefully terminate engine sub-components, halt in-flight agent tasks,
        and close persistent database connections.
        """
        self.is_ready = False
        logger.info("Initiating OrchestrationEngine shutdown sequence...")

        # 1. Halt the DAG Executor (Stops new nodes from being dispatched)
        dag_executor = getattr(self.engine, "dag_executor", getattr(self.orchestrator, "dag_executor", None))
        if dag_executor and hasattr(dag_executor, "shutdown"):
            try:
                if inspect.iscoroutinefunction(dag_executor.shutdown):
                    await dag_executor.shutdown()
                else:
                    dag_executor.shutdown()
                logger.debug("DAG Executor shutdown complete.")
            except Exception as e:
                logger.error(f"Error shutting down DAG executor: {e}")

        # 2. Halt Orchestrator (Kills active agent loops, flushes ChromaDB)
        if hasattr(self.orchestrator, "shutdown"):
            try:
                if inspect.iscoroutinefunction(self.orchestrator.shutdown):
                    await self.orchestrator.shutdown()
                else:
                    self.orchestrator.shutdown()
                logger.debug("Orchestrator shutdown complete.")
            except Exception as e:
                logger.error(f"Error shutting down Orchestrator: {e}")

        # 3. Safely Close SQLite Connections (State, Ledger, Librarian)
        librarian = getattr(self.engine, "librarian", getattr(self.orchestrator, "librarian", None))
        persistent_stores = [
            (self.state_mgr, "StateManager"),
            (self.ledger, "ExecutionLedger"),
        ]
        if librarian:
            persistent_stores.append((librarian, "SkillLibrarian"))

        for component, name in persistent_stores:
            # Handle both .close() and .shutdown() naming conventions
            teardown_fn = getattr(component, "close", getattr(component, "shutdown", None))
            if teardown_fn:
                try:
                    if inspect.iscoroutinefunction(teardown_fn):
                        await teardown_fn()
                    else:
                        teardown_fn()
                    logger.debug(f"Closed {name} persistent connections.")
                except Exception as e:
                    logger.error(f"Error closing {name}: {e}")

        logger.info("OrchestrationEngine shutdown sequence finalized.")