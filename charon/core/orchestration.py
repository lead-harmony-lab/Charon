"""
charon/core/orchestration.py
System Version: v2.2.0 | File Revision: 2.4.2

Module: Main Orchestration Engine facade for Charon.
Refactored for the Active Execution Envelope paradigm.
Delegates strictly to the Coordinator for execution and the Concierge for UX proposals.
Updated: Direct SkillLibrarian encapsulation for agent hydration and tool discovery with comprehensive diagnostic logging.
"""

import inspect
import logging
from typing import Any, Callable, Dict, Optional, Tuple

from charon.config.paths import STATE_DB_PATH
from charon.telemetry.ledger import ExecutionLedger
from charon.core.skills import SkillLibrarian
from charon.core.state import StateManager
from charon.core.coordinator.engine import Coordinator, _exec_sync_or_async
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
        self.concierge = None

        self._verify_required_system_roles()

        logger.debug(f"[ENGINE] Initializing Coordinator with STATE_DB_PATH='{STATE_DB_PATH}'")
        self.coordinator = Coordinator(db_path=STATE_DB_PATH)

        # Inject the required ingredients into the Coordinator for JIT hydration
        self.coordinator.heavy_model = heavy_model
        self.coordinator.gatekeeper = self.gatekeeper
        if self.llm_client:
            self.coordinator.llm_client = self.llm_client

        logger.info("[ENGINE] OrchestrationEngine initialization complete. Delegating hydration to Coordinator.")

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
        self.concierge = concierge
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
        """Primary execution lifecycle controller."""
        raw_prompt = user_input.strip() if user_input else ""
        if not raw_prompt:
            logger.warning("[ENGINE] Received empty prompt, aborting request execution.")
            return "Error: Empty prompt received."

        logger.info(
            f"[ENGINE.PATHWAY] Enter process_request [Task ID: {task_id or 'volatile'}] "
            f"Override: {agent_override} | Routing Hint: {routing_hint} | Prompt: '{raw_prompt[:60]}...'"
        )

        # 1. Telemetry Broadcast: Typed UI Event Emission
        if self.emitter:
            try:
                emit_event_fn = getattr(
                    self.emitter, "emit_system_event", getattr(self.emitter, "emit_event", None)
                )
                if emit_event_fn:
                    event_payload = {
                        "event_type": "TaskDispatchedEvent",
                        "task_id": task_id,
                        "agent_override": agent_override,
                        "status": "in_progress",
                    }
                    logger.debug(f"[ENGINE.PATHWAY] Emitting TaskDispatchedEvent: {event_payload}")
                    res_emit = emit_event_fn(event_payload)
                    if inspect.isawaitable(res_emit):
                        await res_emit
                    logger.info("[ENGINE.PATHWAY] Initial TaskDispatchedEvent emitted.")
                else:
                    logger.warning("[ENGINE.PATHWAY] Emitter present but no valid emit_event method found.")
            except Exception as ack_err:
                logger.debug(f"[ENGINE] Telemetry dispatch fallback error: {ack_err}", exc_info=True)
        else:
            logger.warning(
                "[ENGINE.PATHWAY] self.emitter is None. Skipping initial telemetry broadcast."
            )

        result: Any = None
        completed_blackboard = None

        try:
            # Fetch topology manifest directly via SkillLibrarian
            logger.debug("[ENGINE.PATHWAY] Fetching system topology from SkillLibrarian...")
            system_topology = self.librarian.get_system_topology()

            metadata = {
                "agent_override": agent_override,
                "routing_hint": routing_hint,
                "stream_cb": stream_cb,
            }

            # --- PRE-PLANNER DIAGNOSTIC LOGGING ---
            registered_coordinator_agents = (
                list(self.coordinator.agents.keys()) if hasattr(self.coordinator, "agents") else []
            )

            # Query execution tool catalog strictly via SkillLibrarian
            skill_catalog_preview = self.librarian.get_execution_tool_catalog(as_dict=False)

            logger.info(
                f"[ENGINE.PRE_PLANNER] Pre-execution audit:\n"
                f"  - Task ID: {task_id}\n"
                f"  - System Topology Agents Count: {len(system_topology)}\n"
                f"  - System Topology Listing: {[t.get('agent_id') for t in system_topology if isinstance(t, dict)]}\n"
                f"  - Registered Coordinator Roles: {registered_coordinator_agents}\n"
                f"  - Librarian Skills Catalog Count: {len(skill_catalog_preview)}"
            )

            # 2. Trigger Zero-Trust Execution Lifecycle
            logger.info("[ENGINE.PATHWAY] Step 2: Triggering Coordinator Zero-Trust Lifecycle...")

            _exec_sync_or_async(
                self.coordinator.run_task_lifecycle,
                task_id=task_id,
                user_input=raw_prompt,
                system_topology=system_topology,
                metadata=metadata,
            )
            logger.info(
                "[ENGINE.PATHWAY] Coordinator.run_task_lifecycle completed successfully."
            )

            # 3. Result Extraction via TaskBlackboard
            logger.debug(f"[ENGINE.PATHWAY] Fetching results from TaskBlackboard for task_id: {task_id}")
            completed_blackboard = TaskBlackboard(STATE_DB_PATH, task_id)
            result = completed_blackboard._get_results_payload()

            logger.info(f"[ENGINE.PATHWAY] Final result resolved from blackboard: {str(result)[:100]}...")

        except Exception as engine_err:
            logger.error(
                f"[ENGINE.PATHWAY] Catastrophic failure in execution loop: {engine_err}",
                exc_info=True,
            )
            result = {"error": "System Error", "message": str(engine_err)}

        # 4. Native Output Broadcast
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

        # 5. Proactive Evaluation
        if self.concierge and self.emitter and result:
            logger.debug("[ENGINE.PATHWAY] Invoking Concierge for next step evaluation...")
            try:
                eval_fn = getattr(
                    self.concierge,
                    "evaluate_next_step",
                    getattr(self.concierge, "get_next_step", None),
                )
                if eval_fn:
                    artifacts = (
                        str(completed_blackboard._get_results_payload())
                        if completed_blackboard
                        else ""
                    )
                    str_result = str(
                        result.model_dump() if hasattr(result, "model_dump") else result
                    )

                    res_coro = eval_fn(
                        user_query=raw_prompt,
                        completed_action="coordinator_loop",
                        execution_result=str_result,
                        blackboard_artifacts=artifacts,
                    )
                    suggestion = (
                        await res_coro if inspect.iscoroutine(res_coro) else res_coro
                    )

                    if suggestion:
                        phrase = getattr(
                            suggestion,
                            "phrase",
                            suggestion.get("phrase", "New Proposal")
                            if isinstance(suggestion, dict)
                            else "New Proposal",
                        )
                        logger.info(
                            f"[ENGINE.PATHWAY] Concierge generated proposal: {phrase}"
                        )

                        emit_payload = (
                            suggestion.model_dump()
                            if hasattr(suggestion, "model_dump")
                            else suggestion
                        )
                        emit_concierge_fn = getattr(
                            self.emitter,
                            "emit_concierge",
                            getattr(self.emitter, "emit_event", None),
                        )
                        if emit_concierge_fn:
                            res_c = emit_concierge_fn(emit_payload)
                            if inspect.isawaitable(res_c):
                                await res_c
                            logger.debug("[ENGINE.PATHWAY] Concierge proposal emitted to UI.")

            except Exception as concierge_err:
                logger.warning(
                    f"[ENGINE.PATHWAY] Concierge evaluation failed gracefully: {concierge_err}",
                    exc_info=True,
                )

        if self.ledger and task_id:
            logger.debug(f"[ENGINE.PATHWAY] Writing execution ledger event for task_id: {task_id}")
            await self.ledger.log_event(
                task_id=task_id,
                event_type="engine_request_completed",
                data={"result_summary": str(result)[:300]},
            )

        logger.info(
            f"[ENGINE.PATHWAY] Exit process_request [Task ID: {task_id or 'volatile'}]"
        )
        return result