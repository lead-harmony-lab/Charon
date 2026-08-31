"""
charon/core/orchestration.py
System Version: v2.3.0 | File Revision: 2.8.0

Module: Main Orchestration Engine facade for Charon.
Refactored for the Active Execution Envelope paradigm and Y-Junction Intent Routing.
Delegates strictly to the Coordinator for execution and the Concierge for UX proposals / conversational bypass.
Updated: Direct SkillLibrarian encapsulation, native async execution via _safe_execute,
sensory context enrichment, Y-junction semantic gateway (task override, chat bypass, HIL authorization),
circuit breaker safety interrupts, fail-safe state recovery, and passive Concierge ingress/egress observation hooks.
"""

import inspect
import logging
from typing import Any, Callable, Dict, Optional, Tuple

from charon.config.paths import STATE_DB_PATH
from charon.telemetry.ledger import ExecutionLedger
from charon.core.skills import SkillLibrarian
from charon.core.state import StateManager
from charon.core.coordinator.engine import Coordinator, _safe_execute
from charon.core.coordinator.blackboard import TaskBlackboard

logger = logging.getLogger("Charon.Engine")

REQUIRED_SYSTEM_ROLES: Tuple[str, ...] = (
    "system_generalist",
    "system_engineer",
    "system_planner",
    "system_fallback",
)


class OrchestrationEngine:
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        concierge: Optional[Any] = None,
        heavy_model: str = "llama3.1",
        triage_model: str = "llama3.1",
        state_manager: Optional[StateManager] = None,
        ledger: Optional[ExecutionLedger] = None,
        librarian: Optional[SkillLibrarian] = None,
        gatekeeper: Optional[Any] = None,
    ):
        logger.info(
            f"[ENGINE] Initializing OrchestrationEngine (heavy_model='{heavy_model}', "
            f"triage_model='{triage_model}', llm_client={bool(llm_client)})"
        )
        self.llm_client = llm_client
        self.librarian = librarian or SkillLibrarian.get_instance()
        self.gatekeeper = gatekeeper
        self.state_mgr = state_manager
        self.ledger = ledger
        self.emitter = None
        self.concierge = concierge

        if self.concierge and self.gatekeeper:
            self.concierge.gatekeeper = self.gatekeeper

        self._verify_required_system_roles()

        logger.debug(f"[ENGINE] Initializing Coordinator with STATE_DB_PATH='{STATE_DB_PATH}'")

        self.coordinator = Coordinator(
            db_path=STATE_DB_PATH,
            gatekeeper=self.gatekeeper,
            ledger=self.ledger,
            heavy_model=heavy_model,
        )

        if self.llm_client:
            self.coordinator.llm_client = self.llm_client

        logger.info("[ENGINE] OrchestrationEngine initialization complete.")

    def _verify_required_system_roles(self) -> None:
        """Verifies that all required system roles can be resolved by SkillLibrarian."""
        logger.info(f"[ENGINE] Verifying required system role mappings: {REQUIRED_SYSTEM_ROLES}")
        if hasattr(self.librarian, "validate_core_roles"):
            is_valid = self.librarian.validate_core_roles()
            logger.debug(f"[ENGINE] SkillLibrarian.validate_core_roles() returned: {is_valid}")
            if not is_valid:
                logger.warning("[ENGINE] Librarian reported missing or inactive core role mappings.")

        missing_roles = []
        for role in REQUIRED_SYSTEM_ROLES:
            try:
                agent_id = self.librarian.resolve_agent_id_for_role(role)
                if agent_id:
                    logger.debug(f"[ENGINE] Role check passed: '{role}' -> '{agent_id}'")
                else:
                    logger.warning(f"[ENGINE] Role check failed: '{role}' could not be resolved.")
                    missing_roles.append(role)
            except Exception as err:
                logger.critical(f"[ENGINE] Exception while resolving mandatory system role '{role}': {err}", exc_info=True)
                missing_roles.append(role)

        if missing_roles:
            fatal_msg = (
                f"CRITICAL STARTUP FAILURE: SkillLibrarian could not resolve required system roles: "
                f"{missing_roles}. System halting."
            )
            logger.critical(fatal_msg)
            raise RuntimeError(fatal_msg)

        logger.info("[ENGINE] System roles verification passed successfully.")

    def bind_gateway_context(
        self,
        emitter: Optional[Any] = None,
        concierge: Optional[Any] = None,
        state_manager: Optional[StateManager] = None,
        ledger: Optional[ExecutionLedger] = None,
    ) -> None:
        """Bind Gateway contexts and cascade them down to the Coordinator."""
        logger.info("[ENGINE] Binding Gateway context...")
        self.emitter = emitter
        if concierge:
            self.concierge = concierge
            if self.gatekeeper:
                self.concierge.gatekeeper = self.gatekeeper
        if state_manager:
            self.state_mgr = state_manager
        if ledger:
            self.ledger = ledger

        logger.info(
            f"[ENGINE] Gateway context bound: emitter={bool(self.emitter)}, "
            f"concierge={bool(self.concierge)}, state_mgr={bool(self.state_mgr)}, ledger={bool(self.ledger)}"
        )

        if hasattr(self, "coordinator") and self.coordinator:
            self.coordinator.emitter = self.emitter
            self.coordinator.ledger = self.ledger
            self.coordinator.state_mgr = self.state_mgr
            logger.info("[ENGINE] Gateway contexts successfully cascaded to Coordinator.")
        else:
            logger.warning("[ENGINE] Unable to cascade contexts: Coordinator attribute missing or None.")

    async def shutdown(self) -> None:
        """Gracefully shuts down engine components during daemon teardown."""
        logger.info("[ENGINE] Initiating engine teardown sequence...")
        if hasattr(self.coordinator, "shutdown"):
            logger.debug("[ENGINE] Executing coordinator shutdown...")
            if inspect.iscoroutinefunction(self.coordinator.shutdown):
                await self.coordinator.shutdown()
            else:
                self.coordinator.shutdown()
            logger.info("[ENGINE] Coordinator shutdown complete.")
        else:
            logger.debug("[ENGINE] Coordinator has no custom shutdown method.")
        logger.info("[ENGINE] Engine teardown complete.")

    async def process_request(
        self,
        user_input: str,
        stream_cb: Optional[Callable[[str], None]] = None,
        agent_override: Optional[str] = None,
        task_id: Optional[str] = None,
        routing_hint: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Primary execution lifecycle controller with telemetry integration & circuit breaking."""
        raw_prompt = user_input.strip() if user_input else ""
        if not raw_prompt:
            logger.warning("[ENGINE] Received empty prompt, aborting request execution.")
            return "Error: Empty prompt received."

        # Guard against NoneType defaults crashing downstream merges
        routing_hint = routing_hint or {}

        logger.info(
            f"[ENGINE.PATHWAY] Enter process_request [Task ID: {task_id or 'volatile'}] "
            f"Override: {agent_override} | Routing Hint: {routing_hint} | Prompt: '{raw_prompt[:60]}...'"
        )

        exec_prompt = raw_prompt

        # 1. Harness State Transition -> RUNNING
        if self.concierge and hasattr(self.concierge, "set_harness_state"):
            await _safe_execute(self.concierge.set_harness_state, "RUNNING", task_id=task_id)

        # 1.5 Concierge Ingress Observation (Context enrichment & memory capture)
        if self.concierge and hasattr(self.concierge, "observe_ingress"):
            logger.debug(f"[ENGINE.PATHWAY] Invoking Concierge observe_ingress [Task ID: {task_id}]...")
            ingress_result = await _safe_execute(
                self.concierge.observe_ingress,
                task_id=task_id,
                prompt=raw_prompt,
                metadata=routing_hint,
            )
            # Safely capture BOTH modified prompt and enriched metadata
            if isinstance(ingress_result, tuple):
                if len(ingress_result) >= 1:
                    exec_prompt = ingress_result[0] or exec_prompt
                if len(ingress_result) >= 2 and isinstance(ingress_result[1], dict):
                    routing_hint.update(ingress_result[1])
            elif isinstance(ingress_result, str) and ingress_result:
                exec_prompt = ingress_result

        # 2. Sensory Context Enrichment
        sensory_context = {}
        if self.concierge and hasattr(self.concierge, "get_sensory_snapshot"):
            try:
                sensory_context = await _safe_execute(self.concierge.get_sensory_snapshot) or {}
                logger.debug(f"[ENGINE.OBSERVER] Injected sensory snapshot keys: {list(sensory_context.keys())}")
            except Exception as context_err:
                logger.warning(f"[ENGINE.OBSERVER] Failed to capture sensory snapshot: {context_err}")

        # 3. Telemetry Broadcast
        if self.emitter:
            try:
                emit_event_fn = getattr(
                    self.emitter, "emit_system_event", getattr(self.emitter, "emit_event", None)
                )
                if emit_event_fn:
                    event_payload = {
                        "event_type": "task_progress",
                        "task_id": task_id,
                        "agent_override": agent_override,
                        "status": "in_progress",
                        "sensory_context": sensory_context,
                    }
                    logger.debug(f"[ENGINE.PATHWAY] Emitting task_progress event: {event_payload}")
                    res_emit = emit_event_fn(event_payload)
                    if inspect.isawaitable(res_emit):
                        await res_emit
                    logger.info("[ENGINE.PATHWAY] Initial task_progress event emitted.")
                else:
                    logger.warning("[ENGINE.PATHWAY] Emitter present but no valid emit_event method found.")
            except Exception as ack_err:
                logger.debug(f"[ENGINE] Telemetry dispatch fallback error: {ack_err}", exc_info=True)
        else:
            logger.warning("[ENGINE.PATHWAY] self.emitter is None. Skipping initial telemetry broadcast.")

        # 4. Safety Circuit Breaker Interrupt
        if self.concierge and hasattr(self.concierge, "check_for_critical_alerts"):
            critical_alert = await _safe_execute(self.concierge.check_for_critical_alerts)
            if critical_alert:
                logger.warning(f"[ENGINE.SAFETY] Execution halted by telemetry circuit breaker: {critical_alert}")
                if hasattr(self.concierge, "set_harness_state"):
                    await _safe_execute(self.concierge.set_harness_state, "FAULTED", task_id=task_id)
                return {"error": "System Safety Interrupt", "message": critical_alert}

        # 4.5 The Y-Junction: Syntax Routing & Semantic Gateway
        is_explicit_task = exec_prompt.lower().startswith("task: ")
        route_to_engine = is_explicit_task
        result: Any = None
        completed_blackboard = None

        # Configure the threshold required to bypass Human-in-the-Loop authorization
        MIN_CONFIDENCE_THRESHOLD = 0.85

        if is_explicit_task:
            exec_prompt = exec_prompt[6:].strip()
            logger.info(
                f"[ENGINE.ROUTER] Hard override detected ('task: '). Routing directly to Engine: '{exec_prompt[:50]}...'")
        elif self.concierge and hasattr(self.concierge, "classify_intent"):
            logger.debug("[ENGINE.ROUTER] No syntax override detected. Querying Concierge semantic gateway...")

            intent = await _safe_execute(
                self.concierge.classify_intent,
                prompt=exec_prompt,
                context=sensory_context
            )

            if intent == "chat":
                logger.info("[ENGINE.ROUTER] Intent classified as conversational. Bypassing Engine.")
                chat_response = await _safe_execute(
                    self.concierge.handle_conversational_bypass,
                    prompt=exec_prompt,
                    context=sensory_context
                )
                result = {"result": chat_response, "type": "chat_bypass"}
                route_to_engine = False

            else:
                logger.info(
                    "[ENGINE.ROUTER] Intent classified as agentic task. Evaluating autonomous confidence...")

                # Check historical approval confidence to potentially bypass HIL
                confidence = 0.0
                if hasattr(self.concierge, "memory") and hasattr(self.concierge.memory,
                                                                 "evaluate_routing_confidence"):
                    confidence = await _safe_execute(
                        self.concierge.memory.evaluate_routing_confidence,
                        intent_summary=exec_prompt,
                        sensory_context=sensory_context
                    ) or 0.0

                if confidence >= MIN_CONFIDENCE_THRESHOLD:
                    logger.info(
                        f"[ENGINE.ROUTER] Autonomous routing confidence ({confidence:.2f}) meets threshold. Bypassing HIL.")
                    route_to_engine = True
                else:
                    logger.info(
                        f"[ENGINE.ROUTER] Routing confidence ({confidence:.2f}) below threshold. Triggering HIL Gatekeeper...")
                    auth_granted = await _safe_execute(
                        self.concierge.request_hil_authorization,
                        task_id=task_id,
                        intent_summary=exec_prompt
                    )

                    if auth_granted:
                        logger.info("[ENGINE.ROUTER] HIL authorization GRANTED. Proceeding to Engine.")
                        route_to_engine = True
                    else:
                        logger.warning("[ENGINE.ROUTER] HIL authorization DENIED. Aborting task.")
                        result = {"error": "HIL_DENIED", "message": "User aborted task via Gatekeeper UI."}
                        route_to_engine = False
        else:
            logger.warning(
                "[ENGINE.ROUTER] Semantic gateway unavailable. Defaulting to engine execution for safety.")
            route_to_engine = True

        # Conditional Orchestration Execution Path
        if route_to_engine:
            try:
                # 5. Topology & Catalog Audit
                logger.debug("[ENGINE.PATHWAY] Fetching system topology from SkillLibrarian...")
                system_topology = self.librarian.get_system_topology()

                metadata = {
                    "agent_override": agent_override,
                    "routing_hint": routing_hint,
                    "stream_cb": stream_cb,
                    "sensory_context": sensory_context,
                }

                registered_coordinator_agents = (
                    list(self.coordinator.agents.keys()) if hasattr(self.coordinator, "agents") else []
                )
                skill_catalog_preview = self.librarian.get_execution_tool_catalog(as_dict=False)

                logger.info(
                    f"[ENGINE.PRE_PLANNER] Pre-execution audit:\n"
                    f"  - Task ID: {task_id}\n"
                    f"  - System Topology Agents Count: {len(system_topology)}\n"
                    f"  - System Topology Listing: {[t.get('agent_id') for t in system_topology if isinstance(t, dict)]}\n"
                    f"  - Registered Coordinator Roles: {registered_coordinator_agents}\n"
                    f"  - Librarian Skills Catalog Count: {len(skill_catalog_preview)}"
                )

                # 6. Zero-Trust Execution Lifecycle Trigger
                logger.info("[ENGINE.PATHWAY] Triggering Coordinator Zero-Trust Lifecycle...")
                await _safe_execute(
                    self.coordinator.run_task_lifecycle,
                    task_id=task_id,
                    user_input=exec_prompt,
                    system_topology=system_topology,
                    metadata=metadata,
                )
                logger.info("[ENGINE.PATHWAY] Coordinator.run_task_lifecycle completed successfully.")

                # 7. Result Extraction via TaskBlackboard
                logger.debug(f"[ENGINE.PATHWAY] Fetching results from TaskBlackboard for task_id: {task_id}")
                completed_blackboard = TaskBlackboard(STATE_DB_PATH, task_id)
                raw_payload = completed_blackboard._get_results_payload()

                if isinstance(raw_payload, dict) and "result" in raw_payload:
                    result = raw_payload["result"]
                else:
                    result = raw_payload

                logger.info(f"[ENGINE.PATHWAY] Final result resolved from blackboard: {str(result)[:100]}...")

            except Exception as engine_err:
                logger.error(
                    f"[ENGINE.PATHWAY] Catastrophic failure in execution loop: {engine_err}",
                    exc_info=True,
                )
                result = {"error": "System Error", "message": str(engine_err)}

        # 8. Native Output Broadcast
        if result and self.emitter:
            emit_fn = getattr(
                self.emitter, "emit_agent_response", getattr(self.emitter, "emit_response", None)
            )
            if emit_fn:
                try:
                    output_payload = (
                        result.model_dump() if hasattr(result, "model_dump") else result
                    )
                    logger.debug(f"[ENGINE.PATHWAY] Broadcasting result to emitter: {str(output_payload)[:100]}...")
                    res_emit = emit_fn(agent="system", content=output_payload)
                    if inspect.isawaitable(res_emit):
                        await res_emit
                    logger.info("[ENGINE.PATHWAY] Final result broadcast to emitter.")
                except Exception as emit_err:
                    logger.warning(
                        f"[ENGINE.PATHWAY] Failed to broadcast response to emitter: {emit_err}",
                        exc_info=True,
                    )
            else:
                logger.warning("[ENGINE.PATHWAY] Emitter present but no emit_agent_response or emit_response method available.")

        # 9. Concierge Egress Observation (Learning & UX processing)
        if self.concierge and hasattr(self.concierge, "observe_egress"):
            logger.debug(f"[ENGINE.PATHWAY] Invoking Concierge observe_egress [Task ID: {task_id}]...")
            str_result_for_egress = str(result.model_dump() if hasattr(result, "model_dump") else result)
            artifacts_str = (
                str(completed_blackboard._get_results_payload())
                if completed_blackboard
                else ""
            )
            await _safe_execute(
                self.concierge.observe_egress,
                task_id=task_id,
                user_query=raw_prompt,
                execution_result=str_result_for_egress,
                blackboard_artifacts=artifacts_str,
                emitter=self.emitter,
            )

        # 10. Execution Ledger Event
        if self.ledger and task_id:
            logger.debug(f"[ENGINE.PATHWAY] Writing execution ledger event for task_id: {task_id}")
            await self.ledger.log_event(
                task_id=task_id,
                event_type="engine_request_completed",
                data={"result_summary": str(result)[:300]},
            )

        logger.info(f"[ENGINE.PATHWAY] Exit process_request [Task ID: {task_id or 'volatile'}]")
        return result