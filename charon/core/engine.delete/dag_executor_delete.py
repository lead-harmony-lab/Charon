"""
charon/core/engine/dag_executor.py
System Version: v0.6.3 | File Revision: 4.0.0

Module: Asynchronous DAG execution and context substitution engine.
Enforces strict fail-fast contracts on system_roles, prevents deadlock
hazards via guaranteed future resolution, and prevents dependency cascades.
"""

import asyncio
import inspect
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Union

from charon.core.orchestration.self_healing import SelfHealingHandler
from charon.core.ledger import ExecutionLedger
from charon.core.session import SessionGateway
from charon.core.skills.librarian import SkillLibrarian
from charon.core.state import StateManager, TaskStatus
from charon.intent.routing import RoutingPayload

logger = logging.getLogger("Charon.Engine.DAGExecutor")


class DAGPlanExecutor:
    """Decomposes multi-step tasks into DAG sequences and executes them with parallel resolution."""

    def __init__(
        self,
        orchestrator: SessionGateway,
        self_healing_handler: SelfHealingHandler,
        gatekeeper: Optional[Any] = None,
        state_mgr: Optional[StateManager] = None,
        ledger: Optional[ExecutionLedger] = None,
        emitter: Optional[Any] = None,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.orchestrator = orchestrator
        self.self_healing = self_healing_handler
        self.gatekeeper = gatekeeper
        self.state_mgr = state_mgr
        self.ledger = ledger
        self.emitter = emitter
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _normalize_step_id(self, step_val: Any) -> Union[int, str]:
        """Ensures step IDs and dependency keys are normalized for dictionary lookup."""
        try:
            return int(step_val)
        except (ValueError, TypeError):
            return str(step_val).strip()

    def _step_sort_key(self, step_id: Any) -> tuple:
        """Orders numeric steps numerically first, followed by string identifiers lexicographically."""
        norm = self._normalize_step_id(step_id)
        if isinstance(norm, int):
            return (0, norm)
        return (1, str(norm))

    async def execute_plan_sequence(
        self,
        raw_prompt: str,
        routing: Optional[RoutingPayload],
        stream_cb: Optional[Callable[[str], None]] = None,
        task_id: Optional[str] = None,
        fallback_single_turn_cb: Optional[Callable[..., Any]] = None,
    ) -> str:
        """Requests task decomposition from the planning agent and executes the resulting DAG."""
        logger.info("Initiating multi-step task decomposition via the planning agent...")

        # Fail Fast: Strict validation against DB system_roles
        planner_id = self.librarian.resolve_agent_id_for_role("system_planner")
        if not planner_id:
            raise RuntimeError(
                "Bootstrap Error: Mandatory system role 'system_planner' is not bound in system_roles."
            )

        generalist_id = self.librarian.resolve_agent_id_for_role("system_generalist")
        if not generalist_id:
            raise RuntimeError(
                "Bootstrap Error: Mandatory system role 'system_generalist' is not bound in system_roles."
            )

        if stream_cb:
            stream_cb("[Analyzing task complexity and drafting DAG execution strategy...]\n\n")

        planner = self.orchestrator.dispatcher._resolve_agent(planner_id)

        plan_res = planner.execute(
            action="decompose_task",
            parameters={"objective": raw_prompt, "prompt": raw_prompt},
            raw_prompt=raw_prompt,
        )
        plan = await plan_res if inspect.isawaitable(plan_res) else plan_res

        if not isinstance(plan, list) or not plan:
            logger.warning("Planner produced no valid execution steps. Fallback to standard execution.")
            if fallback_single_turn_cb:
                return await fallback_single_turn_cb(
                    raw_prompt=raw_prompt,
                    agent=planner_id,
                    stream_cb=stream_cb,
                    task_id=task_id,
                )
            return "Error: Could not decompose task or execute fallback."

        logger.info(f"Decomposed plan into {len(plan)} node DAG.")

        if self.ledger and task_id:
            await self.ledger.log_event(
                task_id=task_id,
                event_type="plan_decomposed",
                data={"total_steps": len(plan), "plan_summary": plan},
            )

        # Output the plan overview
        if stream_cb:
            stream_cb(f"**Execution Blueprint ({len(plan)} steps):**\n")
            for item in plan:
                s_num = self._normalize_step_id(item.get("step", "?"))
                raw_ref = item.get("agent", "Unknown")
                resolved_id = self.librarian.resolve_agent_id_for_role(raw_ref) or raw_ref
                s_agent = self.librarian.get_display_name_for_agent(resolved_id)
                s_action = item.get("action", "execute")
                deps = item.get("depends_on", [])
                dep_str = f" (Waits on {deps})" if deps else " (Parallel Ready)"
                stream_cb(f"  * **Step {s_num}**: `{s_agent}` → `{s_action}`{dep_str}\n")
            stream_cb("\n---\n")

        # --- Async DAG Execution Setup ---
        step_futures: Dict[Union[int, str], asyncio.Future] = {}
        results_history: Dict[Union[int, str], Dict[str, Any]] = {}
        stream_lock = asyncio.Lock()

        # Pre-pass: Normalize step IDs, initialize futures, and infer sequential dependencies if omitted
        for i, step_dict in enumerate(plan):
            s_num = self._normalize_step_id(step_dict.get("step", i + 1))
            step_dict["step"] = s_num
            step_futures[s_num] = asyncio.Future()

            if "depends_on" not in step_dict:
                step_dict["depends_on"] = [plan[i - 1]["step"]] if i > 0 else []
            else:
                step_dict["depends_on"] = [self._normalize_step_id(d) for d in step_dict["depends_on"]]

        async def execute_node(step_dict: Dict[str, Any]) -> str:
            step_num = step_dict["step"]
            deps = step_dict.get("depends_on", [])
            raw_agent_ref = str(step_dict.get("agent", generalist_id))
            action = str(step_dict.get("action", "execute"))
            raw_params = step_dict.get("parameters", {})
            requires_approval = step_dict.get("requires_approval", False)

            resolved_agent_id = self.librarian.resolve_agent_id_for_role(raw_agent_ref) or raw_agent_ref
            step_result: str = ""

            try:
                # 1. Await Dependencies & Prevent Failure Cascading
                for dep in deps:
                    if dep not in step_futures:
                        step_result = (
                            f"[Dependency Error]: Step {step_num} ({resolved_agent_id}::{action}) "
                            f"depends on unknown or non-existent Step '{dep}'."
                        )
                        logger.error(step_result)
                        results_history[step_num] = {
                            "step": step_num,
                            "agent": resolved_agent_id,
                            "action": action,
                            "output": step_result,
                        }
                        return step_result

                    dep_output = await step_futures[dep]

                    # Short-circuit downstream execution if prerequisite failed or was blocked
                    if isinstance(dep_output, str) and any(
                        dep_output.startswith(p)
                        for p in (
                            "[Authorization Denied]",
                            "[Authorization Error]",
                            "[Dependency Error]",
                            "[Runtime Error]",
                        )
                    ):
                        step_result = (
                            f"[Dependency Error]: Step {step_num} ({resolved_agent_id}::{action}) "
                            f"aborted due to failure in dependency Step {dep}."
                        )
                        logger.warning(step_result)
                        results_history[step_num] = {
                            "step": step_num,
                            "agent": resolved_agent_id,
                            "action": action,
                            "output": step_result,
                        }
                        return step_result

                # 2. Resolve Parameters using completed dependency outputs
                sorted_history_keys = sorted(results_history.keys(), key=self._step_sort_key)
                history_list = [results_history[k] for k in sorted_history_keys]
                resolved_params = self._resolve_step_references(raw_params, history_list)

                # 3. Capability Authorization Guard (agent_skill_map compliance)
                if not self.librarian.is_skill_available(action, resolved_agent_id):
                    step_result = (
                        f"[Authorization Error]: Agent '{resolved_agent_id}' is not authorized "
                        f"to execute action '{action}' per agent_skill_map."
                    )
                    logger.error(step_result)
                    results_history[step_num] = {
                        "step": step_num,
                        "agent": resolved_agent_id,
                        "action": action,
                        "output": step_result,
                    }
                    return step_result

                logger.info(f"Executing Step {step_num} [{resolved_agent_id}::{action}]")
                if self.ledger and task_id:
                    await self.ledger.log_event(
                        task_id=task_id,
                        event_type="step_started",
                        data={"step": step_num, "agent": resolved_agent_id, "action": action},
                    )

                # Thread-safe UI Streaming
                async with stream_lock:
                    if stream_cb:
                        display_agent = self.librarian.get_display_name_for_agent(resolved_agent_id)
                        stream_cb(f"\n### Step {step_num}: `{display_agent}` — `{action}`\n")

                # 4. Gatekeeper Verification
                if self.gatekeeper and requires_approval:
                    logger.warning(f"Step {step_num} flagged for authorization. Intercepting.")
                    synthetic_extraction = {"action": action, "parameters": resolved_params, "agent": resolved_agent_id}

                    manifest, g_action, approval_id = self.gatekeeper.intercept_task(
                        resolved_agent_id, synthetic_extraction, raw_prompt
                    )

                    if self.state_mgr and task_id:
                        await self.state_mgr.update_status(
                            task_id=task_id, status=TaskStatus.AWAITING_APPROVAL, approval_id=approval_id
                        )

                    async with stream_lock:
                        if stream_cb:
                            stream_cb(f"\n{manifest}\n\n[Awaiting step authorization token: {approval_id}...]\n")

                    decision = await self.gatekeeper.wait_for_decision(approval_id, timeout=300.0)
                    if decision not in ("APPROVED", "PROCEED"):
                        step_result = f"[Authorization Denied]: Step {step_num} ({resolved_agent_id}::{action}) blocked."
                        results_history[step_num] = {
                            "step": step_num,
                            "agent": resolved_agent_id,
                            "action": action,
                            "output": step_result,
                        }
                        return step_result

                    if self.state_mgr and task_id:
                        await self.state_mgr.update_status(task_id=task_id, status=TaskStatus.RUNNING)

                # 5. Agent Execution
                try:
                    agent_instance = self.orchestrator.dispatcher._resolve_agent(resolved_agent_id)
                    step_res = agent_instance.execute(
                        action=action,
                        parameters=resolved_params,
                        raw_prompt=raw_prompt,
                    )
                    step_result = await step_res if inspect.isawaitable(step_res) else step_res
                except Exception as e:
                    logger.error(f"Error executing step {step_num} ({resolved_agent_id}): {e}", exc_info=True)
                    step_result = f"[Runtime Error]: Execution aborted due to unhandled exception: {str(e)}"

                # 6. Self-Healing Intercept
                auth_prefixes = (
                    "[Authorization Denied]",
                    "[Authorization Error]",
                    "[Awaiting Authorization]",
                    "[Dependency Error]",
                )
                if isinstance(step_result, str) and not any(step_result.startswith(p) for p in auth_prefixes):
                    async with stream_lock:
                        step_result = await self.self_healing.handle_if_needed(
                            step_num=step_num,
                            agent_name=resolved_agent_id,
                            step_result=str(step_result),
                            raw_prompt=raw_prompt,
                            stream_cb=stream_cb,
                            task_id=task_id,
                        )

                if self.ledger and task_id:
                    await self.ledger.log_event(
                        task_id=task_id,
                        event_type="step_completed",
                        data={
                            "step": step_num,
                            "agent": resolved_agent_id,
                            "action": action,
                            "output_summary": str(step_result)[:300],
                        },
                    )

                # 7. Record Result
                results_history[step_num] = {
                    "step": step_num,
                    "agent": resolved_agent_id,
                    "action": action,
                    "output": step_result,
                }

                async with stream_lock:
                    if stream_cb:
                        stream_cb(f"\n*Step {step_num} completed.*\n")

                return str(step_result)

            except Exception as fatal_err:
                logger.error(f"Fatal unhandled engine failure in step {step_num}: {fatal_err}", exc_info=True)
                step_result = f"[Runtime Error]: Internal engine failure: {str(fatal_err)}"
                results_history[step_num] = {
                    "step": step_num,
                    "agent": resolved_agent_id,
                    "action": action,
                    "output": step_result,
                }
                return step_result

            finally:
                # Guarantee step future resolution with populated result to prevent downstream async deadlocks
                if step_num in step_futures and not step_futures[step_num].done():
                    step_futures[step_num].set_result(step_result)

        # Fire all nodes into the event loop safely
        await asyncio.gather(*(execute_node(s) for s in plan))

        # --- Final Assembly ---
        step_outputs: List[str] = []
        for step_num in sorted(results_history.keys(), key=self._step_sort_key):
            step_data = results_history[step_num]
            formatted = f"**Step {step_num} Output ({step_data['agent']})**:\n{step_data['output']}"
            step_outputs.append(formatted)

        final_summary = "\n\n---\n\n".join(step_outputs)
        self.orchestrator.record_turn(raw_prompt, final_summary)
        return final_summary

    def _sanitize_output_for_injection(self, output: Any, max_chars: int = 2000) -> str:
        """Truncates step outputs from the middle to protect LLM context windows."""
        text = str(output) if output is not None else ""
        if len(text) <= max_chars:
            return text

        half_len = max_chars // 2
        truncated_count = len(text) - max_chars
        return (
            f"{text[:half_len]}\n\n"
            f"[... Charon Context Guard: Truncated {truncated_count} characters of raw output ...]\n\n"
            f"{text[-half_len:]}"
        )

    def _resolve_step_references(
        self,
        parameters: Any,
        history: List[Dict[str, Any]],
        max_output_chars: int = 2000,
    ) -> Any:
        """Recursively replaces $STEP_X_OUTPUT placeholders using completed dependency history."""
        if not history or parameters is None:
            return parameters

        raw_last = history[-1].get("output", "")
        last_output = self._sanitize_output_for_injection(raw_last, max_chars=max_output_chars)

        if isinstance(parameters, str):
            val = parameters
            val = val.replace("$PREVIOUS_STEP_OUTPUT", last_output)
            val = val.replace("$LAST_OUTPUT", last_output)

            history_map = {self._normalize_step_id(item.get("step", "")): item for item in history}

            # Regex token matching avoids substring collisions (e.g. $STEP_1_OUTPUT vs $STEP_10_OUTPUT)
            def replace_placeholder(match: re.Match) -> str:
                raw_step_key = match.group(1)
                norm_key = self._normalize_step_id(raw_step_key)
                if norm_key in history_map:
                    raw_step_out = history_map[norm_key].get("output", "")
                    return self._sanitize_output_for_injection(
                        raw_step_out, max_chars=max_output_chars
                    )
                return match.group(0)

            val = re.sub(r"\$STEP_([a-zA-Z0-9_-]+)_OUTPUT", replace_placeholder, val)
            return val

        if isinstance(parameters, dict):
            return {
                k: self._resolve_step_references(v, history, max_output_chars=max_output_chars)
                for k, v in parameters.items()
            }

        if isinstance(parameters, list):
            return [
                self._resolve_step_references(item, history, max_output_chars=max_output_chars)
                for item in parameters
            ]

        return parameters