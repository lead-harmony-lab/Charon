"""
charon/core/skills/storage/dynamic/core.system.planner/plugin.py
System Version: v1.0.0 | File Revision: 3.1.0

Exports the PlannerPolicyExecutionContainer for dynamic instantiation by the RuntimeAgent.
Implements Zero-Trust CBAC planning, constraint ingestion, and DAG construction.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, ValidationError

from charon.core.permissions.contract_policies import BaseContractPolicy
from charon.core.permissions.middleware import PermissionDeniedError
from charon.gateway.gatekeeper import GatekeeperManager
from charon.telemetry.ledger import ExecutionLedger

logger = logging.getLogger(__name__)


# ==========================================
# 1. HARD ARTIFACT SCHEMAS (The Expected Output)
# ==========================================
class DAGNode(BaseModel):
    node_id: str = Field(description="Unique identifier for the step (e.g., 'step_1').")
    target_skill: str = Field(description="The exact name of the authorized tool to invoke.")
    dependencies: List[str] = Field(default_factory=list, description="Node IDs that must complete before this step.")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Key-value arguments required by the target skill.")


class PlanArtifact(BaseModel):
    plan_id: str = Field(description="Unique identifier for this specific execution plan.")
    nodes: List[DAGNode] = Field(description="The directed acyclic graph of execution steps.")


# ==========================================
# 2. DIAGNOSTIC SCHEMAS (The Diff Engine Output)
# ==========================================
class DiagnosticArtifact(BaseModel):
    tool_execution_successful: bool
    task_fulfilled: bool
    failure_category: Literal["ExecutionError", "ToolMisalignment", "SkillDeficiency"]
    diagnostics: str


# ==========================================
# 3. THE POLICY EXECUTION CONTAINER
# ==========================================
class PlannerPolicyExecutionContainer(BaseContractPolicy):
    """
    The execution envelope for the system_planner role.
    Handles middleware sanitization, contextual tool injection, constraint parsing,
    and schema enforcement, ensuring the resulting DAG strictly adheres to contract policies.
    """

    def __init__(
        self,
        agent_id: str,
        gatekeeper: Optional[GatekeeperManager],
        tool_executor: Callable[..., Any],
        ledger: Optional[ExecutionLedger] = None,
    ):
        super().__init__(
            agent_id=agent_id,
            gatekeeper=gatekeeper,
            tool_executor=tool_executor,
            ledger=ledger,
        )

        # Define the expected output for Coordinator Probing
        self.artifact_schema = PlanArtifact

        # Initialize internal state callbacks
        self._telemetry_callback: Optional[Callable] = None
        self._cot_callback: Optional[Callable] = None

        # System instructions injected into the LLM context
        self.base_system_prompt = (
            "You are the System Planner. Your execution envelope is strictly bound. "
            "You must emit a valid JSON payload matching the PlanArtifact schema. "
            "Do not output conversational text. Use ONLY the authorized tools provided."
        )

    # --- TELEMETRY BINDING ---
    def bind_telemetry(self, callback: Callable) -> None:
        self._telemetry_callback = callback

    def bind_cot(self, callback: Callable) -> None:
        self._cot_callback = callback

    # --- MIDDLEWARE ---
    def _sanitize_payload(self, text: str, max_chars: int = 6000) -> str:
        if not text or len(text) <= max_chars:
            return text

        half = max_chars // 2
        truncated_count = len(text) - max_chars
        logger.warning(f"[{self.agent_id}] Payload exceeded context bounds. Truncated {truncated_count} chars.")

        return (
            f"{text[:half]}\n\n"
            f"[... Charon Middleware Guard: Truncated {truncated_count} raw characters ...]\n\n"
            f"{text[-half:]}"
        )

    # --- TOOL TRANSLATION ---
    def _translate_tools_for_planner(self, raw_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        translated_tools = []
        for tool in raw_tools:
            t_copy = tool.copy() if isinstance(tool, dict) else tool
            if isinstance(t_copy, dict):
                original_desc = t_copy.get("description", "")
                t_copy["description"] = f"[PLANNING CONTEXT: Use this node to {original_desc.lower()}]"
            translated_tools.append(t_copy)
        return translated_tools

    # --- THE DIFF ENGINE ---
    def _run_error_analysis(self, error: Exception, raw_output: Any) -> DiagnosticArtifact:
        logger.error(f"[{self.agent_id}] Validation failed: {str(error)}")

        if isinstance(error, ValidationError):
            return DiagnosticArtifact(
                tool_execution_successful=False,
                task_fulfilled=False,
                failure_category="ExecutionError",
                diagnostics=f"Schema violation detected: {str(error)}",
            )

        return DiagnosticArtifact(
            tool_execution_successful=False,
            task_fulfilled=False,
            failure_category="ExecutionError",
            diagnostics=f"Execution failure during plan generation: {str(error)}",
        )

    # --- MAIN EXECUTION LOOP ---
    def execute(
        self,
        task_payload: Dict[str, Any],
        authorized_tools: List[Dict[str, Any]],
        coordinator_constraints: Optional[Union[Dict[str, Any], BaseModel]] = None,
    ) -> BaseModel:
        if self._telemetry_callback:
            self._telemetry_callback(event_type="CONTRACT_STARTED", details={"phase": "sanitization"})

        # Resolve request string across multiple potential payload conventions
        raw_request = (
            task_payload.get("user_query")
            or task_payload.get("prompt")
            or task_payload.get("task")
            or (json.dumps(task_payload) if isinstance(task_payload, dict) else str(task_payload))
        )
        safe_request = self._sanitize_payload(str(raw_request))
        framed_tools = self._translate_tools_for_planner(authorized_tools)

        # LEVEL 1 SOFT LOCK: Injecting authorized nodes into the system prompt
        allowed_tools_str = ", ".join([t.get("name", "unknown") for t in authorized_tools if isinstance(t, dict)]) if authorized_tools else "None"
        dynamic_system_prompt = self.base_system_prompt + f"\n\nAUTHORIZED DELEGATION NODES: {allowed_tools_str}."

        # Ingest and serialize constraints (supports dicts or Pydantic models like ConstraintRevision)
        if coordinator_constraints:
            if isinstance(coordinator_constraints, BaseModel):
                constraints_str = coordinator_constraints.model_dump_json()
            else:
                constraints_str = json.dumps(coordinator_constraints)
            dynamic_system_prompt += f"\nCRITICAL REVISION CONSTRAINTS: {constraints_str}"

        if self._cot_callback:
            self._cot_callback(message="Generating DAG based on translated tools and constraints.", thought_type="ANALYSIS")

        # LLM Output Generation Target
        raw_llm_output = {}

        try:
            valid_artifact = self.artifact_schema(**raw_llm_output)

            # LEVEL 1 HARD LOCK: Ensuring the DAG doesn't route to unauthorized tools
            allowed_tool_names = [t.get("name") for t in authorized_tools if isinstance(t, dict)]
            for node in valid_artifact.nodes:
                if node.target_skill not in allowed_tool_names:
                    raise PermissionDeniedError(f"Planner attempted to route task to unauthorized skill: '{node.target_skill}'")

            logger.info(f"[{self.agent_id}] PlanArtifact successfully validated.")

            if self._telemetry_callback:
                self._telemetry_callback(event_type="CONTRACT_COMPLETED", details={"artifact": "PlanArtifact"})

            return valid_artifact

        # LEVEL 2/3 LOCK: Escalate delegation boundary breaches to GNOME Gatekeeper
        except PermissionDeniedError as e:
            logger.warning(f"[{self.agent_id}] CBAC Delegation Boundary Breach. Escalating to Gatekeeper: {e}")

            if not self.gatekeeper:
                return self._run_error_analysis(e, raw_llm_output)

            manifest, action_name, approval_id = self.gatekeeper.intercept_task(
                agent=self.agent_id,
                extraction=None,
                user_raw_input=f"Planner attempted restricted delegation.\nReason: {e}"
            )

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            decision = loop.run_until_complete(
                self.gatekeeper.wait_for_decision(approval_id)
            )

            if decision == "APPROVED":
                logger.info(f"[{self.agent_id}] Human OVERRODE delegation block.")
                return valid_artifact
            else:
                logger.warning(f"[{self.agent_id}] Human REJECTED delegation route.")
                return self._run_error_analysis(e, raw_llm_output)

        except ValidationError as e:
            diagnostic = self._run_error_analysis(e, raw_llm_output)

            if diagnostic.failure_category in ["ToolMisalignment", "SkillDeficiency"]:
                logger.error(f"[{self.agent_id}] Fast-fail triggered: {diagnostic.failure_category}")
                return diagnostic
            elif diagnostic.failure_category == "ExecutionError":
                logger.warning(f"[{self.agent_id}] Execution error. Yielding DiagnosticArtifact to Escalation Manager.")
                return diagnostic