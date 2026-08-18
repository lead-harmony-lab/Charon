"""
charon/core/coordinator/engine.py
System Version: v1.2.2 | File Revision: 10.7.0

Module: Core Reflection Engine and Multi-Intent Coordinator Facade.
Refactored for strict Zero-Trust Execution, DB-backed state management,
RoleResolver-driven pre-audit normalization, ephemeral contract minting,
and Just-In-Time (JIT) Agent Container Hydration.
"""

import asyncio
import concurrent.futures
import inspect
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.agents.base import BaseAgent
from charon.agents.runtime import RuntimeAgent  # Required for JIT Hydration
from charon.config.paths import WORKSPACES_DIR
from charon.core.contracts import (
    ContractResponse,
    DiagnosticArtifact,
    ExecutionStatus,
    GapType,
)
from charon.core.coordinator.constraints import build_constraint_revision
from charon.core.skills import SkillLibrarian
from charon.core.skills.roles import RoleResolutionError
from charon.db.repositories.coordinator import CoordinatorStateRepository
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus
from charon.gateway.gatekeeper import GatekeeperManager
from charon.telemetry.ledger import ExecutionLedger

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


def resolve_user_facing_output(blackboard: Dict[str, Any]) -> str:
    """
    Extracts user-facing stdout or results from blackboard step artifacts,
    preventing raw Pydantic JSON metadata dumps to the client emitter.
    """
    if not isinstance(blackboard, dict):
        return str(blackboard)

    # Short-circuit if output has already been resolved to a result string
    if "result" in blackboard and isinstance(blackboard["result"], str):
        return blackboard["result"]

    # Unwrap nested blackboard if wrapped in DB envelope
    if "blackboard" in blackboard and isinstance(blackboard["blackboard"], dict):
        blackboard = blackboard["blackboard"]

    results = []

    for step_id, data in blackboard.items():
        if isinstance(data, dict):
            # 1. Handle EngineeringArtifact results (pull raw stdout)
            if "execution_output" in data and data["execution_output"]:
                results.append(data["execution_output"].strip())
            # 2. Fallback to final code if stdout was empty
            elif "final_code" in data and data["final_code"]:
                results.append(f"```python\n{data['final_code'].strip()}\n```")
            # 3. Handle DiagnosticArtifact results
            elif "diagnostics" in data:
                results.append(str(data["diagnostics"]))
            elif "failure_summary" in data and data["failure_summary"]:
                results.append(str(data["failure_summary"]))
            else:
                results.append(str(data))
        else:
            results.append(str(data))

    return "\n\n".join(results) if results else "Task executed successfully."


class Coordinator:
    """The Zero-Trust Execution Engine governing the Charon execution loop."""

    def __init__(
        self,
        db_path: Path,
        agents: Optional[Dict[str, BaseAgent]] = None,
        gatekeeper: Optional[GatekeeperManager] = None,
        ledger: Optional[ExecutionLedger] = None,
        heavy_model: str = "llama3.1",
    ) -> None:
        self.db = CoordinatorStateRepository(db_path)
        self.agents = agents or {}

        # Inject Orchestrator dependencies
        self.gatekeeper = gatekeeper
        self.ledger = ledger
        self.heavy_model = heavy_model

        # Phase 4: System Pruning (The Sweeper)
        swept_task_ids = self.db.sweep_stale_tasks(days_old=7)
        for swept_id in swept_task_ids:
            self._purge_task_workspace(swept_id)

    def _purge_task_workspace(self, task_id: str) -> None:
        """Helper to safely remove task workspace artifacts from disk."""
        task_workspace = WORKSPACES_DIR / task_id
        if task_workspace.exists() and task_workspace.is_dir():
            try:
                shutil.rmtree(task_workspace)
                logger.info(f"[CLEANUP] Purged workspace directory for task: {task_id}")
            except Exception as e:
                logger.error(f"[CLEANUP] Failed to purge workspace for task {task_id}: {e}")

    def register_agent(self, agent_id: str, agent_instance: BaseAgent) -> None:
        self.agents[agent_id] = agent_instance

    def _hydrate_agent(self, agent_id: str, role_name: Optional[str] = None) -> BaseAgent:
        """Just-In-Time (JIT) provisioning of Policy Execution Containers."""
        # Return if already hydrated in this lifecycle
        if agent_id in self.agents:
            return self.agents[agent_id]

        librarian = SkillLibrarian.get_instance()

        logger.debug(f"[COORDINATOR] Hydrating Work Contract for '{agent_id}'...")
        agent_meta = librarian.get_agent_manifest(agent_id) or {}

        contract = (
            agent_meta.get("default_action")
            or agent_meta.get("default_action_contract")
            or f"{agent_id}_contract"
        )
        display_name = agent_meta.get("display_name", agent_id.replace("_", " ").title())
        description = agent_meta.get("description", f"Automated RuntimeAgent for {agent_id}.")
        priority = agent_meta.get("priority_weight", 1.0)

        # Pull dependencies injected by the Orchestrator (or default them)
        heavy_model = getattr(self, "heavy_model", "llama3.1")
        gatekeeper = getattr(self, "gatekeeper", None)
        ledger = getattr(self, "ledger", None)

        agent_instance = RuntimeAgent(
            agent_id=agent_id,
            default_action_contract=contract,
            role_name=role_name or agent_meta.get("role", agent_id),
            display_name=display_name,
            description=description,
            priority_weight=priority,
            heavy_model=heavy_model,
            librarian=librarian,
            gatekeeper=gatekeeper,
            ledger=ledger,
        )

        # Cache the container for the duration of this Coordinator's lifecycle
        self.register_agent(agent_id, agent_instance)
        logger.info(f"[COORDINATOR] Successfully provisioned Work Contract for '{agent_id}'.")

        return agent_instance

    def process_pending_tasks(self) -> None:
        """Entry point for background worker: polls DB and executes."""
        tasks = self.db.get_pending_tasks()
        for task_row in tasks:
            self.run_task_lifecycle(task_row["task_id"])

    def run_task_lifecycle(
        self,
        task_id: str,
        user_input: Optional[str] = None,
        system_topology: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Manages the full Zero-Trust lifecycle for a single task:
        1. Planning -> 2. The Key Maker -> 3. Execution -> 4. The Burn
        """
        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.INITIALIZATION,
                agent_name="Coordinator",
                action="task_lifecycle_start",
                details={"task_id": task_id},
            )
        )

        try:
            tasks = [t for t in self.db.get_pending_tasks() if t["task_id"] == task_id]
            if not tasks:
                return
            task = tasks[0]

            # Phase 1: Task Ingestion & Planning (The Blueprint)
            plan_json = task["plan_json"]
            if not plan_json or task["status"] in ("PENDING", "PLANNING"):
                prompt = user_input or task.get("prompt", "")
                plan_json = self._invoke_system_planner(
                    task_id,
                    prompt,
                    system_topology=system_topology,
                    metadata=metadata,
                )
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
            # Phase 4: Immediate Key Revocation & Filesystem Cleanup (The Burn)
            logger.info(f"[COORDINATOR] Triggering The Burn for task: {task_id}")
            self.db.burn_task_contracts(task_id)
            self._purge_task_workspace(task_id)

    def _invoke_system_planner(
        self,
        task_id: str,
        prompt: str,
        system_topology: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Invokes the planner PEC to generate the declarative DAG blueprint."""
        librarian = SkillLibrarian.get_instance()

        # Resolve canonical planner ID through system_roles
        try:
            canonical_planner_id = librarian.resolve_agent_id_for_role("planner")
        except RoleResolutionError:
            canonical_planner_id = "system_planner"

        # Dynamically provision the planner via JIT
        planner = self._hydrate_agent(canonical_planner_id, role_name="planner")

        logger.info(f"[COORDINATOR] Generating Blueprint for task {task_id} via '{canonical_planner_id}'...")

        planner_role = getattr(planner, "role_name", None) or canonical_planner_id
        planner_skill = librarian.get_default_action_for_role(planner_role)
        if not planner_skill:
            raise RuntimeError(f"CRITICAL: No default action configured for planner role '{planner_role}'.")

        # 1. Fetch ALL tool skills from DB to provide context to the Planner
        global_tool_catalog = librarian.get_execution_tool_catalog(
            role_name=None,
            skill_type="tool",
            as_dict=True,
        )

        # 2. Delegation Authority Boundary Extraction
        planner_authorized_tools: List[str] = []
        if isinstance(global_tool_catalog, list):
            for item in global_tool_catalog:
                if isinstance(item, dict):
                    sk_id = item.get("skill_id")
                    act_name = item.get("action_name") or item.get("name") or item.get("action")
                    if sk_id:
                        planner_authorized_tools.append(str(sk_id))
                    if act_name:
                        planner_authorized_tools.append(str(act_name))
                else:
                    sk_id = getattr(item, "skill_id", None)
                    act_name = (
                        getattr(item, "action_name", None)
                        or getattr(item, "name", None)
                        or getattr(item, "action", None)
                    )
                    if sk_id:
                        planner_authorized_tools.append(str(sk_id))
                    if act_name:
                        planner_authorized_tools.append(str(act_name))

        elif isinstance(global_tool_catalog, dict):
            for key, val in global_tool_catalog.items():
                if isinstance(val, dict):
                    sk_id = val.get("skill_id")
                    act_name = val.get("action_name") or key
                    if sk_id:
                        planner_authorized_tools.append(str(sk_id))
                    if act_name:
                        planner_authorized_tools.append(str(act_name))
                else:
                    planner_authorized_tools.append(str(key))

        planner_authorized_tools = list(dict.fromkeys(planner_authorized_tools))

        # 3. Mint Ephemeral Contract for Planner using canonical ID
        contract_id = self.db.mint_ephemeral_contract(
            task_id=task_id,
            agent_id=canonical_planner_id,
            skill_id=planner_skill,
            authorized_tools=planner_authorized_tools,
        )

        active_topology = system_topology if system_topology is not None else librarian.get_system_topology()

        payload = {
            "prompt": prompt,
            "task_id": task_id,
            "active_contract_id": contract_id,
            "skill_catalog": global_tool_catalog,
            "authorized_tools": planner_authorized_tools,
            "system_topology": active_topology,
            "metadata": metadata or {},
        }

        catalog_count = len(global_tool_catalog) if isinstance(global_tool_catalog, (dict, list)) else 0
        topology_count = len(active_topology) if isinstance(active_topology, list) else 0

        logger.info(
            f"[COORDINATOR.PLANNER_PAYLOAD] Invoking Planner (Task: {task_id}, Contract: {contract_id}, "
            f"Catalog Tools: {catalog_count}, Topology Nodes: {topology_count}, "
            f"Authorized Tools: {len(planner_authorized_tools)})"
        )

        plan_artifact = _exec_sync_or_async(planner.execute_task, payload=payload)

        # 5. Strict failure handling for DiagnosticArtifacts
        is_diagnostic = False
        error_msg = "Planner returned a Diagnostic Artifact"

        artifact_type = (
            plan_artifact.get("artifact_type")
            if isinstance(plan_artifact, dict)
            else getattr(plan_artifact, "artifact_type", None)
        )
        status = str(
            plan_artifact.get("status")
            if isinstance(plan_artifact, dict)
            else getattr(plan_artifact, "status", "")
        )
        has_gap = "gap_type" in plan_artifact if isinstance(plan_artifact, dict) else hasattr(plan_artifact, "gap_type")

        if artifact_type == "diagnostic" or "FAILED" in status or has_gap:
            is_diagnostic = True
            if isinstance(plan_artifact, dict):
                error_msg = plan_artifact.get("failure_summary") or plan_artifact.get("error") or error_msg
            else:
                error_msg = (
                    getattr(plan_artifact, "failure_summary", None)
                    or getattr(plan_artifact, "error", None)
                    or error_msg
                )

        if is_diagnostic:
            raise RuntimeError(f"Planning Phase Failed: {error_msg}")

        return plan_artifact if isinstance(plan_artifact, dict) else plan_artifact.model_dump()

    def _execute_plan_loop(self, task_id: str, task_state: Any, plan_json: Dict[str, Any]) -> None:
        """Iterates through the DAG blueprint, minting keys and executing."""
        librarian = SkillLibrarian.get_instance()
        steps = plan_json.get("nodes", plan_json.get("steps", []))

        if not steps:
            raise RuntimeError(
                "Task execution aborted: Blueprint generated 0 executable steps (CBAC/Validation failure)."
            )
        current_index = task_state["current_step_index"]

        step_count = 0
        final_results = {}

        while current_index < len(steps) and step_count < MAX_LOOP_LIMIT:
            step_node = steps[current_index]

            # 1. Extract step requirements
            if isinstance(step_node, dict):
                target_skill = step_node.get("target_skill") or step_node.get("skill_id")
                target_agent = step_node.get("target_agent") or step_node.get("agent_id")
                parameters = step_node.get("arguments") or step_node.get("parameters") or {}
            else:
                target_skill = getattr(step_node, "target_skill", None) or getattr(step_node, "skill_id", None)
                target_agent = getattr(step_node, "target_agent", None) or getattr(step_node, "agent_id", None)
                parameters = getattr(step_node, "arguments", None) or getattr(step_node, "parameters", {}) or {}

            # 2. Domain Resolution: Resolve skill default agent if unassigned
            if target_skill and not target_agent:
                target_agent = librarian.get_agent_for_skill(target_skill)

            # 3. DB-Backed Pre-Audit Role Resolution
            # Resolve target_agent to canonical agent_id BEFORE Zero-Trust Level 0 Audit
            if target_agent:
                try:
                    canonical_id = librarian.resolve_agent_id_for_role(target_agent)
                    if canonical_id:
                        target_agent = canonical_id
                except RoleResolutionError:
                    logger.warning(f"[COORDINATOR] Unmapped role alias '{target_agent}' at step {current_index}.")

            # 4. Guard against unresolvable bindings
            if not target_agent or not target_skill:
                reason = f"ZERO-TRUST VIOLATION: Unresolvable agent/skill binding at step {current_index} (Agent='{target_agent}', Skill='{target_skill}')."
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

            # ---------------------------------------------------------
            # Phase 2: THE KEY MAKER PHASE (Zero-Trust Minting)
            # ---------------------------------------------------------
            # LEVEL 0: Strict DB Audit using canonical target_agent
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

            # LEVEL 1: Mint Ephemeral Contract against canonical ID
            contract_id = self.db.mint_ephemeral_contract(
                task_id=task_id,
                agent_id=target_agent,
                skill_id=target_skill,
            )

            # ---------------------------------------------------------
            # Phase 3: AGENT EXECUTION & STATE TRACKING
            # ---------------------------------------------------------
            try:
                agent_instance = self._hydrate_agent(target_agent)
            except Exception as e:
                raise NotImplementedError(f"Failed to provision Work Contract for '{target_agent}': {e}")

            if not hasattr(agent_instance, "execute_task"):
                raise NotImplementedError(f"Agent '{target_agent}' missing valid execute_task method.")

            execution_payload = dict(parameters)
            execution_payload["authorized_tools"] = [target_skill]
            execution_payload["active_contract_id"] = contract_id

            start_time = time.perf_counter()
            try:
                logger.info(f"[COORDINATOR] Executing step {current_index} via {target_agent} -> {target_skill}")
                artifact_result = _exec_sync_or_async(agent_instance.execute_task, payload=execution_payload)

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
                        details={"contract_id": contract_id, "step_index": current_index},
                    )
                )

            current_index += 1
            step_count += 1
            self.db.advance_task_step(task_id, current_index)

        if current_index >= len(steps):
            user_output = resolve_user_facing_output(final_results)
            self.db.update_task_status(
                task_id,
                "COMPLETED",
                results_json={"result": user_output, "blackboard": final_results},
            )
            logger.info(f"[COORDINATOR] Task {task_id} COMPLETED successfully.")
        else:
            constraint = build_constraint_revision("MAX_LOOP_LIMIT exceeded.")
            self.db.update_task_status(
                task_id,
                "FAILED",
                {"constraint_revision": constraint.model_dump()},
            )
            logger.warning(f"[COORDINATOR] Task {task_id} FAILED: Loop limit reached.")