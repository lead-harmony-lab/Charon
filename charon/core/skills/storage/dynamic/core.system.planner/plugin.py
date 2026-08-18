"""
charon/core/skills/storage/dynamic/core.system.planner/plugin.py
System Version: v1.0.0 | File Revision: 3.4.0

Exports the PlannerPolicyExecutionContainer for dynamic instantiation by the RuntimeAgent.
Implements Zero-Trust CBAC planning, constraint ingestion, dynamic grammar sampling, and strict DAG construction.
Integrates SkillLibrarian for strict agent-capability resolution and JIT envelope enforcement.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, ValidationError, create_model

from charon.core.permissions.contract_policies import BaseContractPolicy
from charon.core.permissions.middleware import PermissionDeniedError
from charon.gateway.gatekeeper import GatekeeperManager
from charon.telemetry.ledger import ExecutionLedger

logger = logging.getLogger(__name__)


# ==========================================
# 1. HARD ARTIFACT SCHEMAS (Baseline Reference)
# ==========================================
class DAGNode(BaseModel):
    node_id: str = Field(description="Unique identifier for the step (e.g., 'step_1').")
    target_agent: str = Field(description="Mandatory target agent assigned to execute this step.")
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
            "Do not output conversational text. Use ONLY the authorized tools and target agents provided."
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
    def _translate_tools_for_planner(self, raw_tools: Any) -> List[Dict[str, Any]]:
        # Normalize dictionary to list if passed via as_dict=True from Coordinator
        tool_list = list(raw_tools.values()) if isinstance(raw_tools, dict) else raw_tools

        translated_tools = []
        for tool in tool_list:
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

        # Extract tools and system topology passed by Coordinator
        skill_catalog = task_payload.get("skill_catalog", [])
        system_topology = task_payload.get("system_topology", [])

        framed_catalog = self._translate_tools_for_planner(skill_catalog)

        # Identify delegatable tool names and build the Skill-to-Agent map
        from charon.core.skills.librarian import SkillLibrarian

        delegatable_tool_names = []
        skill_owner_map = {}

        # Instantiate the global Librarian singleton
        librarian = SkillLibrarian.get_instance()

        for t in framed_catalog:
            if isinstance(t, dict):
                # Prioritize strict skill_id to ensure the LLM generates a Zero-Trust compliant DAG
                name = t.get("skill_id") or t.get("action_name") or t.get("name")

                # Librarian natively cross-references agent_skill_map and skill_registry
                owner = librarian.get_agent_for_skill(name) if name else None

                if name:
                    delegatable_tool_names.append(name)
                    if owner:
                        skill_owner_map[name] = owner
                    else:
                        logger.warning(
                            f"[{self.agent_id}] Librarian could not resolve an owner for '{name}'."
                        )

        delegatable_tools_str = ", ".join(delegatable_tool_names) if delegatable_tool_names else "None"

        available_agents = [
            a.get("agent_id") for a in system_topology if isinstance(a, dict) and a.get("agent_id")
        ]
        available_agents_str = ", ".join(available_agents) if available_agents else "engineer"

        # ------------------------------------------------------------------
        # SAMPLING-LEVEL FIX: Dynamic Schema Construction
        # Build strict Literal types dynamically so Ollama's GBNF grammar
        # physically locks token generation to authorized agents & skills.
        # ------------------------------------------------------------------
        AgentEnum = Literal.__getitem__(tuple(available_agents)) if available_agents else str
        SkillEnum = Literal.__getitem__(tuple(delegatable_tool_names)) if delegatable_tool_names else str

        DynamicDAGNode = create_model(
            "DynamicDAGNode",
            node_id=(str, Field(description="Unique identifier for the step (e.g., 'step_1').")),
            target_agent=(AgentEnum, Field(description="Mandatory target agent assigned to execute this step.")),
            target_skill=(SkillEnum, Field(description="The exact name of the authorized tool to invoke.")),
            dependencies=(List[str], Field(default_factory=list, description="Node IDs that must complete before this step.")),
            arguments=(Dict[str, Any], Field(default_factory=dict, description="Key-value arguments required by the target skill."))
        )

        DynamicPlanArtifact = create_model(
            "DynamicPlanArtifact",
            plan_id=(str, Field(description="Unique identifier for this specific execution plan.")),
            nodes=(List[DynamicDAGNode], Field(description="The directed acyclic graph of execution steps."))
        )

        # Inject system topology & tool catalog into prompt
        dynamic_system_prompt = (
            f"{self.base_system_prompt}\n\n"
            f"AVAILABLE TARGET AGENTS:\n{json.dumps(system_topology, indent=2)}\n"
            f"VALID TARGET AGENT IDs: [{available_agents_str}]\n\n"
            f"AVAILABLE SYSTEM DELEGATION NODES:\n{json.dumps(framed_catalog, indent=2)}\n\n"
            f"AUTHORIZED DELEGATION NODE NAMES: [{delegatable_tools_str}]"
        )

        # Ingest and serialize constraints
        if coordinator_constraints:
            if isinstance(coordinator_constraints, BaseModel):
                constraints_str = coordinator_constraints.model_dump_json()
            else:
                constraints_str = json.dumps(coordinator_constraints)
            dynamic_system_prompt += f"\nCRITICAL REVISION CONSTRAINTS: {constraints_str}"

        if self._cot_callback:
            self._cot_callback(message="Generating DAG based on topology and tools.", thought_type="ANALYSIS")

        # LLM Output Generation Target
        schema_definition = json.dumps(DynamicPlanArtifact.model_json_schema(), indent=2)
        example_tool = delegatable_tool_names[0] if delegatable_tool_names else "sk_engineer_run_script"
        example_agent = available_agents[0] if available_agents else "engineer"

        clean_schema = (
            {k: v for k, v in schema_definition.items() if k != "$defs"}
            if isinstance(schema_definition, dict)
            else schema_definition
        )

        dynamic_system_prompt += (
            f"\n\nSTRICT TOOL SELECTION RULES:\n"
            f"1. You MUST select 'target_skill' EXCLUSIVELY from this exact allowed set: [{delegatable_tools_str}].\n"
            f"2. Selection of ANY tool string outside [{delegatable_tools_str}] is strictly illegal and will trigger systemic failure.\n"
            f"3. Every node MUST set 'target_agent' strictly to an agent ID from [{available_agents_str}].\n"
            f"4. You MUST include a 'user_query' or 'task' key inside the 'arguments' dictionary for every node to provide the downstream agent with its instruction.\n\n"
            f"Target Schema:\n{clean_schema}\n\n"
            f"EXPECTED OUTPUT STRUCTURE EXAMPLE:\n"
            f"{{\n"
            f'  "plan_id": "unique_plan_name",\n'
            f'  "nodes": [\n'
            f'    {{\n'
            f'      "node_id": "step_1",\n'
            f'      "target_agent": "{example_agent}",\n'
            f'      "target_skill": "{example_tool}",\n'
            f'      "dependencies": [],\n'
            f'      "arguments": {{"user_query": "Write and execute a Python script to display the current system time."}}\n'
            f'    }}\n'
            f'  ]\n'
            f"}}\n"
            f"Respond strictly with raw JSON matching the target schema."
        )

        raw_llm_output = {}

        if self._cot_callback:
            self._cot_callback(message="Executing LLM inference for DAG planning.", thought_type="INFERENCE")

        try:
            from litellm import completion
            import os

            model = os.getenv("CHARON_HEAVY_MODEL", "llama3.1")
            api_base = os.getenv("OLLAMA_HOST", "http://localhost:11434")

            # Pass the dynamically generated schema directly to Ollama for GBNF sampling
            response = completion(
                model=f"ollama/{model}",
                api_base=api_base,
                messages=[
                    {"role": "system", "content": dynamic_system_prompt},
                    {"role": "user", "content": safe_request}
                ],
                format=DynamicPlanArtifact.model_json_schema()
            )

            raw_content = response.choices[0].message.content
            raw_llm_output = json.loads(raw_content)
            logger.info(f"[{self.agent_id}] LLM Inference successful. Passing to schema validator...")

        except json.JSONDecodeError as e:
            logger.error(f"[{self.agent_id}] LLM returned malformed JSON: {str(e)}")
            raw_llm_output = {}

        except Exception as e:
            logger.error(f"[{self.agent_id}] LLM Inference failed: {str(e)}")
            raw_llm_output = {}

        # Validation Execution
        try:
            valid_artifact = self.artifact_schema(**raw_llm_output)

            # LEVEL 1 HARD LOCK: System Tool Validation & Route Correction
            for node in valid_artifact.nodes:
                # 1. Ensure the DAG only routes to globally known system tools
                if node.target_skill not in delegatable_tool_names:
                    raise PermissionDeniedError(
                        f"Planner attempted to route task to unknown system skill: '{node.target_skill}'"
                    )

                # 2. Agent-Skill Alignment Procedure (Middleware Correction)
                expected_owner = skill_owner_map.get(node.target_skill)

                if expected_owner and node.target_agent != expected_owner:
                    logger.warning(
                        f"[{self.agent_id}] Routing mismatch detected. LLM assigned '{node.target_skill}' "
                        f"to unauthorized agent '{node.target_agent}'. "
                        f"Auto-correcting DAG node to strict owner: '{expected_owner}'."
                    )
                    # Forcibly overwrite the LLM's hallucinated agent with the DB-verified owner
                    node.target_agent = expected_owner

            logger.info(f"[{self.agent_id}] PlanArtifact successfully validated and routing secured.")

            if self._telemetry_callback:
                self._telemetry_callback(event_type="CONTRACT_COMPLETED", details={"artifact": "PlanArtifact"})

            return valid_artifact

        except (PermissionDeniedError, PermissionError) as e:
            logger.warning(f"[{self.agent_id}] CBAC / Zero-Trust Delegation Boundary Breach. Escalating to Gatekeeper: {e}")

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