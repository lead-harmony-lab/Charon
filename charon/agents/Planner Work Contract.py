import logging
import json
from typing import Any, Callable, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ValidationError

# Core System Imports (aligned with your base.py and runtime.py)
from charon.agents.base import BaseWorkContract
from charon.gateway.gatekeeper import GatekeeperManager
from charon.telemetry.ledger import ExecutionLedger

logger = logging.getLogger("Charon.Contracts.Planner")


# ==========================================
# 1. HARD ARTIFACT SCHEMAS (The Expected Output)
# ==========================================
class DAGNode(BaseModel):
    node_id: str = Field(description="Unique identifier for the step (e.g., 'step_1').")
    target_skill: str = Field(description="The exact name of the authorized tool to invoke.")
    dependencies: List[str] = Field(default_factory=list, description="Node IDs that must complete before this step.")
    arguments: Dict[str, Any] = Field(description="Key-value arguments required by the target skill.")


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
# 3. THE WORK CONTRACT ENVELOPE
# ==========================================
class PlannerWorkContract(BaseWorkContract):
    """
    The execution envelope for the system_planner role.
    Handles middleware sanitization, contextual tool injection, and schema enforcement.
    Inherits from BaseWorkContract to satisfy the Charon Orchestration Engine interfaces.
    """

    def __init__(
            self,
            agent_id: str,
            gatekeeper: Optional[GatekeeperManager],
            tool_executor: Callable[[str, Dict[str, Any], str], Any],
            ledger: Optional[ExecutionLedger] = None
    ):
        # 1. Satisfy the Abstract Base Class constructor
        super().__init__(
            agent_id=agent_id,
            gatekeeper=gatekeeper,
            tool_executor=tool_executor,
            ledger=ledger
        )

        # 2. Define the expected output for Coordinator Probing
        self.artifact_schema = PlanArtifact

        # 3. Initialize internal state callbacks
        self._telemetry_callback: Optional[Callable] = None
        self._cot_callback: Optional[Callable] = None

        # System instructions injected into the LLM context
        self.system_prompt = (
            "You are the System Planner. Your execution envelope is strictly bound. "
            "You must emit a valid JSON payload matching the PlanArtifact schema. "
            "Do not output conversational text. Use ONLY the authorized tools provided."
        )

    # --- TELEMETRY BINDING (Satisfying the ABC) ---
    def bind_telemetry(self, callback: Callable) -> None:
        """Binds standard agent telemetry trace reporting from the RuntimeAgent."""
        self._telemetry_callback = callback

    def bind_cot(self, callback: Callable) -> None:
        """Binds Chain of Thought (CoT) internal reasoning reporting from the RuntimeAgent."""
        self._cot_callback = callback

    # --- MIDDLEWARE ---
    def _sanitize_payload(self, text: str, max_chars: int = 6000) -> str:
        """Truncates massive inputs BEFORE the LLM sees them to preserve context."""
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
        """Contextualizes generic tools specifically for the Planner persona."""
        translated_tools = []
        for tool in raw_tools:
            t_copy = tool.copy()
            original_desc = t_copy.get("description", "")
            t_copy["description"] = f"[PLANNING CONTEXT: Use this node to {original_desc.lower()}]"
            translated_tools.append(t_copy)
        return translated_tools

    # --- THE DIFF ENGINE ---
    def _run_error_analysis(self, error: Exception, raw_output: Any) -> DiagnosticArtifact:
        """Evaluates schema failures or logic breakdowns and packages them for the Coordinator."""
        logger.error(f"[{self.agent_id}] Validation failed: {str(error)}")

        if isinstance(error, ValidationError):
            return DiagnosticArtifact(
                tool_execution_successful=False,
                task_fulfilled=False,
                failure_category="ExecutionError",
                diagnostics=f"Schema violation detected: {str(error)}"
            )

        return DiagnosticArtifact(
            tool_execution_successful=False,
            task_fulfilled=False,
            failure_category="ExecutionError",
            diagnostics="Unknown execution failure during plan generation."
        )

    # --- MAIN EXECUTION LOOP ---
    def execute(
            self,
            task_payload: Dict[str, Any],
            authorized_tools: List[Dict[str, Any]],
            coordinator_constraints: Optional[Dict[str, Any]] = None
    ) -> BaseModel:
        """
        The primary entrypoint invoked by RuntimeAgent.execute_task().
        """
        if self._telemetry_callback:
            self._telemetry_callback(event_type="CONTRACT_STARTED", details={"phase": "sanitization"})

        # 1. Apply Middleware
        raw_request = task_payload.get("user_query", "")
        safe_request = self._sanitize_payload(raw_request)

        # 2. Translate Tools contextually
        framed_tools = self._translate_tools_for_planner(authorized_tools)

        # 3. Compile prompt with constraints
        runtime_prompt = self.system_prompt
        if coordinator_constraints:
            runtime_prompt += f"\nCRITICAL REVISION CONSTRAINTS: {json.dumps(coordinator_constraints)}"

        # 4. Invoke LLM (Mocked for architecture mapping)
        if self._cot_callback:
            self._cot_callback(message="Generating DAG based on translated tools.", thought_type="ANALYSIS")

        raw_llm_output = {}

        # 5. Localized Validation & Fast-Fail Routing
        try:
            valid_artifact = self.artifact_schema(**raw_llm_output)
            logger.info(f"[{self.agent_id}] PlanArtifact successfully validated.")

            if self._telemetry_callback:
                self._telemetry_callback(event_type="CONTRACT_COMPLETED", details={"artifact": "PlanArtifact"})

            return valid_artifact

        except ValidationError as e:
            # 6. Engage the Diff Engine
            diagnostic = self._run_error_analysis(e, raw_llm_output)

            # 7. Fast-Fail Routing
            if diagnostic.failure_category in ["ToolMisalignment", "SkillDeficiency"]:
                logger.error(f"[{self.agent_id}] Fast-fail triggered: {diagnostic.failure_category}")
                return diagnostic

            elif diagnostic.failure_category == "ExecutionError":
                logger.warning(f"[{self.agent_id}] Execution error. Yielding DiagnosticArtifact to Escalation Manager.")
                return diagnostic