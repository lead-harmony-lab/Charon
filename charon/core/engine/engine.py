"""
charon/core/engine/engine.py
System Version: v0.6.3 | File Revision: 4.0.0

Module: Main Orchestration Engine facade for Charon.
Enforces strict agent_registry identifier normalization, CBAC Schema V2 compliance,
active agent validation, quarantine lifecycle handling, and direct Librarian integration.
"""

import inspect
import logging
from typing import Any, Callable, Dict, Optional, Tuple, Union

from charon.core.engine.dag_executor import DAGPlanExecutor
from charon.core.engine.self_healing import SelfHealingHandler
from charon.core.engine.synthesizer import OutputSynthesizer
from charon.core.ledger import ExecutionLedger
from charon.core.session import SessionGateway
from charon.core.skills import SkillLibrarian
from charon.core.state import StateManager, TaskStatus
from charon.exceptions import HandoffException
from charon.intent import RoutingPayload

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
        orchestrator: Optional[SessionGateway] = None,
        heavy_model: str = "llama3.1",
        triage_model: str = "llama3.1",
        state_manager: Optional[StateManager] = None,
        ledger: Optional[ExecutionLedger] = None,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.librarian = librarian or SkillLibrarian.get_instance()

        # Enforce role resolution on startup
        self._verify_required_system_roles()

        self.orchestrator = orchestrator or SessionGateway(
            heavy_model=heavy_model,
            triage_model=triage_model,
        )
        self.state_mgr = state_manager
        self.ledger = ledger
        self.gatekeeper = None
        self.emitter = None
        self.concierge = None

        # Initialize sub-component modules
        self.synthesizer = OutputSynthesizer(self.orchestrator)
        self.self_healing = SelfHealingHandler(self.orchestrator, ledger=self.ledger)
        self.dag_executor = DAGPlanExecutor(
            orchestrator=self.orchestrator,
            self_healing_handler=self.self_healing,
            gatekeeper=self.gatekeeper,
            state_mgr=self.state_mgr,
            ledger=self.ledger,
            emitter=self.emitter,
            librarian=self.librarian,
        )

    def _verify_required_system_roles(self) -> None:
        """
        Verifies that all required system roles can be resolved by SkillLibrarian.
        Halts execution on startup if any minimum system role cannot be resolved.
        """
        if not self.librarian.validate_core_roles():
            logger.warning("[ENGINE] Librarian reported missing or inactive core role mappings.")

        missing_roles = []
        for role in REQUIRED_SYSTEM_ROLES:
            try:
                agent_id = self._get_agent_for_role(role, strict=True)
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

    def _get_agent_for_role(self, role: str, strict: bool = False) -> str:
        """Resolves an agent identifier by system role via SkillLibrarian."""
        try:
            agent_id = self.librarian.resolve_agent_id_for_role(role)
            if agent_id:
                return agent_id
        except Exception as err:
            if strict:
                raise err
            logger.warning(f"Failed to resolve role '{role}': {err}")

        if strict:
            raise RuntimeError(f"Unable to resolve mandatory system role: '{role}'")
        return role

    def _validate_and_resolve_agent(self, agent_input: str) -> str:
        """
        Ensures an agent input (ID or role name) is resolved to an active agent_id
        registered in the database, preventing orphaned foreign keys or execution against quarantined agents.
        """
        if not agent_input:
            return self._get_agent_for_role("system_generalist")

        try:
            # 1. Direct Agent ID check: If agent_input is already an active agent ID, return it immediately
            if self.librarian.is_agent_active(agent_input):
                return agent_input

            # 2. Try role-based resolution via SkillLibrarian
            resolved_id = self.librarian.resolve_agent_id_for_role(agent_input)

            if resolved_id:
                if not self.librarian.is_agent_active(resolved_id):
                    logger.warning(
                        f"[ENGINE] Resolved agent '{resolved_id}' for input '{agent_input}' is inactive or quarantined. "
                        "Falling back to default generalist."
                    )
                    return self._get_agent_for_role("system_generalist")
                return resolved_id
        except Exception as err:
            logger.warning(f"[ENGINE] Failed to resolve agent input '{agent_input}': {err}")

        # 3. Fallback to default system generalist
        logger.warning(f"[ENGINE] Unrecognized or invalid agent override '{agent_input}'. Falling back to default generalist.")
        return self._get_agent_for_role("system_generalist")

    def bind_gateway_context(
        self,
        gatekeeper: Optional[Any] = None,
        emitter: Optional[Any] = None,
        concierge: Optional[Any] = None,
        state_manager: Optional[StateManager] = None,
        ledger: Optional[ExecutionLedger] = None,
    ) -> None:
        """Bind Gateway contexts and propagate them to sub-modules."""
        self.gatekeeper = gatekeeper
        self.emitter = emitter
        self.concierge = concierge
        if state_manager:
            self.state_mgr = state_manager
        if ledger:
            self.ledger = ledger

        # Propagate context to sub-modules
        self.self_healing.ledger = self.ledger
        self.dag_executor.gatekeeper = self.gatekeeper
        self.dag_executor.state_mgr = self.state_mgr
        self.dag_executor.ledger = self.ledger
        self.dag_executor.emitter = self.emitter

    async def process_request(
        self,
        user_input: str,
        stream_cb: Optional[Callable[[str], None]] = None,
        agent_override: Optional[str] = None,
        task_id: Optional[str] = None,
        routing_hint: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Primary execution lifecycle controller."""
        raw_prompt = user_input.strip()
        if not raw_prompt:
            return "Error: Empty prompt received."

        logger.info(f"Engine processing request [{task_id or 'volatile'}]: '{raw_prompt[:60]}...'")

        generalist_agent = self._get_agent_for_role("system_generalist")
        planner_agent = self._get_agent_for_role("system_planner")
        fallback_agent = self._get_agent_for_role("system_fallback")

        result: str = ""
        target_agent: str = generalist_agent
        routing: Optional[RoutingPayload] = None

        try:
            # 1. Direct Agent Override (Sanitized) or Routing Hint Alignment
            if agent_override:
                target_agent = self._validate_and_resolve_agent(agent_override)
                logger.info(f"Bypassing triage router via explicit agent override: {target_agent}")
                result = await self._execute_single_turn(
                    raw_prompt=raw_prompt,
                    agent=target_agent,
                    stream_cb=stream_cb,
                    task_id=task_id,
                )

            elif routing_hint and isinstance(routing_hint, dict):
                hinted_agent = routing_hint.get("agent") or routing_hint.get("target_agent")
                if hinted_agent:
                    target_agent = self._validate_and_resolve_agent(hinted_agent)
                    logger.info(f"Using target agent from proposal routing hint: {target_agent}")
                    result = await self._execute_single_turn(
                        raw_prompt=raw_prompt,
                        agent=target_agent,
                        stream_cb=stream_cb,
                        task_id=task_id,
                    )

            # 2. Standard Triage Routing
            if not result:
                routing = await self.orchestrator.parse_routing(raw_prompt)
                if not routing:
                    logger.warning(
                        f"Routing triage failed. Defaulting to generalist role ({generalist_agent})."
                    )
                    target_agent = generalist_agent
                    needs_decomposition = False
                else:
                    raw_target = getattr(
                        routing, "agent", getattr(routing, "primary_agent", generalist_agent)
                    )
                    target_agent = self._validate_and_resolve_agent(raw_target)
                    needs_decomposition = getattr(routing, "needs_decomposition", False)

                # 3. DAG Decomposition vs Single-Turn Dispatch
                if needs_decomposition or target_agent == planner_agent:
                    result = await self.dag_executor.execute_plan_sequence(
                        raw_prompt=raw_prompt,
                        routing=routing,
                        stream_cb=stream_cb,
                        task_id=task_id,
                        fallback_single_turn_cb=self._execute_single_turn,
                    )
                else:
                    result = await self._execute_single_turn(
                        raw_prompt=raw_prompt,
                        agent=target_agent,
                        stream_cb=stream_cb,
                        task_id=task_id,
                    )

        except HandoffException as handoff_err:
            logger.warning(
                f"[Charon.Engine] HandoffException caught: '{handoff_err}'. "
                f"Upgrading task execution to target agent loop."
            )
            raw_handoff_target = getattr(handoff_err, "target_agent", fallback_agent)
            target_agent = self._validate_and_resolve_agent(raw_handoff_target)

            # Delegate to Coordinator / Blackboard Loop if available
            dispatcher = getattr(self.orchestrator, "dispatcher", None)
            dispatch_fn = getattr(dispatcher, "dispatch_blackboard_loop", None) if dispatcher else None

            if dispatch_fn and callable(dispatch_fn):
                result = await dispatch_fn(
                    user_raw_input=raw_prompt,
                    initial_agent=target_agent,
                    max_iterations=5,
                )
            elif target_agent == planner_agent:
                result = await self.dag_executor.execute_plan_sequence(
                    raw_prompt=raw_prompt,
                    routing=routing,
                    stream_cb=stream_cb,
                    task_id=task_id,
                    fallback_single_turn_cb=self._execute_single_turn,
                )
            else:
                logger.info(f"[Charon.Engine] Re-dispatching handoff task directly to {target_agent}")
                result = await self._execute_single_turn(
                    raw_prompt=raw_prompt,
                    agent=target_agent,
                    stream_cb=stream_cb,
                    task_id=task_id,
                )

        # 4. Output Synthesis
        if result and not result.startswith(("[Awaiting Authorization]", "[Authorization Denied]", "[System Error]")):
            if target_agent not in (generalist_agent, planner_agent):
                result = await self.synthesizer.synthesize(
                    user_query=raw_prompt,
                    agent=target_agent,
                    raw_output=result,
                    stream_cb=stream_cb,
                )

            if self.emitter:
                emit_fn = getattr(self.emitter, "emit_agent_response", getattr(self.emitter, "emit_response", None))
                if emit_fn:
                    try:
                        res_emit = emit_fn(agent=target_agent, content=result)
                        if inspect.isawaitable(res_emit):
                            await res_emit
                    except Exception as emit_err:
                        logger.warning(f"Failed to broadcast synthesized response to emitter: {emit_err}")

        # 5. Engine-Level Concierge Proactive Evaluation
        if (
            self.concierge
            and self.emitter
            and result
            and not result.startswith(("[Awaiting Authorization]", "[Authorization Denied]", "[System Error]"))
        ):
            try:
                action_name = getattr(routing, "action", None) or "general_response"

                eval_fn = getattr(
                    self.concierge,
                    "evaluate_next_step",
                    getattr(self.concierge, "get_next_step", None),
                )

                if eval_fn:
                    res_coro = eval_fn(
                        user_query=raw_prompt,
                        completed_action=str(action_name),
                        execution_result=result,
                        params={"user_input": raw_prompt},
                    )
                    suggestion = await res_coro if inspect.iscoroutine(res_coro) else res_coro

                    if suggestion:
                        logger.info(
                            f"Engine Concierge generated proactive proposal: {suggestion.get('phrase', suggestion.get('title', ''))}"
                        )
                        await self.emitter.emit_concierge(suggestion)
            except Exception as concierge_err:
                logger.warning(f"Engine-level Concierge evaluation failed gracefully: {concierge_err}")

        return result

    async def _execute_single_turn(
        self,
        raw_prompt: str,
        agent: str,
        stream_cb: Optional[Callable[[str], None]] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """Executes a single-turn agent interaction."""
        resolved_agent = self._validate_and_resolve_agent(agent)
        extraction = await self.orchestrator.parse_extraction(raw_prompt, resolved_agent)

        if stream_cb:
            ack_msg = ""
            action_str = getattr(extraction, "action", "")
            params = getattr(extraction, "parameters", {})

            ack_fn = getattr(self.concierge, "generate_acknowledgment", None)
            if ack_fn:
                try:
                    res_ack = ack_fn(
                        agent=resolved_agent,
                        action=action_str,
                        parameters=params,
                    )
                    ack_msg = await res_ack if inspect.isawaitable(res_ack) else res_ack
                except Exception as ack_err:
                    logger.debug(f"[ENGINE] Concierge acknowledgment generation fallback: {ack_err}")

            if not ack_msg:
                orch_ack_fn = getattr(self.orchestrator, "get_acknowledgment", None)
                if orch_ack_fn:
                    ack_msg = orch_ack_fn(resolved_agent, action=action_str, parameters=params)

            if ack_msg:
                stream_cb(f"{ack_msg}\n\n")

        if self.gatekeeper and self.gatekeeper.requires_approval(extraction):
            logger.info(f"Gatekeeper intercepted high-risk task for agent '{resolved_agent}'. Awaiting user approval.")

            manifest, action, approval_id = self.gatekeeper.intercept_task(resolved_agent, extraction, raw_prompt)

            if self.ledger and task_id:
                await self.ledger.log_event(
                    task_id=task_id,
                    event_type="single_turn_intercepted",
                    data={"agent": resolved_agent, "action": action, "approval_id": approval_id},
                )
            if self.state_mgr and task_id:
                await self.state_mgr.update_status(
                    task_id=task_id,
                    status=TaskStatus.AWAITING_APPROVAL,
                    approval_id=approval_id,
                )

            if self.emitter:
                await self.emitter.emit_gatekeeper(manifest, action)

            if stream_cb:
                stream_cb(f"\n{manifest}\n\n[Awaiting authorization token: {approval_id}...]\n")

            decision = await self.gatekeeper.wait_for_decision(approval_id, timeout=300.0)

            if decision not in ("APPROVED", "PROCEED"):
                logger.warning(f"Gatekeeper intercept {approval_id} rejected or expired ({decision}). Aborting.")
                if self.ledger and task_id:
                    await self.ledger.log_event(
                        task_id=task_id,
                        event_type="single_turn_rejected",
                        data={"approval_id": approval_id, "decision": decision},
                    )
                return f"[Authorization Denied]: Intercept {approval_id} for action '{action}' was {decision.lower()}."

            logger.info(f"Gatekeeper intercept {approval_id} approved. Resuming execution.")
            if self.ledger and task_id:
                await self.ledger.log_event(
                    task_id=task_id,
                    event_type="single_turn_approved",
                    data={"approval_id": approval_id},
                )
            if self.state_mgr and task_id:
                await self.state_mgr.update_status(task_id=task_id, status=TaskStatus.RUNNING)

            if hasattr(extraction, "confirmed"):
                setattr(extraction, "confirmed", True)

        result = await self.orchestrator.execute_agent_task(
            agent=resolved_agent,
            extraction=extraction,
            user_raw_input=raw_prompt,
            stream_cb=stream_cb,
        )

        if self.ledger and task_id:
            await self.ledger.log_event(
                task_id=task_id,
                event_type="single_turn_completed",
                data={"agent": resolved_agent, "result_summary": str(result)[:300]},
            )

        self.orchestrator.record_turn(raw_prompt, result)
        return result