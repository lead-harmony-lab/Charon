"""
charon/core/engine.py
System Version: v2.1.1

Module: Main Orchestration Engine facade for Charon.
Refactored for the Active Execution Envelope paradigm.
Delegates strictly to the Coordinator for execution and the Concierge for UX proposals.
Micromanagement, legacy extraction, string synthesis, and Gatekeeper loops have been removed.
"""

import inspect
import logging
from typing import Any, Callable, Dict, Optional, Tuple

from charon.telemetry.ledger import ExecutionLedger
from charon.core.skills import SkillLibrarian
from charon.core.state import StateManager
from charon.core.coordinator.engine import Coordinator, _exec_sync_or_async

logger = logging.getLogger("Charon.Engine")

# Mandatory minimum system roles required for core operation
REQUIRED_SYSTEM_ROLES: Tuple[str, ...] = (
    "system_generalist",
    "system_engineer",
    "system_planner",
    "system_fallback",
)


class OrchestrationEngine:
    """High-level Orchestration Engine facade for Charon."""

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        heavy_model: str = "llama3.1",
        triage_model: str = "llama3.1",
        state_manager: Optional[StateManager] = None,
        ledger: Optional[ExecutionLedger] = None,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.llm_client = llm_client
        self.librarian = librarian or SkillLibrarian.get_instance()

        # Enforce role resolution on startup
        self._verify_required_system_roles()

        self.state_mgr = state_manager
        self.ledger = ledger
        self.emitter = None
        self.concierge = None

        # The Brain: Instantiate the Coordinator directly
        self.coordinator = Coordinator()

    def _verify_required_system_roles(self) -> None:
        """Verifies that all required system roles can be resolved by SkillLibrarian."""
        if not self.librarian.validate_core_roles():
            logger.warning("[ENGINE] Librarian reported missing or inactive core role mappings.")

        missing_roles = []
        for role in REQUIRED_SYSTEM_ROLES:
            try:
                agent_id = self.librarian.resolve_agent_id_for_role(role)
                if not agent_id:
                    missing_roles.append(role)
            except Exception as err:
                logger.critical(f"Failed to resolve mandatory system role '{role}': {err}")
                missing_roles.append(role)

        if missing_roles:
            fatal_msg = (
                f"CRITICAL STARTUP FAILURE: SkillLibrarian could not resolve required system roles: "
                f"{missing_roles}. System halting."
            )
            logger.critical(fatal_msg)
            raise RuntimeError(fatal_msg)

    def bind_gateway_context(
        self,
        emitter: Optional[Any] = None,
        concierge: Optional[Any] = None,
        state_manager: Optional[StateManager] = None,
        ledger: Optional[ExecutionLedger] = None,
    ) -> None:
        """Bind Gateway contexts. Gatekeeper is deliberately excluded (handled natively by Work Contracts)."""
        self.emitter = emitter
        self.concierge = concierge
        if state_manager:
            self.state_mgr = state_manager
        if ledger:
            self.ledger = ledger

    async def shutdown(self) -> None:
        """Gracefully shuts down engine components during daemon teardown."""
        logger.info("[ENGINE] Initiating engine teardown sequence...")
        # (Coordinator teardown logic can be added here if needed in the future)

    async def process_request(
        self,
        user_input: str,
        stream_cb: Optional[Callable[[str], None]] = None,
        agent_override: Optional[str] = None,
        task_id: Optional[str] = None,
        routing_hint: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Primary execution lifecycle controller."""
        raw_prompt = user_input.strip()
        if not raw_prompt:
            return "Error: Empty prompt received."

        logger.info(f"Engine processing request [{task_id or 'volatile'}]: '{raw_prompt[:60]}...'")

        # 1. Telemetry Broadcast: Typed UI Event Emission
        if self.emitter:
            try:
                emit_event_fn = getattr(self.emitter, "emit_system_event", getattr(self.emitter, "emit_event", None))
                if emit_event_fn:
                    event_payload = {
                        "event_type": "TaskDispatchedEvent",
                        "task_id": task_id,
                        "agent_override": agent_override,
                        "status": "in_progress",
                    }
                    res_emit = emit_event_fn(event_payload)
                    if inspect.isawaitable(res_emit):
                        await res_emit
            except Exception as ack_err:
                logger.debug(f"[ENGINE] Telemetry dispatch fallback: {ack_err}")

        result: Any = None
        completed_blackboard = None

        try:
            # 2. The Brain (Coordinator): Initialize State & Decompose
            metadata = {"agent_override": agent_override, "routing_hint": routing_hint}
            blackboard = await _exec_sync_or_async(
                self.coordinator.initialize_blackboard,
                prompt=raw_prompt,
                task_id=task_id,
                metadata=metadata,
            )

            # 3. The Brain (Coordinator): Execute Workflow (Work Contracts & Escalation)
            completed_blackboard = await _exec_sync_or_async(
                self.coordinator.run_turn,
                blackboard=blackboard,
            )

            # 4. State Resolution: Expecting a Pydantic Artifact
            result = completed_blackboard.get_final_result()

        except Exception as engine_err:
            logger.error(f"[ENGINE] Catastrophic failure in execution loop: {engine_err}", exc_info=True)
            result = {"error": "System Error", "message": str(engine_err)}

        # 5. Native Output Broadcast
        if result and self.emitter:
            emit_fn = getattr(self.emitter, "emit_agent_response", getattr(self.emitter, "emit_response", None))
            if emit_fn:
                try:
                    output_payload = result.model_dump() if hasattr(result, "model_dump") else result
                    res_emit = emit_fn(agent="system", content=output_payload)
                    if inspect.isawaitable(res_emit):
                        await res_emit
                except Exception as emit_err:
                    logger.warning(f"Failed to broadcast structured response to emitter: {emit_err}")

        # 6. The Mouth (Concierge): Proactive Evaluation
        if self.concierge and self.emitter and result:
            try:
                eval_fn = getattr(
                    self.concierge,
                    "evaluate_next_step",
                    getattr(self.concierge, "get_next_step", None),
                )
                if eval_fn:
                    artifacts = str(completed_blackboard) if completed_blackboard else ""
                    str_result = str(result.model_dump() if hasattr(result, "model_dump") else result)

                    res_coro = eval_fn(
                        user_query=raw_prompt,
                        completed_action="coordinator_loop",
                        execution_result=str_result,
                        blackboard_artifacts=artifacts,
                    )
                    suggestion = await res_coro if inspect.iscoroutine(res_coro) else res_coro

                    if suggestion:
                        phrase = getattr(
                            suggestion,
                            "phrase",
                            suggestion.get("phrase", "New Proposal") if isinstance(suggestion, dict) else "New Proposal",
                        )
                        logger.info(f"Engine Concierge generated proactive proposal: {phrase}")

                        emit_payload = suggestion.model_dump() if hasattr(suggestion, "model_dump") else suggestion
                        emit_concierge_fn = getattr(self.emitter, "emit_concierge", getattr(self.emitter, "emit_event", None))
                        if emit_concierge_fn:
                            res_c = emit_concierge_fn(emit_payload)
                            if inspect.isawaitable(res_c):
                                await res_c

            except Exception as concierge_err:
                logger.warning(f"Engine-level Concierge evaluation failed gracefully: {concierge_err}", exc_info=True)

        if self.ledger and task_id:
            await self.ledger.log_event(
                task_id=task_id,
                event_type="engine_request_completed",
                data={"result_summary": str(result)[:300]},
            )

        return result