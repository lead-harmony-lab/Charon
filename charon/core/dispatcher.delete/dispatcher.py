"""
charon/core/dispatcher/dispatcher.py
System Version: v0.7.0 | File Revision: 8.0.0

Module: Core AgentDispatcher implementation.
Handles specialist agent execution, dynamic skill negotiation, telemetry event routing,
and stateful TaskBlackboard reflection loops. Standardized on action_name routing,
dynamic agent resolution via SkillLibrarian, and guaranteed output telemetry emission.
Hardened against None return values from missing role defaults and prompt lookups.
"""

import inspect
import logging
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

from pydantic import BaseModel

from charon.agents.base import CapabilityType
from charon.config.paths import STATE_DB_PATH
from charon.core.coordinator import Coordinator
from charon.core.coordinator.blackboard import (
    EscalationLevel,
    TaskBlackboard,
    TaskStatus,
    UnfulfilledRequirement,
)
from charon.core.dispatcher.artifacts import extract_artifacts_from_result
from charon.core.dispatcher.router import AgentRouter
from charon.core.dispatcher.telemetry import emit_telemetry, get_trace_event_type
from charon.core.skills.librarian import SkillLibrarian
from charon.db.repositories.gap import SkillGapRepository
from charon.intent import DynamicActionPayload, get_agent_manifest
from charon.telemetry.trace import TraceEvent

logger = logging.getLogger("Charon.Dispatcher")

CORE_TRIANGLE_ROLES: Tuple[str, ...] = (
    "system_generalist",
    "system_engineer",
    "system_fallback",
)


def _is_blackboard_satisfied(coordinator: Coordinator, blackboard: TaskBlackboard) -> bool:
    """Evaluates whether all blackboard requirements are satisfied."""
    if blackboard.status == TaskStatus.COMPLETED:
        return True

    if hasattr(coordinator, "evaluate_satisfaction"):
        return coordinator.evaluate_satisfaction(blackboard)

    if not blackboard.execution_history:
        return False

    return len(blackboard.unfulfilled_requirements) == 0


class AgentDispatcher:
    """Handles dispatching payloads to specialist agents via a unified TaskBlackboard loop and AgentRouter."""

    def __init__(
        self,
        db_path: Optional[Union[Path, str]] = None,
        heavy_model: str = "",
        agent_telemetry_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        router: Optional[AgentRouter] = None,
    ):
        target_path = Path(db_path) if db_path else STATE_DB_PATH
        if target_path.is_dir():
            logger.warning(
                f"[DISPATCHER] Target DB path '{target_path}' is a directory. "
                f"Defaulting to STATE_DB_PATH '{STATE_DB_PATH}'."
            )
            target_path = STATE_DB_PATH

        self.db_path = target_path
        self.heavy_model = heavy_model
        self.coordinator = Coordinator()
        self.agent_telemetry_callback = agent_telemetry_callback

        # Injectable router; falls back to default instantiation
        self.router = router if router is not None else AgentRouter(db_path=self.db_path)

        # Enforce Core System Boot Guardrail
        self._verify_core_triangle()

    def set_telemetry_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Dynamically binds or updates the active agent telemetry callback."""
        self.agent_telemetry_callback = callback

    def _verify_core_triangle(self) -> None:
        """Validates required core system roles are mapped in SkillLibrarian."""
        librarian = SkillLibrarian.get_instance(self.db_path)

        if not librarian.validate_core_roles():
            logger.warning("[DISPATCHER] Librarian reported incomplete core role mappings.")

        missing_roles = [
            role for role in CORE_TRIANGLE_ROLES
            if not librarian.resolve_agent_id_for_role(role)
        ]

        if missing_roles:
            raise RuntimeError(
                f"[FATAL BOOT FAULT] Core Triangle Violation: Missing active agent mapped "
                f"to required system role(s): {missing_roles}. Engine cannot safely boot."
            )

    def _resolve_agent(self, agent_id: str) -> Any:
        """Delegates agent resolution to AgentRouter and binds telemetry callbacks."""
        if not agent_id:
            raise ValueError("[DISPATCHER] Agent resolution failed: agent_id was empty or None.")

        agent_instance = self.router.get_agent_instance(
            agent_id=agent_id,
            heavy_model=self.heavy_model,
        )

        if agent_instance is None:
            raise RuntimeError(f"AgentRouter failed to resolve agent target: '{agent_id}'")

        if self.agent_telemetry_callback and hasattr(agent_instance, "bind_telemetry"):
            agent_instance.bind_telemetry(self.agent_telemetry_callback)

        return agent_instance

    def _log_skill_gap_to_db(self, action: str, agent_id: str, missing_prereqs: list) -> None:
        """Records identified skill gaps into state store."""
        if not self.db_path.exists() or self.db_path.is_dir():
            return

        librarian = SkillLibrarian.get_instance(self.db_path)
        resolved_agent_id = librarian.resolve_agent_id_for_role(agent_id) or agent_id
        display_name = librarian.get_display_name_for_agent(resolved_agent_id)

        try:
            repo = SkillGapRepository(db_path=str(self.db_path))
            repo.log_skill_gap(
                action_name=action,
                agent_name=resolved_agent_id,
                missing_prereqs=missing_prereqs,
            )
            logger.warning(
                f"[COORDINATOR] Skill gap logged for '{action}' (Agent: {display_name}, Missing: {missing_prereqs})"
            )
        except Exception as e:
            logger.error(f"[COORDINATOR] Failed to log skill gap for '{display_name}': {e}")

    async def execute_step(
        self,
        agent_id: str,
        action: str,
        parameters: Dict[str, Any],
        user_raw_input: str,
        stream_cb: Any = None,
    ) -> Any:
        """Executes a single discrete step on a specialist agent and returns execution result."""
        if not action:
            raise ValueError("[DISPATCHER] Invalid execution step: 'action' parameter cannot be empty.")

        agent_instance = self._resolve_agent(agent_id)
        librarian = SkillLibrarian.get_instance(self.db_path)
        display_name = librarian.get_display_name_for_agent(agent_id)

        # 1. Dynamic Skill, Lifecycle Status & Schema Validation
        action_details = librarian.get_action_details(action)
        if action_details and isinstance(action_details, dict):
            status = action_details.get("status", "ACTIVE").upper()
            if status in ("QUARANTINED", "DISABLED", "ARCHIVED"):
                reason = action_details.get("quarantine_reason", "Skill is not active.")
                self._log_skill_gap_to_db(action, agent_id, [f"Status: {status} - {reason}"])
                raise PermissionError(
                    f"Execution blocked: Skill '{action}' is currently {status}. Reason: {reason}"
                )

            expected_params = action_details.get("parameters", {})
            if expected_params and isinstance(expected_params, dict):
                sanitized_params = {k: v for k, v in parameters.items() if k in expected_params}
            else:
                sanitized_params = parameters

            payload = DynamicActionPayload(call_action=action, params=sanitized_params)
            try:
                payload.validate_against_manifest()
            except ValueError as ve:
                self._log_skill_gap_to_db(action, agent_id, [str(ve)])
                raise RuntimeError(f"Parameter validation failed for '{action}': {ve}")

        # 2. Capability Evaluation
        exec_route = "NATIVE"
        if hasattr(agent_instance, "evaluate_capability"):
            contract = agent_instance.evaluate_capability(action, parameters)
            contract_status = getattr(contract, "status", None)

            if contract_status == "UNSUPPORTED_ACTION":
                self._log_skill_gap_to_db(action, agent_id, [])
                raise ValueError(f"Action '{action}' is unsupported by {display_name}.")

            if contract_status == "CAPABILITY_GAP":
                missing = getattr(contract, "missing_prerequisites", [])
                self._log_skill_gap_to_db(action, agent_id, missing)
                raise RuntimeError(
                    f"Agent {display_name} lacks prerequisites for '{action}': {missing}"
                )

            if getattr(contract, "capability_type", None) == CapabilityType.DYNAMIC_SKILL:
                exec_route = "DYNAMIC"

        # 3. Execution Routing
        if exec_route == "DYNAMIC" and hasattr(agent_instance, "execute_dynamic"):
            exec_method = agent_instance.execute_dynamic
        else:
            exec_method = getattr(agent_instance, "execute", None)

        if not callable(exec_method):
            raise NotImplementedError(
                f"Agent '{display_name}' lacks a callable 'execute' method for action '{action}'."
            )

        sig = inspect.signature(exec_method)
        exec_kwargs: Dict[str, Any] = {}

        if stream_cb is not None and (
            "stream_callback" in sig.parameters
            or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        ):
            exec_kwargs["stream_callback"] = stream_cb

        if "raw_prompt" in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        ):
            exec_kwargs["raw_prompt"] = user_raw_input

        res = exec_method(action=action, parameters=parameters, **exec_kwargs)
        if inspect.isawaitable(res):
            res = await res

        return res

    async def dispatch_blackboard_loop(
        self,
        user_raw_input: Optional[str] = None,
        blackboard: Optional[TaskBlackboard] = None,
        initial_agent_id: Optional[str] = None,
        initial_extraction: Optional[BaseModel] = None,
        stream_cb: Any = None,
        max_iterations: int = 5,
        **kwargs: Any,
    ) -> str:
        """Executes the stateful Reflection Engine loop utilizing AgentRouter for targets."""
        raw_prompt = user_raw_input or kwargs.get("raw_prompt") or kwargs.get("prompt") or ""
        cb = stream_cb or kwargs.get("stream_callback")

        librarian = SkillLibrarian.get_instance(self.db_path)
        default_generalist_action = (
            librarian.get_default_action_for_role("system_generalist") or "general_query"
        )

        init_agent_id = (
            initial_agent_id
            or kwargs.get("target_agent")
            or kwargs.get("starting_agent")
            or self.router.get_system_fallback()
        )

        if blackboard is None:
            task_id = kwargs.get("task_id")
            metadata = kwargs.get("metadata", {})
            blackboard = self.coordinator.initialize_blackboard(
                prompt=raw_prompt,
                task_id=task_id,
                metadata=metadata,
            )
            logger.info("Initialized TaskBlackboard [%s] for prompt: '%s'", blackboard.task_id, raw_prompt)

        if initial_extraction:
            hint_data = initial_extraction.model_dump(
                exclude={"requires_approval", "memory_candidate"}, exclude_none=True
            )
            for k, v in hint_data.items():
                if k != "action" and v is not None:
                    blackboard.artifacts[k] = v

        initial_action_hint = getattr(initial_extraction, "action", None) if initial_extraction else None
        init_agent_display = librarian.get_display_name_for_agent(init_agent_id) if init_agent_id else "Unknown"

        await emit_telemetry(
            TraceEvent(
                agent_name="Coordinator",
                event_type=get_trace_event_type("INITIALIZATION"),
                action="Initialize Reflection Loop",
                details={
                    "task_id": blackboard.task_id,
                    "prompt": raw_prompt,
                    "triage_hint_agent": init_agent_display,
                    "triage_hint_action": initial_action_hint,
                },
            )
        )

        max_iter = kwargs.get("max_turns", max_iterations)
        iteration = 0
        final_summaries = []
        full_results = []

        while iteration < max_iter:
            iteration += 1

            if _is_blackboard_satisfied(self.coordinator, blackboard):
                logger.info("TaskBlackboard [%s] fully satisfied in %d iterations.", blackboard.task_id, iteration)
                break

            step_selection = self.coordinator.select_next_execution_step(blackboard)

            if not step_selection and iteration == 1 and init_agent_id:
                manifest = get_agent_manifest(init_agent_id)
                action_hint = (
                    initial_action_hint
                    or (manifest.default_action if manifest else None)
                    or default_generalist_action
                )
                action_details = librarian.get_action_details(action_hint) or {
                    "action_name": action_hint,
                    "agent": init_agent_id,
                }

                hint_params = initial_extraction.model_dump(exclude_none=True) if initial_extraction else {}
                if blackboard.unfulfilled_requirements:
                    req = blackboard.unfulfilled_requirements[0]
                else:
                    req = UnfulfilledRequirement(
                        capability_required=action_hint,
                        parameters=hint_params,
                    )
                    blackboard.unfulfilled_requirements.append(req)
                step_selection = (req, action_details, hint_params)

            if not step_selection:
                if blackboard.status == TaskStatus.FAILED:
                    failure_msg = "❌ Task Execution Failed: Unresolvable requirement during escalation."
                    if hasattr(blackboard, "result"):
                        blackboard.result = failure_msg
                    return failure_msg
                break

            req, capability_info, step_params = step_selection
            bound_params = {**blackboard.artifacts, **step_params}

            if isinstance(capability_info, dict):
                action = (
                    capability_info.get("action_name")
                    or getattr(req, "capability_required", None)
                    or default_generalist_action
                )
                requested_agent = (
                    capability_info.get("agent")
                    or capability_info.get("assigned_agent")
                    or getattr(req, "assigned_agent_override", None)
                    or init_agent_id
                    or self.router.get_system_fallback()
                )
            else:
                requested_agent = getattr(capability_info, "agent", init_agent_id)
                action = (
                    getattr(capability_info, "capability_name", None)
                    or getattr(capability_info, "action", None)
                    or getattr(req, "capability_required", None)
                    or default_generalist_action
                )

            target_role, fallback_role = self.router.resolve_route(
                action_name=action,
                default_agent=requested_agent,
            )

            target_agent_id = librarian.resolve_agent_id_for_role(target_role) or target_role
            fallback_agent_id = librarian.resolve_agent_id_for_role(fallback_role) if fallback_role else None

            target_display = librarian.get_display_name_for_agent(target_agent_id)
            fallback_display = librarian.get_display_name_for_agent(fallback_agent_id) if fallback_agent_id else "None"

            esc_lvl = getattr(req, "escalation_level", EscalationLevel.L1_SPECIALIST)
            esc_val = esc_lvl.value if hasattr(esc_lvl, "value") else int(esc_lvl)

            logger.info(
                "Loop Iteration %d: Dispatching to %s (Fallback: %s) [%s] [Escalation Level %d]",
                iteration,
                target_display,
                fallback_display,
                action,
                esc_val,
            )

            await emit_telemetry(
                TraceEvent(
                    agent_name=target_display,
                    event_type=get_trace_event_type("NEGOTIATION"),
                    action=action,
                    details={"escalation_level": esc_val, "params": bound_params},
                )
            )

            start_t = time.time()
            exec_success = False
            exec_agent_display = target_display
            res = None
            primary_err = None

            try:
                res = await self.execute_step(
                    agent_id=target_agent_id,
                    action=action,
                    parameters=bound_params,
                    user_raw_input=raw_prompt,
                    stream_cb=cb,
                )
                exec_success = True
            except Exception as exec_err:
                primary_err = exec_err
                dur_ms = (time.time() - start_t) * 1000.0
                tb_str = traceback.format_exc()
                logger.error("Step execution failed on agent %s (%s): %s", target_display, action, exec_err)

                if fallback_agent_id and fallback_agent_id != target_agent_id:
                    logger.info("Attempting execution via router fallback: %s", fallback_display)
                    try:
                        res = await self.execute_step(
                            agent_id=fallback_agent_id,
                            action=action,
                            parameters=bound_params,
                            user_raw_input=raw_prompt,
                            stream_cb=cb,
                        )
                        exec_agent_display = f"{fallback_display} (Fallback)"
                        exec_success = True
                    except Exception as fallback_err:
                        logger.error("Fallback execution on %s failed: %s", fallback_display, fallback_err)
                        combined_err = (
                            f"Primary ({target_display}): {primary_err} | Fallback ({fallback_display}): {fallback_err}"
                        )
                        fallback_tb = traceback.format_exc()
                        tb_str = f"--- PRIMARY TRACEBACK ---\n{tb_str}\n--- FALLBACK TRACEBACK ---\n{fallback_tb}"

                        if hasattr(self.coordinator, "escalate_requirement"):
                            self.coordinator.escalate_requirement(
                                blackboard=blackboard,
                                requirement=req,
                                failure_reason=combined_err,
                            )

                        if hasattr(self.coordinator, "handle_step_completion"):
                            self.coordinator.handle_step_completion(
                                blackboard=blackboard,
                                requirement=req,
                                capability=capability_info,
                                success=False,
                                output_summary="Execution fault occurred.",
                                produced_artifacts={},
                                error_message=f"{combined_err}\nTraceback:\n{tb_str}",
                            )

                        blackboard.record_step(
                            role=target_display,
                            action=action,
                            status="FAILED",
                            output_summary=f"Execution error: {combined_err}",
                            error_message=tb_str,
                        )

                        to_lvl = (
                            blackboard.current_escalation_level.value
                            if hasattr(blackboard.current_escalation_level, "value")
                            else str(blackboard.current_escalation_level)
                        )
                        await emit_telemetry(
                            TraceEvent(
                                agent_name="Coordinator",
                                event_type=get_trace_event_type("ESCALATION"),
                                action=action,
                                duration_ms=dur_ms,
                                details={"reason": combined_err, "to_level": to_lvl},
                            )
                        )

            if exec_success:
                dur_ms = (time.time() - start_t) * 1000.0
                cap_dict = capability_info if isinstance(capability_info, dict) else {}
                produced_artifacts = extract_artifacts_from_result(
                    action=action, result=res, parameters=bound_params, capability_info=cap_dict
                )

                if isinstance(res, dict):
                    if res.get("status") in ("failure", "error"):
                        err_msg = res.get("last_error") or res.get("message") or "Skill reported execution failure."
                        raise RuntimeError(err_msg)

                    str_res = str(res.get("output") or res.get("result") or res)
                else:
                    str_res = str(res) if res is not None else ""

                full_results.append(str_res)

                # Broadcast fallback agent_response if telemetry callback is present
                if self.agent_telemetry_callback and str_res:
                    try:
                        self.agent_telemetry_callback({
                            "type": "agent_response",
                            "agent_name": exec_agent_display,
                            "data": {"content": str_res},
                        })
                    except Exception as tel_err:
                        logger.warning("Failed to emit agent_response telemetry: %s", tel_err)

                # Direct stream callback dispatch
                if cb and str_res:
                    try:
                        if inspect.iscoroutinefunction(cb):
                            await cb(str_res)
                        else:
                            cb(str_res)
                    except Exception as cb_err:
                        logger.warning("Failed to invoke stream_cb with final result: %s", cb_err)

                summary_text = str_res[:300] + ("..." if len(str_res) > 300 else "")
                final_summaries.append(f"**[{exec_agent_display} -> {action}]**: {summary_text}")

                if hasattr(self.coordinator, "handle_step_completion"):
                    self.coordinator.handle_step_completion(
                        blackboard=blackboard,
                        requirement=req,
                        capability=capability_info,
                        success=True,
                        output_summary=str_res,
                        produced_artifacts=produced_artifacts,
                    )

                if req and hasattr(req, "requirement_id"):
                    blackboard.pop_requirement(req.requirement_id)

                blackboard.record_step(
                    role=exec_agent_display,
                    action=action,
                    status="SUCCESS",
                    output_summary=str_res,
                    produced_artifacts=produced_artifacts,
                )

                if not blackboard.unfulfilled_requirements:
                    blackboard.mark_completed()

                await emit_telemetry(
                    TraceEvent(
                        agent_name=exec_agent_display,
                        event_type=get_trace_event_type("EXECUTION"),
                        action=action,
                        duration_ms=dur_ms,
                        details={"summary": summary_text, "produced_artifacts": list(produced_artifacts.keys())},
                    )
                )

        # Build final return text and attach to TaskBlackboard state
        if blackboard.status == TaskStatus.COMPLETED or _is_blackboard_satisfied(self.coordinator, blackboard):
            if len(full_results) == 1:
                final_out = full_results[0]
            elif full_results:
                final_out = "\n\n".join(full_results)
            else:
                final_out = "### ✅ Task Executed Successfully\n\n" + "\n\n".join(final_summaries)
        else:
            final_out = (
                f"⚠️ **Task Incomplete** (Status: {blackboard.status.value})\n\n"
                + "\n\n".join(full_results if full_results else final_summaries)
            )

        if hasattr(blackboard, "result"):
            blackboard.result = final_out

        return final_out

    async def dispatch(
        self,
        agent_id: str,
        extraction: Optional[BaseModel],
        user_raw_input: str,
        stream_cb: Any = None,
        **kwargs: Any,
    ) -> str:
        """Unified entry point."""
        return await self.dispatch_blackboard_loop(
            user_raw_input=user_raw_input,
            initial_agent_id=agent_id,
            initial_extraction=extraction,
            stream_cb=stream_cb,
            **kwargs,
        )