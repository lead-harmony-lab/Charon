"""
charon/core/skills/storage/dynamic/core.system.engineer/plugin.py
System Version: v1.0.0 | File Revision: 3.1.0

Exports the EngineerPolicyExecutionContainer for dynamic instantiation by the RuntimeAgent.
Implements dynamic self-healing code execution using qwen2.5-coder within
the Zero-Trust CBAC Paradigm.
"""

import asyncio
import json
import logging
import re
from typing import Any, Callable, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field

import ollama

from charon.core.permissions.contract_policies import BaseContractPolicy
from charon.core.permissions.middleware import PermissionDeniedError
from charon.config.paths import PROJECTS_DIR, resolve_project_path
from charon.gateway.gatekeeper import GatekeeperManager
from charon.telemetry.ledger import ExecutionLedger

logger = logging.getLogger(__name__)


# ==========================================
# 1. HARD ARTIFACT SCHEMAS (The Expected Output)
# ==========================================
class CodeDiff(BaseModel):
    file_path: str = Field(description="Target file path relative to workspace root.")
    original_snippet: str = Field(description="Original code snippet prior to modification.", default="")
    replacement_snippet: str = Field(description="Modified code replacement snippet.")


class EngineeringArtifact(BaseModel):
    issue_id: str = Field(description="Unique identifier for the engineering task or repair.")
    root_cause_analysis: str = Field(description="Detailed explanation of the identified bug or system flaw.")
    applied_diffs: List[CodeDiff] = Field(default_factory=list, description="List of code diffs applied to resolve the issue.")
    execution_output: str = Field(description="Stdout/Stderr result from executing the self-healing script.")
    verification_passed: bool = Field(description="Indicates whether test/syntax checks verified the fix.")
    final_code: str = Field(description="The complete self-healed runnable Python script.")


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
class EngineerPolicyExecutionContainer(BaseContractPolicy):
    """
    The execution envelope for the system_engineer role.
    Loads qwen2.5-coder to synthesize, execute, and self-heal Python code solutions,
    channeling peripheral tool calls through CBAC chokepoints in BaseAgent.
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

        self.artifact_schema = EngineeringArtifact
        self.model_name = "qwen2.5-coder:latest"
        self._telemetry_callback: Optional[Callable] = None
        self._cot_callback: Optional[Callable] = None

        self.base_system_prompt = (
            "You are an expert Python Software Engineer specializing in dynamic script resolution.\n"
            "RULES:\n"
            "1. Output ONLY runnable Python code wrapped in a ```python ``` markdown code block.\n"
            "2. Handle exceptions gracefully and print explicit diagnostic output to stdout.\n"
            "3. NEVER use interactive functions like input().\n"
            "4. Make the task succeed by writing clean, deterministic Python logic."
        )

    def bind_telemetry(self, callback: Callable) -> None:
        self._telemetry_callback = callback

    def bind_cot(self, callback: Callable) -> None:
        self._cot_callback = callback

    def _sanitize_payload(self, text: str, max_chars: int = 12000) -> str:
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

    def _extract_code(self, raw_response: str) -> str:
        code_match = re.search(r"```(?:python)?\s*(.*?)\s*```", raw_response, re.DOTALL)
        return code_match.group(1).strip() if code_match else raw_response.strip()

    def execute(
        self,
        task_payload: Dict[str, Any],
        authorized_tools: List[Dict[str, Any]],
        coordinator_constraints: Optional[Union[Dict[str, Any], BaseModel]] = None,
    ) -> BaseModel:

        if self._telemetry_callback:
            self._telemetry_callback(event_type="CONTRACT_STARTED", details={"phase": "self_healing_loop"})

        problem = (
            task_payload.get("user_query")
            or task_payload.get("problem")
            or task_payload.get("prompt")
            or task_payload.get("task")
            or ""
        )

        if not problem:
            return DiagnosticArtifact(
                tool_execution_successful=False,
                task_fulfilled=False,
                failure_category="ExecutionError",
                diagnostics="Missing required query parameter ('user_query', 'problem', 'prompt', or 'task') in task_payload.",
            )

        target_dir_raw = task_payload.get("target_dir") or task_payload.get("base_path")
        target_dir = (
            str(resolve_project_path(target_dir_raw))
            if target_dir_raw
            else str(PROJECTS_DIR)
        )

        max_attempts = min(int(task_payload.get("max_attempts", 2)), 3)
        timeout = float(task_payload.get("timeout", 15.0))
        python_cmd = task_payload.get("python_cmd", "python3")

        safe_problem = self._sanitize_payload(str(problem))
        feedback = ""
        last_output = ""
        client = ollama.Client()

        # LEVEL 1 LOCK: Injecting authorized tools directly into the system prompt
        allowed_tools_str = ", ".join([t.get("name", "unknown") for t in authorized_tools if isinstance(t, dict)]) if authorized_tools else "None"
        dynamic_system_prompt = self.base_system_prompt + f"\n5. AUTHORIZED TOOLS: You are strictly limited to invoking: {allowed_tools_str}."

        for attempt in range(1, max_attempts + 1):
            if self._cot_callback:
                self._cot_callback(
                    message=f"Self-healing attempt {attempt}/{max_attempts} using model {self.model_name}.",
                    thought_type="ANALYSIS",
                )

            prompt_text = (
                f"Task: {safe_problem}\nTarget Workspace: {target_dir}"
                if attempt == 1
                else f"Task: {safe_problem}\nFeedback from attempt {attempt-1}:\n{feedback}\nFix and return corrected code."
            )

            # Ingest and serialize constraints (supports dicts or Pydantic models like ConstraintRevision)
            if coordinator_constraints:
                if isinstance(coordinator_constraints, BaseModel):
                    constraints_str = coordinator_constraints.model_dump_json()
                else:
                    constraints_str = json.dumps(coordinator_constraints)
                prompt_text += f"\nREVISION CONSTRAINTS: {constraints_str}"

            try:
                response = client.generate(
                    model=self.model_name,
                    system=dynamic_system_prompt,
                    prompt=prompt_text,
                )
                raw_response = response.get("response", "").strip()
                code = self._extract_code(raw_response)

                if not code:
                    feedback = "Inference engine returned empty script block."
                    continue

                # EXECUTION TRIPWIRE: Calls BaseAgent.execute_sub_skill via self.tool_executor
                exec_result = self.tool_executor(
                    action="run_script_in_subprocess",
                    parameters={
                        "code": code,
                        "cwd": target_dir,
                        "python_cmd": python_cmd,
                        "timeout": timeout,
                    },
                    raw_prompt="Self-healing script execution step",
                )

                if isinstance(exec_result, dict):
                    output = exec_result.get("output", str(exec_result))
                    is_success = exec_result.get("is_success", False)
                else:
                    output = str(exec_result)
                    is_success = True

                last_output = output

                if is_success:
                    audit_result = self.tool_executor(
                        action="audit_written_artifacts",
                        parameters={"code": code, "cwd": target_dir},
                        raw_prompt="Workspace artifact audit step",
                    )

                    audit_ok = True
                    audit_msg = "Artifact audit passed."
                    if isinstance(audit_result, dict):
                        audit_ok = audit_result.get("audit_ok", True)
                        audit_msg = audit_result.get("audit_msg", audit_msg)

                    if not audit_ok:
                        feedback = f"{output}\n\nAudit Failure: {audit_msg}"
                        continue

                    artifact = EngineeringArtifact(
                        issue_id=f"eng_fix_{attempt}",
                        root_cause_analysis=f"Resolved task in attempt {attempt} using {self.model_name}.",
                        applied_diffs=[
                            CodeDiff(
                                file_path="workspace_execution.py",
                                replacement_snippet=code,
                            )
                        ],
                        execution_output=output,
                        verification_passed=True,
                        final_code=code,
                    )

                    if self._telemetry_callback:
                        self._telemetry_callback(
                            event_type="CONTRACT_COMPLETED",
                            details={"artifact": "EngineeringArtifact", "attempts": attempt},
                        )

                    return artifact

                feedback = output

            # LEVEL 2/3 LOCK: Catching the DB restriction and escalating to Gatekeeper
            except PermissionDeniedError as e:
                logger.warning(f"[{self.agent_id}] CBAC Boundary Breach. Escalating to Gatekeeper: {e}")

                if not self.gatekeeper:
                    feedback = f"Permission Denied. No Gatekeeper attached to handle escalation. {e}"
                    continue

                manifest, action_name, approval_id = self.gatekeeper.intercept_task(
                    agent=self.agent_id,
                    extraction=None,
                    user_raw_input=f"Attempted restricted action: run_script_in_subprocess\nReason: {e}"
                )

                # SYNC/ASYNC BRIDGE: Pausing synchronous container to await GNOME shell IPC
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                decision = loop.run_until_complete(
                    self.gatekeeper.wait_for_decision(approval_id)
                )

                if decision == "APPROVED":
                    feedback = "Human supervisor OVERRODE security block. You may proceed with the operation."
                else:
                    feedback = f"CRITICAL: Human supervisor REJECTED your action. Reason: {decision}. Choose a different approach."

                continue

            # Standard execution errors (syntax, timeouts)
            except Exception as e:
                logger.warning(f"[{self.agent_id}] Exception during attempt {attempt}: {e}")
                feedback = str(e)

        diagnostic = DiagnosticArtifact(
            tool_execution_successful=False,
            task_fulfilled=False,
            failure_category="ExecutionError",
            diagnostics=(
                f"Self-healing code execution failed after {max_attempts} attempts. "
                f"Last execution output:\n{last_output or feedback}"
            ),
        )

        if self._telemetry_callback:
            self._telemetry_callback(
                event_type="CONTRACT_FAILED",
                details={"category": diagnostic.failure_category, "diagnostics": diagnostic.diagnostics},
            )

        return diagnostic