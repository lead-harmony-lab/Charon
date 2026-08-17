"""
charon/core/coordinator/engine.py
System Version: v1.0.0 | File Revision: 10.2.0

Module: Core Reflection Engine and Multi-Intent Coordinator Facade.
Refactored for strict Zero-Trust Execution, DB-backed state management,
Ephemeral Contract Key minting, and stateless ConstraintRevision failure mapping.
"""

import asyncio
import concurrent.futures
import inspect
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.agents.base import BaseAgent
from charon.core.contracts import (
    ContractResponse,
    DiagnosticArtifact,
    ExecutionStatus,
    GapType,
)
from charon.core.coordinator.constraints import build_constraint_revision
from charon.db.repositories.coordinator import CoordinatorStateRepository
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

logger = logging.getLogger("charon.core.coordinator")

MAX_LOOP_LIMIT = 25


def _exec_sync_or_async(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Executes a function safely whether it is synchronous or async."""
    if inspect.iscoroutinefunction(func):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(lambda: asyncio.run(func(*args, **kwargs)))
                return future.result()
        return asyncio.run(func(*args, **kwargs))

    result = func(*args, **kwargs)
    if inspect.iscoroutine(result):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(lambda: asyncio.run(result))
                return future.result()
        return asyncio.run(result)

    return result


class Coordinator:
    """The Zero-Trust Execution Engine governing the Charon execution loop."""

    def __init__(self, db_path: Path, agents: Optional[Dict[str, BaseAgent]] = None) -> None:
        self.db = CoordinatorStateRepository(db_path)
        self.agents = agents or {}

        # Phase 4: System Pruning (The Sweeper)
        # Execute background cleanup on init to prevent DB bloat
        self.db.sweep_stale_tasks(days_old=7)

    def register_agent(self, agent_id: str, agent_instance: BaseAgent) -> None:
        self.agents[agent_id] = agent_instance

    def process_pending_tasks(self) -> None:
        """Entry point for background worker: polls DB and executes."""
        tasks = self.db.get_pending_tasks()
        for task_row in tasks:
            self.run_task_lifecycle(task_row["task_id"])

    def run_task_lifecycle(self, task_id: str) -> None:
        """
        Manages the full Zero-Trust lifecycle for a single task:
        1. Planning -> 2. The Key Maker -> 3. Execution -> 4. The Burn
        """
        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.SYSTEM,
                agent_name="Coordinator",
                action="task_lifecycle_start",
                details={"task_id": task_id},
            )
        )

        try:
            # Re-fetch latest state to avoid race conditions
            tasks = [t for t in self.db.get_pending_tasks() if t["task_id"] == task_id]
            if not tasks:
                return
            task = tasks[0]

            # Phase 1: Task Ingestion & Planning (The Blueprint)
            plan_json = task["plan_json"]
            if not plan_json or task["status"] in ('PENDING', 'PLANNING'):
                plan_json = self._invoke_system_planner(task_id, task["prompt"])
                self.db.update_task_plan(task_id, plan_json)
            else:
                plan_json = json.loads(plan_json) if isinstance(plan_json, str) else plan_json

            # Phase 2 & 3: DAG Traversal & Execution
            self._execute_plan_loop(task_id, task, plan_json)

        except Exception as exc:
            logger.error(f"[COORDINATOR] Fatal Task Error {task_id}: {str(exc)}", exc_info=True)
            constraint = build_constraint_revision(str(exc))
            self.db.update_task_status(
                task_id,
                "FAILED",
                results_json={"constraint_revision": constraint.model_dump()},
            )

        finally:
            # Phase 4: Immediate Key Revocation (The Burn)
            # GUARANTEE: No matter how the loop exits, keys are destroyed.
            logger.info(f"[COORDINATOR] Triggering The Burn for task: {task_id}")
            self.db.burn_task_contracts(task_id)

    def _invoke_system_planner(self, task_id: str, prompt: str) -> Dict[str, Any]:
        """Invokes the system_planner PEC to generate the declarative DAG blueprint."""
        planner = self.agents.get("system_planner")
        if not planner:
            raise RuntimeError("CRITICAL: system_planner agent is not registered.")

        logger.info(f"[COORDINATOR] Generating Blueprint for task {task_id}...")
        payload = {"prompt": prompt, "task_id": task_id}
        plan_artifact = _exec_sync_or_async(planner.execute_task, payload=payload)

        # Duck-type conversion to dict if it's a Pydantic model
        return plan_artifact.model_dump() if hasattr(plan_artifact, "model_dump") else dict(plan_artifact)

    def _execute_plan_loop(self, task_id: str, task_state: Any, plan_json: Dict[str, Any]) -> None:
        """Iterates through the DAG blueprint, minting keys and executing."""
        steps = plan_json.get("steps", [])
        current_index = task_state["current_step_index"]

        step_count = 0
        final_results = {}

        while current_index < len(steps) and step_count < MAX_LOOP_LIMIT:
            step_node = steps[current_index]
            target_agent = step_node.get("agent_id")
            target_skill = step_node.get("skill_id")
            parameters = step_node.get("parameters", {})

            # ---------------------------------------------------------
            # Phase 2: THE KEY MAKER PHASE (Zero-Trust Minting)
            # ---------------------------------------------------------
            # LEVEL 0: Strict DB Audit (Base Capability + Legal Authority)
            if not self.db.audit_level_0_permission_strict(target_agent, target_skill):
                reason = f"ZERO-TRUST VIOLATION: '{target_agent}' lacks strict authority for '{target_skill}'."
                logger.critical(f"[COORDINATOR] {reason}")
                constraint = build_constraint_revision({
                    "failed_step": current_index,
                    "failed_action": target_skill,
                    "message": reason,
                })
                self.db.update_task_status(
                    task_id,
                    "REJECTED",
                    {"constraint_revision": constraint.model_dump()},
                )
                return

            # LEVEL 1: Mint Ephemeral Contract
            contract_id = self.db.mint_ephemeral_contract(
                task_id=task_id,
                agent_id=target_agent,
                skill_id=target_skill
            )

            # ---------------------------------------------------------
            # Phase 3: AGENT EXECUTION & STATE TRACKING
            # ---------------------------------------------------------
            agent_instance = self.agents.get(target_agent)
            if not agent_instance or not hasattr(agent_instance, "execute_task"):
                raise NotImplementedError(f"Agent {target_agent} missing valid Work Contract.")

            # Inject the minted authority into the payload
            execution_payload = dict(parameters)
            execution_payload["authorized_tools"] = [target_skill]
            execution_payload["active_contract_id"] = contract_id

            start_time = time.perf_counter()
            try:
                logger.info(f"[COORDINATOR] Executing step {current_index} via {target_agent} -> {target_skill}")
                artifact_result = _exec_sync_or_async(agent_instance.execute_task, payload=execution_payload)

                # Check for Diagnostic/Failure Artifacts
                if hasattr(artifact_result, "gap_type"):
                    constraint = build_constraint_revision(artifact_result)
                    logger.warning(f"[COORDINATOR] Step Execution Failed: {constraint.failure_summary}")
                    self.db.update_task_status(
                        task_id,
                        "FAILED",
                        {
                            "failed_step": current_index,
                            "constraint_revision": constraint.model_dump(),
                        },
                    )
                    return

                # Record success
                final_results[f"step_{current_index}"] = (
                    artifact_result.model_dump() if hasattr(artifact_result, "model_dump") else dict(artifact_result)
                )

            except Exception as exc:
                logger.error(f"[COORDINATOR] Execution crash in {target_agent}: {str(exc)}", exc_info=True)
                constraint = build_constraint_revision({
                    "failed_step": current_index,
                    "failed_action": target_skill,
                    "message": str(exc),
                })
                self.db.update_task_status(
                    task_id,
                    "FAILED",
                    {"constraint_revision": constraint.model_dump()},
                )
                return

            finally:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                telemetry_bus.emit(
                    TraceEvent(
                        event_type=TraceEventType.EXECUTION,
                        agent_name=target_agent,
                        action=target_skill,
                        duration_ms=duration_ms,
                        details={"contract_id": contract_id, "step_index": current_index}
                    )
                )

            # Advance State
            current_index += 1
            step_count += 1

            # Flush incremental state to DB via repository interface
            self.db.advance_task_step(task_id, current_index)

        # Loop completion handling
        if current_index >= len(steps):
            self.db.update_task_status(task_id, "COMPLETED", results_json=final_results)
            logger.info(f"[COORDINATOR] Task {task_id} COMPLETED successfully.")
        else:
            constraint = build_constraint_revision("MAX_LOOP_LIMIT exceeded.")
            self.db.update_task_status(
                task_id,
                "FAILED",
                {"constraint_revision": constraint.model_dump()},
            )
            logger.warning(f"[COORDINATOR] Task {task_id} FAILED: Loop limit reached.")