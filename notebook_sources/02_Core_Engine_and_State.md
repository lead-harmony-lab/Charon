# Subsystem Domain Context: 02_Core_Engine_and_State
> **Generated:** 2026-08-11 06:46 UTC  
> **Charon Core Version:** v8.0  
> **Git Branch:** `Streamline-Dynamic-Routing` | **Commit:** `c416670`

---

## Target File: `charon/core/__init__.py`

```python
"""
charon/core/__init__.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Core orchestration, parsing, dispatching, and utility primitives.
"""

from charon.core.coordinator.blackboard import (
    EscalationLevel,
    TaskBlackboard,
    TaskStatus,
    UnfulfilledRequirement,
)
from charon.core.dispatcher import AgentDispatcher
from charon.core.session import SessionGateway
from charon.core.parser import IntentParser
from charon.core.prompts import (
    CHARON_ROUTING_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
)
from charon.core.utils import (
    clean_json_string,
    get_schema_json,
    normalize_agent,
)

__all__ = [
    # Stateful Reflection & Blackboard
    "TaskBlackboard",
    "TaskStatus",
    "EscalationLevel",
    # Main Orchestration Engine & Dispatcher
    "SessionGateway",
    "AgentDispatcher",
    "IntentParser",
    # Parsing & Schema Utilities
    "clean_json_string",
    "normalize_agent",
    "get_schema_json",
]
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/agent_runner.py`

```python
"""
charon/core/agent_runner.py
System Version: v0.3.4 | File Revision: 1.1.0

Module: Generic, Stateless Agent Execution Harness.
Instantiates agent personas dynamically via role abstraction, hydra-loads tool specs
from the SkillLibrarian, and executes plugin.py tool calls adhering strictly to the
Janitorial Working Anchor.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from charon.config.settings import DEFAULT_HEAVY_MODEL
from charon.core.skills.librarian import SkillLibrarian

logger = logging.getLogger("Charon.Core.AgentRunner")


class AgentExecutionError(RuntimeError):
    """Raised when an agent execution step or tool checkout encounters an unrecoverable fault."""
    pass


class AgentRunner:
    """
    Stateless execution engine for dynamic agents.
    Accepts a System Role name, resolves persona/tools via SkillLibrarian,
    and executes LLM tool loops without hardcoded identities or prompts.
    """

    def __init__(
        self,
        role_name: str = "system_generalist",
        librarian: Optional[SkillLibrarian] = None,
        max_tool_turns: int = 5,
    ) -> None:
        self.role_name: str = role_name
        self.librarian: SkillLibrarian = librarian or SkillLibrarian.get_instance()
        self.max_tool_turns: int = max_tool_turns

        # 1. Resolve agent_id dynamically via role abstraction
        self.agent_id: str = self.librarian.resolve_role(self.role_name)

        # 2. Fetch presentation display name for decoupled logging
        self.display_name: str = self.librarian.get_display_name_for_role(self.role_name)

        logger.info(
            f"[AGENT_RUNNER] Initialized runner for role '{self.role_name}' "
            f"(Resolved ID: '{self.agent_id}' | Display: '{self.display_name}')"
        )

    @property
    def system_prompt(self) -> str:
        """Database-Driven Prompting: Pulls system prompt dynamically strictly from SQLite."""
        prompt = self.librarian.get_system_prompt_for_role(self.role_name)
        if not prompt:
            logger.warning(
                f"[AGENT_RUNNER] No system prompt found in DB for role '{self.role_name}'."
            )
        return prompt

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Hydrates OpenAI/Ollama tool JSON specifications mapped to this agent in DB."""
        return self.librarian.get_agent_tool_schemas(self.agent_id)

    def execute_task(
        self,
        task_prompt: str,
        llm_client: Any,
        model_name: Optional[str] = None,
        blackboard_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes an agent task cycle:
        1. Formulates LLM context (System Prompt + Blackboard Context + Tools)
        2. Dispatches prompt to LLM
        3. Intercepts tool calls and executes matching plugin.py handlers
        4. Returns final response and telemetry settlement
        """
        active_model = model_name or DEFAULT_HEAVY_MODEL
        context = blackboard_context or {}
        tools = self.get_tool_schemas()
        sys_prompt = self.system_prompt

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": sys_prompt},
            {
                "role": "user",
                "content": f"Context: {json.dumps(context)}\n\nTask: {task_prompt}",
            },
        ]

        logger.info(
            f"[{self.display_name}] Executing task on model '{active_model}' with {len(tools)} loaded tools..."
        )

        turn_count = 0
        while turn_count < self.max_tool_turns:
            turn_count += 1

            # Dispatch turn to LLM Client (Expected interface: Ollama or OpenAI compatible client)
            try:
                response = llm_client.chat(
                    model=active_model,
                    messages=messages,
                    tools=tools if tools else None,
                )
            except Exception as e:
                logger.error(f"[{self.display_name}] LLM invocation failed: {e}")
                raise AgentExecutionError(f"LLM communication error: {e}")

            message = response.get("message", {})
            tool_calls = message.get("tool_calls", [])

            # Case A: LLM produced a final text answer (No tool calls)
            if not tool_calls:
                final_content = message.get("content", "")
                logger.info(f"[{self.display_name}] Task completed successfully.")
                return {
                    "status": "success",
                    "role_name": self.role_name,
                    "agent_id": self.agent_id,
                    "display_name": self.display_name,
                    "model_used": active_model,
                    "output": final_content,
                    "turns_taken": turn_count,
                }

            # Case B: LLM issued function tool calls
            messages.append(message)  # Append assistant tool intent turn

            for tool_call in tool_calls:
                function_info = tool_call.get("function", {})
                action_name = function_info.get("name")
                raw_args = function_info.get("arguments", {})

                params = (
                    json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                )

                logger.info(
                    f"[{self.display_name}] Intercepted tool call: '{action_name}'"
                )

                # Execute action via Skill Checkout
                tool_result = self._dispatch_skill_action(action_name, params)

                # Feed tool result back into message stream for LLM
                messages.append({
                    "role": "tool",
                    "name": action_name,
                    "content": json.dumps(tool_result),
                })

        raise AgentExecutionError(
            f"[{self.display_name}] Exceeded max tool execution turns ({self.max_tool_turns})."
        )

    def _dispatch_skill_action(
        self, action_name: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validates checkout permissions and invokes plugin.execute_action()."""
        handler = self.librarian.check_out_skill(action_name, self.agent_id)

        if not handler:
            error_msg = (
                f"Checkout failed: Role '{self.role_name}' ({self.agent_id}) "
                f"is not authorized or missing plugin file for action '{action_name}'."
            )
            logger.error(f"[{self.display_name}] {error_msg}")
            return {"status": "error", "message": error_msg}

        try:
            # Invoke plugin entrypoint
            if callable(handler):
                result = handler(self.agent_id, params)
            elif hasattr(handler, "execute"):
                result = handler.execute(params)
            else:
                raise TypeError(f"Skill handler for '{action_name}' is not callable.")

            return result if isinstance(result, dict) else {"status": "success", "result": result}

        except Exception as e:
            logger.error(
                f"[{self.display_name}] Execution exception in plugin action '{action_name}': {e}"
            )
            return {"status": "error", "message": str(e)}
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/concierge.py`

```python
"""
charon/core/concierge.py
System Version: v0.1.0 | File Revision: 1.3.1

Module: Pre-execution status & post-execution proactive concierge assistant for Charon.
Provides grounded pre-execution status acknowledgments and LLM-driven proactive follow-up proposals.
Inspects TaskBlackboard artifacts and history to prevent path hallucinations and generate rich technical proposals.
Leaves inter-agent routing and task orchestration to the Agent Dispatcher.
"""

import json
import logging
import re
from typing import Any, Dict, Optional, Set, Tuple, Union

import ollama
from charon.config import DEFAULT_CONCIERGE_MIN_CONFIDENCE

logger = logging.getLogger("Charon.Concierge")

EXIT_PHRASES: Set[str] = {
    "that will be all",
    "that'll be all",
    "thanks",
    "thank you",
    "done",
    "stop",
    "exit",
    "quit",
    "nothing else",
    "goodbye",
    "n/a",
    "no",
    "no thanks",
    "all good",
    "that is all",
    "that's all",
}

TRIVIAL_QUERY_PATTERNS = [
    re.compile(
        r"^(display|show|get|check|print)?\s*(the)?\s*(current)?\s*(system)?\s*(time|date|clock|uptime|whoami|hostname|pwd)\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"^(time|date|whoami|uptime|pwd|hostname)$", re.IGNORECASE),
]


CONCIERGE_INFERENCE_PROMPT = """
You are Charon's Proactive Concierge Engine (Continental style).
Your task is to analyze a completed user task, its execution result, and any produced blackboard artifacts to determine if a single, logical, high-value follow-up prompt should be suggested to the user.

STRICT RULES:
1. TONE & PHRASE: 'phrase' must be formal, polite, concise, and executive ("Shall I...", "Would you like me to...", "May I...").
2. ACTIONABLE SUGGESTED PROMPT: 'suggested_prompt' MUST be an explicit, high-intent natural language instruction matching the proposal 'phrase'. NEVER output raw shell commands (e.g., 'ls ~/Projects') or questions in 'suggested_prompt'.
3. DATASHEETS / PDF / TECHNICAL DOCUMENTS WORKFLOW:
   * When a datasheet or PDF file is fetched, indexed, or opened in a GUI viewer:
   * DO NOT suggest opening binary/PDF files in a text editor or re-launching the viewer.
   * DO suggest querying ChromaDB for specific technical parameters, pinouts, operating voltages, or feature summaries.
   * Example:
     {
       "phrase": "Would you like me to retrieve specific technical details, pinouts, or power specs from this datasheet?",
       "suggested_prompt": "What are the power requirements and pinouts for ESP32-S3-WROOM-1?",
       "confidence": 0.95
     }
4. TRIVIAL / INFORMATIONAL QUERIES: If the completed task was a simple informational lookup (e.g., checking system time, date, username, uptime) and executed cleanly without errors or anomalies, output EXACTLY: null
5. SCOPE PRESERVATION & GROUNDING: Maintain context scope. STRICTLY suggest follow-up actions grounded ONLY in the user query, blackboard artifacts, or result provided. NEVER invent nonexistent project paths or file paths that do not appear in the context.
6. NO PLACEHOLDERS: NEVER output bracketed placeholders, template strings (e.g., '{project_name}', '{port}'), or generic references like 'active_project' or 'your_username'.
7. NO REPETITION / NO LOOPS: NEVER suggest an action or command identical or equivalent to the USER QUERY that was just executed. If the task completed cleanly and no obvious next step is required, output EXACTLY: null
8. DISMISSAL / TERMINATION: If the USER QUERY expresses completion, satisfaction, or dismissal (e.g., "that will be all", "thanks", "done", "no"), output EXACTLY: null
9. CONFIDENCE SCORE: Estimate your certainty that the follow-up proposal is logically required and non-annoying on a scale from 0.00 to 1.00.
10. JSON ONLY: Output strictly valid JSON matching this schema:
   {
     "phrase": "Would you like me to retrieve specific technical details, pinouts, or power specs from this datasheet?",
     "suggested_prompt": "What are the power requirements and pinouts for ESP32-S3-WROOM-1?",
     "confidence": 0.95
   }
11. If no grounded follow-up action makes sense, output EXACTLY: null
12. Do NOT include markdown code blocks, explanations, or commentary.
"""


class ConciergeService:
    """Post-execution proactive assistant & pre-execution status generator for the Charon daemon."""

    def __init__(
        self,
        ollama_client: Optional[ollama.AsyncClient] = None,
        model_name: str = "llama3.1",
        min_confidence: float = DEFAULT_CONCIERGE_MIN_CONFIDENCE,
    ):
        try:
            self.client = ollama_client or ollama.AsyncClient()
        except Exception as client_err:
            logger.error(f"[CONCIERGE] Failed to initialize Ollama AsyncClient: {client_err}")
            self.client = None

        self.model_name = model_name
        self.min_confidence = min_confidence

    @staticmethod
    def _clean_agent_id(agent: Any) -> str:
        """Extracts normalized string representation of an agent identifier or enum."""
        return agent.value if hasattr(agent, "value") else str(agent)

    async def generate_acknowledgment(
        self,
        agent: str,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generates a grounded, Continental-style status acknowledgment before task execution."""
        params = parameters or {}

        # Resolve explicit target indicators
        target = (
            params.get("target_path")
            or params.get("path")
            or params.get("directory")
            or params.get("query")
            or params.get("command")
            or params.get("target_device")
        )

        clean_agent = self._clean_agent_id(agent)

        if target:
            clean_target = re.sub(r"^/home/[^/]+", "~", str(target))
            clean_action = action.replace("_", " ").title() if action else "Executing"
            return f"[{clean_agent}: {clean_action} on '{clean_target}']"

        clean_action = action.replace("_", " ").title() if action else "Processing task"
        return f"[{clean_agent}: Executing {clean_action}...]"

    def _validate_proposal_logic(
        self,
        proposal: Dict[str, Any],
        user_query: str,
        execution_result: str,
        blackboard_context: str = "",
    ) -> bool:
        """Confidence, Grounding, Placeholder, Scope Regression, and Anti-Looping Validation Guardrail."""
        if not proposal or not isinstance(proposal, dict):
            return False

        phrase = proposal.get("phrase", "")
        suggested = proposal.get("suggested_prompt", "")

        if not phrase or not suggested:
            return False

        # 0. Quantitative Confidence Check
        try:
            confidence = float(proposal.get("confidence", 0.0))
        except (ValueError, TypeError):
            confidence = 0.0

        if confidence < self.min_confidence:
            logger.warning(
                f"[CONCIERGE] Rejected low-confidence proposal ({confidence:.2f} < {self.min_confidence:.2f}): '{suggested}'"
            )
            return False

        combined = f"{phrase} {suggested}".lower()
        full_corpus = f"{user_query} {execution_result} {blackboard_context}".lower()

        # 1. Reject opening PDF / binary files in text editors
        if ".pdf" in full_corpus:
            if any(editor in combined for editor in ["text editor", "nano", "vim", "gedit", "open in editor"]):
                logger.warning(
                    f"[CONCIERGE] Rejected nonsensical text editor proposal for PDF file: '{suggested}'"
                )
                return False

        # 2. Reject unresolved placeholders or generic dynamic markers
        invalid_placeholders = [
            "{",
            "}",
            "active project",
            "yourusername",
            "example_dir",
            "some_project",
            "target_device",
        ]
        if any(ph in combined for ph in invalid_placeholders):
            logger.warning(
                f"[CONCIERGE] Rejected proposal containing template placeholder: '{suggested}'"
            )
            return False

        # 3. Anti-Looping Guardrail: Do not repeat what was just asked
        norm_query = re.sub(r"[\s\-_/~.]+", " ", user_query.lower()).strip()
        norm_suggested = re.sub(r"[\s\-_/~.]+", " ", suggested.lower()).strip()

        if norm_suggested and (
            norm_suggested == norm_query
            or norm_suggested in norm_query
            or norm_query in norm_suggested
        ):
            logger.warning(
                f"[CONCIERGE] Rejected redundant proposal matching executed query: '{suggested}'"
            )
            return False

        # 4. Scope Regression Guardrail: Prevent proposing parent path when operating in subpath
        if "/" in user_query:
            q_paths = re.findall(r"(?:~|/home/[^/]+)?/[a-zA-Z0-9_\-./]+", user_query)
            s_paths = re.findall(r"(?:~|/home/[^/]+)?/[a-zA-Z0-9_\-./]+", suggested)
            if q_paths and s_paths:
                q_clean = q_paths[0].rstrip("/").lower()
                s_clean = s_paths[0].rstrip("/").lower()
                if q_clean.startswith(s_clean) and len(s_clean) < len(q_clean):
                    logger.warning(
                        f"[CONCIERGE] Rejected scope regression: '{suggested}' is parent of '{q_clean}'"
                    )
                    return False

        # 5. Suppress directory inspection proposals if result explicitly states directory is empty
        result_lower = execution_result.lower()
        if any(kw in result_lower for kw in ["is currently empty", "no files found", "0 items"]):
            if any(kw in norm_suggested for kw in ["list", "directory", "inspect"]):
                logger.warning(
                    f"[CONCIERGE] Suppressed listing proposal for empty directory: '{suggested}'"
                )
                return False

        # 6. Strict Grounding Guardrail: Any path mentioned in suggested_prompt MUST exist in query, result, or blackboard
        suggested_paths = re.findall(
            r"(?:~|/home/[^/\s]+|/[a-zA-Z0-9_\-.]+)+/[a-zA-Z0-9_\-./]+", suggested
        )
        for p in suggested_paths:
            clean_p = p.rstrip("/").lower()
            base_p = clean_p.split("/")[-1]
            if clean_p not in full_corpus and base_p not in full_corpus:
                logger.warning(
                    f"[CONCIERGE] Rejected ungrounded path hallucination: '{p}' in proposal '{suggested}'"
                )
                return False

        return True

    def _extract_blackboard_context(self, blackboard: Any, fallback_query: str) -> Tuple[str, str, str]:
        """Extracts effective user query, artifacts string, and execution history string from Blackboard."""
        artifacts_str = ""
        history_str = ""
        effective_query = fallback_query or getattr(blackboard, "original_prompt", fallback_query)

        artifacts = getattr(blackboard, "artifacts", {})
        if isinstance(artifacts, dict) and artifacts:
            clean_artifacts = {
                k: v for k, v in artifacts.items() if k not in ("active_agent_profiles", "agent_instances")
            }
            try:
                artifacts_str = json.dumps(clean_artifacts, default=str, indent=2)
            except Exception:
                artifacts_str = str(clean_artifacts)

        history = getattr(blackboard, "execution_history", [])
        if isinstance(history, list) and history:
            history_lines = []
            for entry in history[-5:]:  # Summarize up to 5 recent execution steps
                if isinstance(entry, dict):
                    act = entry.get("action") or entry.get("agent", "Step")
                    acc = entry.get("accomplishments") or entry.get("summary", "")
                    st = entry.get("status", "completed")
                    history_lines.append(f"- Action: {act} | Status: {st} | Details: {acc}")
                else:
                    history_lines.append(f"- {str(entry)}")
            history_str = "\n".join(history_lines)

        return effective_query, artifacts_str, history_str

    async def infer_dynamic_next_step(
        self,
        user_query: str,
        executed_action: str,
        execution_result: str,
        blackboard: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Evaluates completed tasks using LLM dynamic inference and Blackboard context."""
        if not self.client:
            logger.warning("[CONCIERGE] Ollama client is unavailable. Skipping proposal generation.")
            return None

        logger.info(f"[CONCIERGE] Evaluating proactive proposal via Ollama ({self.model_name})...")

        artifacts_str, history_str = "", ""
        if blackboard:
            user_query, artifacts_str, history_str = self._extract_blackboard_context(blackboard, user_query)

        user_content_blocks = [f"USER QUERY: {user_query}", f"EXECUTED ACTION: {executed_action}"]
        if artifacts_str:
            user_content_blocks.append(f"PRODUCED ARTIFACTS / BLACKBOARD STATE:\n{artifacts_str}")
        if history_str:
            user_content_blocks.append(f"RECENT EXECUTION HISTORY:\n{history_str}")
        user_content_blocks.append(f"RESULT OUTPUT:\n{execution_result[:1500]}")

        user_content = "\n\n".join(user_content_blocks)
        blackboard_context = f"{artifacts_str} {history_str}"

        try:
            response = await self.client.generate(
                model=self.model_name,
                system=CONCIERGE_INFERENCE_PROMPT,
                prompt=user_content,
                options={"temperature": 0.1},
            )

            if isinstance(response, dict):
                raw_output = response.get("response", "").strip()
            else:
                raw_output = getattr(response, "response", str(response)).strip()

            if not raw_output or raw_output.lower() == "null":
                logger.info("[CONCIERGE] LLM returned null. No follow-up proposal suggested.")
                return None

            clean_json = re.sub(r"^```(?:json)?\s*", "", raw_output, flags=re.IGNORECASE)
            clean_json = re.sub(r"\s*```$", "", clean_json).strip()

            data = json.loads(clean_json)
            if isinstance(data, dict) and "phrase" in data and "suggested_prompt" in data:
                proposal = {
                    "id": "dynamic_llm_suggestion",
                    "phrase": str(data["phrase"]).strip(),
                    "suggested_prompt": str(data["suggested_prompt"]).strip(),
                    "confidence": float(data.get("confidence", 0.0)),
                }
                if self._validate_proposal_logic(
                    proposal=proposal,
                    user_query=user_query,
                    execution_result=execution_result,
                    blackboard_context=blackboard_context,
                ):
                    logger.info(
                        f"[CONCIERGE] Proposal accepted (confidence: {proposal['confidence']:.2f}): "
                        f"{proposal['phrase']} -> '{proposal['suggested_prompt']}'"
                    )
                    return proposal

        except Exception as e:
            logger.warning(f"[CONCIERGE] Dynamic suggestion inference failed: {e}")

        return None

    async def get_next_step(
        self,
        user_query: str = "",
        completed_action: str = "",
        execution_result: str = "",
        params: Optional[Dict[str, Any]] = None,
        blackboard: Optional[Any] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Primary entry point for post-execution concierge proposals."""
        params = params or {}
        blackboard = blackboard or params.get("blackboard") or kwargs.get("blackboard")

        if not user_query and "user_input" in params:
            user_query = str(params["user_input"])

        clean_query = user_query.strip().lower().rstrip(".!")

        # 0. Intercept dismissal or closing statements
        if clean_query in EXIT_PHRASES:
            logger.info(f"[CONCIERGE] Exit phrase detected ('{user_query}'). Suppressing proposal.")
            return None

        # 1. Intercept trivial read-only informational queries (time, date, whoami, uptime, etc.)
        if any(pattern.match(clean_query) for pattern in TRIVIAL_QUERY_PATTERNS):
            logger.info(f"[CONCIERGE] Trivial/informational query detected ('{user_query}'). Suppressing proposal.")
            return None

        return await self.infer_dynamic_next_step(
            user_query=user_query,
            executed_action=completed_action,
            execution_result=execution_result,
            blackboard=blackboard,
        )

    async def evaluate_next_step(
        self,
        action_or_query: str = "",
        params_or_result: Union[Dict[str, Any], str, None] = None,
        *args: Any,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Compatibility wrapper mapping evaluate_next_step calls to get_next_step."""
        user_query = kwargs.get(
            "user_query", kwargs.get("user_raw_input", kwargs.get("user_input", kwargs.get("query", "")))
        )
        completed_action = kwargs.get(
            "completed_action", kwargs.get("executed_action", kwargs.get("action", ""))
        )
        execution_result = kwargs.get(
            "execution_result", kwargs.get("result", kwargs.get("res", ""))
        )
        params = kwargs.get("params", kwargs.get("execution_parameters", None))
        blackboard = kwargs.get("blackboard")

        if not completed_action and action_or_query:
            if isinstance(params_or_result, dict):
                completed_action = action_or_query
                params = params_or_result
            elif isinstance(params_or_result, str):
                user_query = action_or_query
                execution_result = params_or_result
            else:
                completed_action = action_or_query

        if params is None and isinstance(params_or_result, dict):
            params = params_or_result

        if not blackboard and isinstance(params, dict):
            blackboard = params.get("blackboard")

        return await self.get_next_step(
            user_query=str(user_query),
            completed_action=str(completed_action),
            execution_result=str(execution_result),
            params=params or {},
            blackboard=blackboard,
        )


# Compatibility Alias
ConciergeEngine = ConciergeService
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/contracts.py`

```python
"""
charon/core/contracts.py
System Version: v0.2.0 | File Revision: 1.2.1

Module: Core Negotiation Schemas, Diagnostic Flashlight Models, & Role Contracts.
Provides Pydantic V2 schemas for manifest inspection, capability negotiation,
rich diagnostic gap reporting, skill blueprints, and execution output across Charon.
Updated with Pydantic V2 AliasChoices and full two-way property setters for legacy agent fields.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ExecutionStatus(str, Enum):
    """Status code returned by a role executor following a step negotiation execution."""

    SATISFIED = "SATISFIED"
    PARTIAL = "PARTIAL"
    INCAPABLE = "INCAPABLE"
    FAILED = "FAILED"


class GapType(str, Enum):
    """Taxonomy of capability gaps identified during negotiation or execution (The Flashlight)."""

    ACTION_UNSUPPORTED = "ACTION_UNSUPPORTED"
    MISSING_ARTIFACT = "MISSING_ARTIFACT"
    MISSING_SYSTEM_DEPENDENCY = "MISSING_SYSTEM_DEPENDENCY"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class DiagnosticGap(BaseModel):
    """Structured root-cause diagnostic explaining exactly why a role cannot complete a step."""

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    gap_type: GapType = Field(
        description="Categorical root-cause identifier for the execution barrier."
    )
    description: str = Field(
        description="Human/LLM readable detail of the missing capability or state."
    )
    missing_key_or_tool: Optional[str] = Field(
        default=None,
        description="Specific missing blackboard artifact key, binary executable, or skill action.",
    )
    suggested_remediation: str = Field(
        description="Actionable guidance for the Coordinator (e.g., fallback role or missing key step)."
    )


class SkillBlueprint(BaseModel):
    """Declarative specification generated by system engineers when ad-hoc solving a recurring task."""

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    suggested_skill_name: str = Field(
        description="PascalCase name suggested for the new permanent Skill class."
    )
    action_name: str = Field(
        description="Snake_case string identifier for the action capability."
    )
    target_role: str = Field(
        validation_alias=AliasChoices("target_role", "target_agent"),
        description="Target specialist role persona best suited to adopt this skill.",
    )
    description: str = Field(
        description="Summary of what the skill performs and when it should be invoked."
    )
    inputs_required: List[str] = Field(
        default_factory=list,
        description="Blackboard artifact keys required as prerequisites.",
    )
    outputs_produced: List[str] = Field(
        default_factory=list,
        description="Blackboard artifact keys produced upon successful execution.",
    )
    system_dependencies: List[str] = Field(
        default_factory=list,
        description="CLI tools or python packages required by the skill execution.",
    )
    adhoc_code_reference: Optional[str] = Field(
        default=None,
        description="File path or temp log ID where ad-hoc execution code was archived.",
    )

    @property
    def target_agent(self) -> str:
        """Legacy compatibility alias for target_role."""
        return self.target_role

    @target_agent.setter
    def target_agent(self, value: str) -> None:
        self.target_role = value


class ToolManifest(BaseModel):
    """Declarative capability contract exposed by roles during preplanning and discovery."""

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    role_name: str = Field(
        validation_alias=AliasChoices("role_name", "agent_name"),
        description="Unique string role identity of the specialist.",
    )
    supported_actions: List[str] = Field(
        default_factory=list,
        description="List of capability names or action aliases supported by the role.",
    )
    system_requirements: List[str] = Field(
        default_factory=list,
        description="Required system dependencies or executable binaries (e.g., ['gui', 'xdg-open']).",
    )
    consumed_artifacts: List[str] = Field(
        default_factory=list,
        description="Blackboard artifact keys required as input prerequisites.",
    )
    produced_artifacts: List[str] = Field(
        default_factory=list,
        description="Blackboard artifact keys guaranteed to be produced upon successful execution.",
    )
    description: str = Field(
        description="Human/LLM-readable summary of domain expertise and action scope."
    )

    @property
    def agent_name(self) -> str:
        """Legacy compatibility alias for role_name."""
        return self.role_name

    @agent_name.setter
    def agent_name(self, value: str) -> None:
        self.role_name = value


class CapabilityNegotiation(BaseModel):
    """Coordinator query payload sent to evaluate if a role can fulfill a plan step."""

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    step_id: str = Field(
        description="Unique step/requirement identifier on the blackboard queue."
    )
    target_action: str = Field(
        description="Capability or action name requested by the Coordinator."
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Bound step parameters and input artifact values.",
    )
    context_keys_available: List[str] = Field(
        default_factory=list,
        description="Artifact keys currently populated on the Shared TaskBlackboard.",
    )


class ContractResponse(BaseModel):
    """Standardized contract response returned by specialist roles back to the Coordinator."""

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    role_name: str = Field(
        validation_alias=AliasChoices("role_name", "agent_name"),
        description="Identity of the responding specialist role.",
    )
    status: ExecutionStatus = Field(
        description="Outcome status of the negotiation or execution turn."
    )
    accomplishments: List[str] = Field(
        default_factory=list,
        description="Summary of work or sub-tasks completed during execution.",
    )
    blackboard_artifacts_added: List[str] = Field(
        default_factory=list,
        description="Keys newly posted to the Shared TaskBlackboard store.",
    )
    unresolved_gaps: List[str] = Field(
        default_factory=list,
        description="Sub-tasks or missing prerequisites the role could NOT satisfy.",
    )
    diagnostics: Optional[DiagnosticGap] = Field(
        default=None,
        description="Flashlight diagnostic detailing specific root-cause if INCAPABLE or FAILED.",
    )
    skill_blueprint: Optional[SkillBlueprint] = Field(
        default=None,
        description="Optional skill forge blueprint emitted when ad-hoc problem solving occurs.",
    )
    suggested_next_role: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("suggested_next_role", "suggested_next_agent"),
        description="Optional role recommendation if status is INCAPABLE or PARTIAL.",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Detailed diagnostic message or exception string if partial/failed.",
    )

    @property
    def agent_name(self) -> str:
        """Legacy compatibility alias for role_name."""
        return self.role_name

    @agent_name.setter
    def agent_name(self, value: str) -> None:
        self.role_name = value

    @property
    def suggested_next_agent(self) -> Optional[str]:
        """Legacy compatibility alias for suggested_next_role."""
        return self.suggested_next_role

    @suggested_next_agent.setter
    def suggested_next_agent(self, value: Optional[str]) -> None:
        self.suggested_next_role = value
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/coordinator/__init__.py`

```python
"""
charon/core/coordinator/__init__.py
Package exports for Charon Coordinator module.
"""

from charon.core.coordinator.blackboard import (
    EscalationLevel,
    TaskBlackboard,
    TaskStatus,
    UnfulfilledRequirement,
)
from charon.core.coordinator.decomposer import RequirementDecomposer
from charon.core.coordinator.discovery import AgentDiscoveryManager
from charon.core.coordinator.engine import Coordinator
from charon.core.coordinator.escalation import EscalationManager
from charon.core.coordinator.profile import AgentProfile

__all__ = [
    "Coordinator",
    "TaskBlackboard",
    "TaskStatus",
    "UnfulfilledRequirement",
    "EscalationLevel",
    "AgentProfile",
    "AgentDiscoveryManager",
    "RequirementDecomposer",
    "EscalationManager",
]

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/coordinator/blackboard.py`

```python
"""
charon/core/coordinator/blackboard.py
System Version: v0.8.0 | File Revision: 8.0.0

Module: Core state blackboard and execution TaskBlackboard models.
Provides strongly-typed schemas for multi-step artifact propagation, unfulfilled task tracking,
contract reflection, state mutation tracking, execution history, and DB state hydration.
Strictly preserves canonical database identifiers across all state interactions.
"""

import json
import uuid
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Callable, Dict, List, Optional, Set

from pydantic import Field

from charon.core.contracts import ContractResponse, ExecutionStatus
from charon.core.skills.librarian import SkillLibrarian
from charon.intent.base import StrictBaseModel


class TaskStatus(str, Enum):
    """Lifecycle status of a TaskBlackboard."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    NEEDS_ESCALATION = "NEEDS_ESCALATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EscalationLevel(IntEnum):
    """The 4-Level Self-Healing Escalation Hierarchy."""

    L1_SPECIALIST = 1        # Domain specialist actions
    L2_OS_AUTOMATION = 2     # OS automation and shell operations
    L3_DIAGNOSTIC = 3        # Diagnostic planning & environment analysis
    L4_ENGINEER_FALLBACK = 4 # System engineer fallback & custom repair


class ThoughtType(str, Enum):
    """Categorizes the phase of internal role/coordinator reasoning."""

    ANALYSIS = "ANALYSIS"
    PLANNING = "PLANNING"
    EXECUTION = "EXECUTION"
    REFLECTION = "REFLECTION"
    ERROR = "ERROR"


class ThoughtRecord(StrictBaseModel):
    """Granular CoT reasoning step emitted by the Coordinator or Specialist Roles."""

    record_id: str = Field(
        default_factory=lambda: f"thg-{uuid.uuid4().hex[:6]}",
        description="Unique identifier for the reasoning record.",
    )
    task_id: str = Field(description="Associated blackboard task ID.")
    source_role: str = Field(description="Abstract role or module key emitting the thought.")
    thought_type: ThoughtType = Field(
        default=ThoughtType.ANALYSIS,
        description="Phase category of the reasoning step.",
    )
    message: str = Field(description="Internal CoT narrative payload.")
    context_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional telemetry payloads (e.g., partial tool inputs, query parameters).",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC timestamp of thought emission.",
    )


class UnfulfilledRequirement(StrictBaseModel):
    """Represents a discrete goal or action that has not yet been satisfied."""

    requirement_id: str = Field(
        default_factory=lambda: f"req-{uuid.uuid4().hex[:6]}",
        description="Unique identifier for the requirement.",
    )
    capability_required: str = Field(
        description="The capability required to fulfill this step."
    )
    target_artifact_key: Optional[str] = Field(
        default=None,
        description="Key in the blackboard artifacts dictionary required for this step.",
    )
    preferred_tool: Optional[str] = Field(
        default=None,
        description="Optional preferred tool/app requested by the user.",
    )
    escalation_level: EscalationLevel = Field(
        default=EscalationLevel.L1_SPECIALIST,
        description="Current escalation level assigned to resolve this requirement.",
    )
    assigned_role_override: Optional[str] = Field(
        default=None,
        description="Abstract system role assigned during escalation (e.g., 'system_engineer').",
    )
    assigned_agent_override: Optional[str] = Field(
        default=None,
        description="Resolved agent_id matching agent_registry FK constraint.",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted target parameters bound to this specific requirement.",
    )


class ExecutionStepRecord(StrictBaseModel):
    """Audit log entry representing a single role execution turn."""

    step_number: int = Field(description="1-based index of the step execution order.")
    role: str = Field(description="The specialist role or agent_id that executed the step.")
    action: str = Field(description="The specific domain action invoked.")
    status: str = Field(
        default="SUCCESS",
        description="Outcome status of the step.",
    )
    output_summary: str = Field(
        default="",
        description="Human-readable or LLM-friendly summary of the output generated.",
    )
    produced_artifacts: Dict[str, Any] = Field(
        default_factory=dict,
        description="New artifacts added to the blackboard during this step.",
    )
    unresolved_gaps: List[str] = Field(
        default_factory=list,
        description="Sub-task requirements that could not be completed during this turn.",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Detailed diagnostic error output if execution failed.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC timestamp of execution.",
    )


class TaskBlackboard(StrictBaseModel):
    """The shared state blackboard for Charon execution turns."""

    task_id: str = Field(
        default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}",
        description="Unique execution session identifier.",
    )
    original_prompt: str = Field(
        description="Unmodified prompt string supplied by the user."
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="Current operational state of the blackboard.",
    )
    current_escalation_level: EscalationLevel = Field(
        default=EscalationLevel.L1_SPECIALIST,
        description="Highest active escalation level reached during execution.",
    )

    artifacts: Dict[str, Any] = Field(
        default_factory=dict,
        description="Ground truth key-value store containing operational data.",
    )
    unfulfilled_requirements: List[UnfulfilledRequirement] = Field(
        default_factory=list,
        description="Queue of unsatisfied intents that the Coordinator must satisfy.",
    )
    active_gaps: List[str] = Field(
        default_factory=list,
        description="Accumulated sub-task gaps that require re-routing or escalation.",
    )
    execution_history: List[ExecutionStepRecord] = Field(
        default_factory=list,
        description="Ordered list of execution records for auditing and reflection.",
    )
    thought_stream: List[ThoughtRecord] = Field(
        default_factory=list,
        description="Live chronological CoT reasoning events emitted during execution.",
    )
    mutation_ledger: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Detailed audit log of state mutations.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="System runtime metadata.",
    )

    @property
    def available_artifact_keys(self) -> Set[str]:
        """Returns non-empty keys available in the current blackboard artifact store."""
        return {k for k, v in self.artifacts.items() if v is not None and v != ""}

    def get_role_display_name(self, role: str) -> str:
        """Resolves human-readable presentation label via SkillLibrarian accessors."""
        clean_role = str(getattr(role, "value", role)).strip() if role else ""
        if not clean_role:
            return "system_generalist"

        librarian = SkillLibrarian.get_instance()
        if hasattr(librarian, "get_display_name_for_role") and callable(
            librarian.get_display_name_for_role
        ):
            name = librarian.get_display_name_for_role(clean_role)
            if name:
                return name
        if hasattr(librarian, "get_display_name_for_agent") and callable(
            librarian.get_display_name_for_agent
        ):
            name = librarian.get_display_name_for_agent(clean_role)
            if name:
                return name
        return clean_role

    def emit_thought(
        self,
        source_role: str,
        message: str,
        thought_type: ThoughtType = ThoughtType.ANALYSIS,
        context_data: Optional[Dict[str, Any]] = None,
        bus_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> ThoughtRecord:
        """Emits a live CoT reasoning event to the blackboard and optional bus callback."""
        clean_role = (
            str(getattr(source_role, "value", source_role)).strip()
            if source_role
            else "system_generalist"
        )
        record = ThoughtRecord(
            task_id=self.task_id,
            source_role=clean_role,
            thought_type=thought_type,
            message=message,
            context_data=context_data or {},
        )
        self.thought_stream.append(record)

        if bus_callback and callable(bus_callback):
            try:
                bus_callback(record.model_dump())
            except Exception:
                pass

        return record

    def _safe_summary(self, value: Any, max_len: int = 250) -> str:
        """Safely summarizes ledger values to prevent memory bloat with large artifacts."""
        if value is None:
            return "None"
        try:
            val_str = str(value)
            if len(val_str) > max_len:
                return f"{val_str[:max_len]}... [Truncated {len(val_str) - max_len} chars]"
            return val_str
        except Exception:
            return f"<{type(value).__name__} Unserializable Object>"

    def set_artifact(self, key: str, value: Any, source_role: str = "system_generalist") -> None:
        """Stores a ground truth artifact on the blackboard and logs a truncated mutation."""
        clean_role = (
            str(getattr(source_role, "value", source_role)).strip()
            if source_role
            else "system_generalist"
        )
        previous_val = self.artifacts.get(key)
        self.artifacts[key] = value

        self.mutation_ledger.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "key": key,
            "previous_value": self._safe_summary(previous_val),
            "new_value": self._safe_summary(value),
            "source_role": clean_role,
        })

    def get_artifact(self, key: str, default: Any = None) -> Any:
        """Retrieves a ground truth artifact from the blackboard."""
        return self.artifacts.get(key, default)

    def has_artifact(self, key: str) -> bool:
        """Checks if a ground truth artifact exists and is non-empty."""
        val = self.artifacts.get(key)
        return val is not None and val != ""

    def log_gap(self, gap_description: str) -> None:
        """Logs an unresolved step gap for the Coordinator's reflection loop."""
        if gap_description and gap_description not in self.active_gaps:
            self.active_gaps.append(gap_description)

    def clear_gap(self, gap_description: str) -> None:
        """Removes a resolved gap from the active gaps list."""
        if gap_description in self.active_gaps:
            self.active_gaps.remove(gap_description)

    def record_step(
        self,
        role: Any = None,
        action: str = "",
        status: str = "SUCCESS",
        output_summary: str = "",
        produced_artifacts: Optional[Dict[str, Any]] = None,
        unresolved_gaps: Optional[List[str]] = None,
        error_message: Optional[str] = None,
        agent: Any = None,  # Alias for role
    ) -> ExecutionStepRecord:
        """Appends an execution turn to history and updates blackboard artifacts."""
        resolved_role = role if role is not None else agent
        clean_role = (
            str(getattr(resolved_role, "value", resolved_role)).strip()
            if resolved_role
            else "system_generalist"
        )

        produced = produced_artifacts or {}
        gaps = unresolved_gaps or []
        step_number = len(self.execution_history) + 1

        record = ExecutionStepRecord(
            step_number=step_number,
            role=clean_role,
            action=action,
            status=status,
            output_summary=output_summary,
            produced_artifacts=produced,
            unresolved_gaps=gaps,
            error_message=error_message,
        )
        self.execution_history.append(record)

        for gap in gaps:
            self.log_gap(gap)

        for k, v in produced.items():
            self.set_artifact(k, v, source_role=clean_role)

        return record

    def record_contract_response(
        self,
        response: ContractResponse,
        action: str,
        produced_artifacts_map: Optional[Dict[str, Any]] = None,
    ) -> ExecutionStepRecord:
        """Integrates a formal Pydantic ContractResponse directly into state history."""
        produced = produced_artifacts_map or {}
        summary = (
            " | ".join(response.accomplishments)
            if response.accomplishments
            else (response.reason or "")
        )

        resolved_role = getattr(
            response,
            "role_name",
            getattr(response, "agent_name", "system_generalist"),
        )

        is_success = response.status in (ExecutionStatus.SUCCESS, ExecutionStatus.SATISFIED)

        return self.record_step(
            role=resolved_role,
            action=action,
            status=response.status.value,
            output_summary=summary,
            produced_artifacts=produced,
            unresolved_gaps=response.unresolved_gaps,
            error_message=None if is_success else response.reason,
        )

    def pop_requirement(self, requirement_id: str) -> Optional[UnfulfilledRequirement]:
        """Removes and returns a fulfilled requirement from the queue."""
        for idx, req in enumerate(self.unfulfilled_requirements):
            if req.requirement_id == requirement_id:
                return self.unfulfilled_requirements.pop(idx)
        return None

    def escalate(self, reason: str) -> EscalationLevel:
        """Escalates the task level up to Level 4."""
        if self.current_escalation_level < EscalationLevel.L4_ENGINEER_FALLBACK:
            self.current_escalation_level = EscalationLevel(
                self.current_escalation_level.value + 1
            )
            self.status = TaskStatus.NEEDS_ESCALATION
        else:
            self.status = TaskStatus.FAILED

        self.log_gap(f"Escalated to Level {self.current_escalation_level.value}: {reason}")
        return self.current_escalation_level

    def mark_completed(self) -> None:
        """Marks the blackboard state as fully satisfied."""
        self.status = TaskStatus.COMPLETED
        self.unfulfilled_requirements.clear()
        self.active_gaps.clear()

    def to_task_state_record(self) -> Dict[str, Any]:
        """Serializes blackboard into SQLite `task_state` schema representation."""
        override_agent = None
        if self.unfulfilled_requirements:
            override_agent = self.unfulfilled_requirements[0].assigned_agent_override

        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "escalation_level": int(self.current_escalation_level),
            "assigned_agent_override": override_agent,
            "plan_json": json.dumps([req.model_dump() for req in self.unfulfilled_requirements]),
            "results_json": json.dumps({
                "artifacts": self.artifacts,
                "history": [rec.model_dump() for rec in self.execution_history],
                "active_gaps": self.active_gaps,
            }),
            "metadata_json": json.dumps(self.metadata),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/coordinator/decomposer.py`

```python
"""
charon/core/coordinator/decomposer.py
System Version: v0.8.0 | File Revision: 8.0.0

Module: Requirement Decomposition and Payload Parsing Engine.
Parses prompts and metadata into discrete blackboard requirements and seed artifacts.
Strictly enforces Database as SSOT across all SkillLibrarian resolutions.
Raises RuntimeError on unmapped roles or inactive capabilities.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel

from charon.core.coordinator.blackboard import (
    EscalationLevel,
    TaskBlackboard,
    UnfulfilledRequirement,
)
from charon.core.skills import SkillLibrarian

# Safe import for manifest lookup
try:
    from charon.intent.manifests import get_agent_manifest
except ImportError:
    get_agent_manifest = lambda agent_id: None

logger = logging.getLogger("charon.core.coordinator.decomposer")


class RequirementDecomposer:
    """Decomposes prompts into initial blackboard artifacts and unfulfilled requirements using SSOT skills."""

    def __init__(self, librarian: Optional[SkillLibrarian] = None):
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _resolve_agent_override(self, raw_override: Any) -> tuple[Optional[str], Optional[str]]:
        """Resolves raw role/agent inputs into canonical (agent_id, agent_id) tuples via direct DB lookup."""
        if not raw_override:
            return None, None

        clean_id = str(getattr(raw_override, "value", raw_override)).strip()
        if not clean_id:
            return None, None

        agent_id = None
        if hasattr(self.librarian, "resolve_agent_id") and callable(self.librarian.resolve_agent_id):
            agent_id = self.librarian.resolve_agent_id(clean_id)
        elif hasattr(self.librarian, "resolve_agent_id_for_role") and callable(
            self.librarian.resolve_agent_id_for_role
        ):
            agent_id = self.librarian.resolve_agent_id_for_role(clean_id)

        if not agent_id:
            raise RuntimeError(
                f"[DECOMPOSER FAULT] Identifier '{clean_id}' could not be resolved in DB via SkillLibrarian."
            )

        resolved_str = str(agent_id)
        return resolved_str, resolved_str

    def _resolve_agent_default_action(self, agent_or_role: str) -> str:
        """Dynamically resolves default interface action for an agent/role strictly via SkillLibrarian or manifest.

        Raises:
            RuntimeError: If default action contract is not explicitly defined in the database or manifest.
        """
        if not agent_or_role or not str(agent_or_role).strip():
            raise RuntimeError(
                "[DECOMPOSER FAULT] Cannot resolve default action: No agent or role identifier provided."
            )

        target_id = str(agent_or_role).strip()

        # 1. Query SkillLibrarian API strictly with exact identifier
        if hasattr(self.librarian, "get_agent_default_action") and callable(
            self.librarian.get_agent_default_action
        ):
            action = self.librarian.get_agent_default_action(target_id)
            if action:
                return str(action)

        # 2. Query Manifest directly
        try:
            manifest = get_agent_manifest(target_id)
            if manifest:
                default_act = (
                    manifest.get("default_action")
                    if isinstance(manifest, dict)
                    else getattr(manifest, "default_action", None)
                )
                if default_act:
                    return str(default_act)
        except Exception:
            pass

        # Strictly fail fast if not mapped in SSOT
        raise RuntimeError(
            f"[DECOMPOSER FAULT] Cannot resolve default action contract for identifier '{target_id}': "
            "No 'default_action' mapped in database state or manifest."
        )

    def get_action_capability(self, action_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves action metadata from the dynamic skill registry, filtering for ACTIVE status."""
        cap = self.librarian.get_action_details(action_name)
        if cap and cap.get("status", "ACTIVE") != "ACTIVE":
            logger.warning(
                f"[DECOMPOSER] Requested action '{action_name}' is not ACTIVE (status={cap.get('status')})."
            )
            return None
        return cap

    def find_matching_capabilities(self, consumed_artifacts: List[str]) -> List[Dict[str, Any]]:
        """Finds active skills whose consumed artifact prerequisites match the input requirements."""
        matching = []
        active_actions = self.librarian.list_available_actions()
        for action_name in active_actions:
            action_info = self.get_action_capability(action_name)
            if not action_info:
                continue
            reqs = action_info.get("consumed_artifacts", [])
            if reqs and set(reqs).issubset(set(consumed_artifacts)):
                matching.append(action_info)
        return matching

    def decompose(
        self,
        prompt: str,
        blackboard: TaskBlackboard,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Populates blackboard with seed artifacts and initial requirement stack."""
        metadata = metadata or {}

        # 1. MPN / Part Number Regex Extraction
        mpn_match = re.search(r"\b([A-Z0-9]+-[A-Z0-9_\-]+|[A-Z0-9]{5,})\b", prompt, re.IGNORECASE)
        if mpn_match:
            blackboard.set_artifact("target_part", mpn_match.group(1))

        blackboard.set_artifact("original_prompt", prompt)
        handled_by_payload = False

        # 2. Check Typed Agent/Role Payloads
        payload_obj = (
            metadata.get("payload")
            or metadata.get("agent_payload")
            or metadata.get("role_payload")
        )
        if payload_obj:
            handled_by_payload = self._process_typed_payload(payload_obj, blackboard)

        # 3. Process Metadata Routing & Intent Extraction
        if not handled_by_payload:
            intent_extraction = metadata.get("intent_extraction")
            routing_payload = metadata.get("routing_payload")
            routing_hint = metadata.get("routing_hint")
            raw_override = metadata.get("role_override") or metadata.get("agent_override")

            role_override, agent_override = self._resolve_agent_override(raw_override)

            if intent_extraction:
                action = getattr(intent_extraction, "action", None) or (
                    intent_extraction.get("action") if isinstance(intent_extraction, dict) else None
                )
                params = getattr(intent_extraction, "parameters", None) or (
                    intent_extraction.get("parameters", {})
                    if isinstance(intent_extraction, dict)
                    else {}
                )

                if action:
                    cap_info = self.get_action_capability(action)
                    if not cap_info:
                        raise RuntimeError(
                            f"[DECOMPOSER FAULT] Intent specified action '{action}', "
                            "but it is missing or inactive in SkillLibrarian database."
                        )

                    cap_name = cap_info.get("capability_name") or cap_info.get("action_name", action)
                    produced = cap_info.get("produced_artifacts", [])
                    esc_level = cap_info.get("escalation_level", EscalationLevel.L1_SPECIALIST)

                    blackboard.unfulfilled_requirements.append(
                        UnfulfilledRequirement(
                            capability_required=cap_name,
                            target_artifact_key=produced[0] if produced else None,
                            escalation_level=esc_level,
                            assigned_role_override=role_override,
                            assigned_agent_override=agent_override,
                            parameters=params or {},
                        )
                    )
                    handled_by_payload = True

            if not handled_by_payload and (routing_payload or routing_hint or raw_override):
                raw_agent = (
                    raw_override
                    or getattr(routing_payload, "role", None)
                    or getattr(routing_payload, "agent", None)
                    or (routing_hint.get("role") if isinstance(routing_hint, dict) else None)
                    or (routing_hint.get("agent") if isinstance(routing_hint, dict) else None)
                    or (routing_hint.get("target_role") if isinstance(routing_hint, dict) else None)
                    or (routing_hint.get("target_agent") if isinstance(routing_hint, dict) else None)
                )

                role_str, agent_id_str = self._resolve_agent_override(raw_agent)

                if role_str:
                    try:
                        manifest = get_agent_manifest(role_str)
                    except Exception:
                        manifest = None

                    hinted_action = (
                        routing_hint.get("capability") or routing_hint.get("action")
                        if isinstance(routing_hint, dict)
                        else None
                    )

                    manifest_default = (
                        manifest.get("default_action")
                        if isinstance(manifest, dict)
                        else getattr(manifest, "default_action", None)
                    ) if manifest else None

                    cap_name = hinted_action or manifest_default
                    cap_info = self.get_action_capability(cap_name) if cap_name else None

                    if not cap_info:
                        agent_actions = self.librarian.list_available_actions(role_str)
                        if agent_actions:
                            cap_info = self.get_action_capability(agent_actions[0])
                        else:
                            fallback_action = self._resolve_agent_default_action(role_str)
                            cap_info = self.get_action_capability(fallback_action)

                    if not cap_info:
                        raise RuntimeError(
                            f"[DECOMPOSER FAULT] Could not resolve an active capability contract for target '{role_str}'."
                        )

                    hint_params = (
                        routing_hint.get("parameters", {})
                        if isinstance(routing_hint, dict)
                        else {}
                    )
                    cap_name_val = cap_info.get("capability_name") or cap_info.get("action_name")
                    produced = cap_info.get("produced_artifacts", [])
                    esc_level = cap_info.get("escalation_level", EscalationLevel.L1_SPECIALIST)

                    blackboard.unfulfilled_requirements.append(
                        UnfulfilledRequirement(
                            capability_required=cap_name_val,
                            target_artifact_key=produced[0] if produced else None,
                            escalation_level=esc_level,
                            assigned_role_override=role_str,
                            assigned_agent_override=agent_id_str,
                            parameters=hint_params,
                        )
                    )
                    handled_by_payload = True

        # 4. Default Fallback -> Direct system_generalist Lookup
        if not blackboard.unfulfilled_requirements:
            generalist_action = self._resolve_agent_default_action("system_generalist")
            cap_info = self.get_action_capability(generalist_action)

            if not cap_info:
                raise RuntimeError(
                    f"[DECOMPOSER FAULT] Default generalist action '{generalist_action}' "
                    "resolved for 'system_generalist' is missing or inactive in SkillLibrarian database."
                )

            cap_name = cap_info.get("capability_name") or cap_info.get("action_name", generalist_action)
            esc_level = cap_info.get("escalation_level", EscalationLevel.L1_SPECIALIST)
            produced = cap_info.get("produced_artifacts", [])

            blackboard.unfulfilled_requirements.append(
                UnfulfilledRequirement(
                    capability_required=cap_name,
                    target_artifact_key=produced[0] if produced else "response_text",
                    escalation_level=esc_level,
                    parameters={"prompt": prompt},
                )
            )

    def _process_typed_payload(
        self, payload: Union[BaseModel, Dict[str, Any]], blackboard: TaskBlackboard
    ) -> bool:
        """Parses dynamic/typed agent payloads into blackboard requirements."""
        payload_dict = (
            payload.model_dump()
            if isinstance(payload, BaseModel)
            else (dict(payload) if isinstance(payload, dict) else {})
        )
        if not payload_dict:
            return False

        action = payload_dict.get("action")
        requires_approval = payload_dict.get("requires_approval", False)

        for key in ["mpn", "part_number", "query", "command", "source_file", "script_path", "project_directory", "url"]:
            val = payload_dict.get(key)
            if val:
                if key in ["mpn", "part_number"]:
                    blackboard.set_artifact("target_part", val)
                blackboard.set_artifact(key, val)

        if not action:
            return False

        cap_info = self.get_action_capability(action)
        if not cap_info:
            raise RuntimeError(
                f"[DECOMPOSER FAULT] Payload specified action '{action}', "
                "but capability is missing or inactive in SkillLibrarian database."
            )

        req_params = {k: v for k, v in payload_dict.items() if v is not None}
        req_params["requires_approval"] = requires_approval

        cap_name = cap_info.get("capability_name") or cap_info.get("action_name", action)
        produced = cap_info.get("produced_artifacts", [])
        esc_level = cap_info.get("escalation_level", EscalationLevel.L1_SPECIALIST)

        raw_override = (
            payload_dict.get("role_override")
            or payload_dict.get("agent_override")
            or payload_dict.get("assigned_role")
            or payload_dict.get("assigned_agent")
        )
        role_str, agent_id_str = self._resolve_agent_override(raw_override)

        blackboard.unfulfilled_requirements.append(
            UnfulfilledRequirement(
                capability_required=cap_name,
                target_artifact_key=produced[0] if produced else None,
                escalation_level=esc_level,
                assigned_role_override=role_str,
                assigned_agent_override=agent_id_str,
                parameters=req_params,
            )
        )
        return True
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/coordinator/discovery.py`

```python
"""
charon/core/coordinator/discovery.py
System Version: v0.8.0 | File Revision: 8.1.0

Module: Coordinator Agent & Role Discovery & Probing Manager.
Handles agent and role registration, candidate preplanning, live capability probing,
host binary availability verification, and dynamic profile building.
Enforces strict zero-fallback execution: raises fast RoleConfigurationError exceptions
if skill metadata or agent capabilities cannot be resolved via SkillLibrarian.
"""

import logging
import shutil
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from charon.agents.base import BaseAgent
from charon.core.coordinator.blackboard import TaskBlackboard, UnfulfilledRequirement
from charon.core.coordinator.profile import (
    AgentProfile,
    CapabilityContract,
    get_default_escalation_level,
)
from charon.core.skills.librarian import SkillLibrarian

# Safe import for manifest lookup
try:
    from charon.intent.manifests import get_agent_manifest
except ImportError:
    get_agent_manifest = lambda agent_id: None

logger = logging.getLogger("charon.core.coordinator.discovery")


class RoleConfigurationError(RuntimeError):
    """Raised when a required system role, agent capability, or action contract cannot be strictly resolved."""


class AgentDiscoveryManager:
    """Manages agent/role registration, health probing, and dynamic profile resolution without magic fallbacks."""

    def __init__(self, librarian: Optional[SkillLibrarian] = None) -> None:
        self.librarian = librarian or SkillLibrarian.get_instance()
        self.agents: Dict[str, BaseAgent] = {}
        self.active_profiles: Dict[str, AgentProfile] = {}

    def _resolve_agent_id(self, agent_or_role: Any) -> str:
        """Resolves a role name, enum, or identifier to a canonical agent_id via SkillLibrarian SSOT."""
        if not agent_or_role:
            return ""

        role_str = str(getattr(agent_or_role, "value", agent_or_role)).strip()
        if not role_str:
            return ""

        if hasattr(self.librarian, "resolve_agent_id_for_role") and callable(
            self.librarian.resolve_agent_id_for_role
        ):
            try:
                resolved = self.librarian.resolve_agent_id_for_role(role_str)
                if resolved:
                    return str(resolved).strip()
            except Exception as err:
                logger.debug(f"[Discovery] SkillLibrarian failed to resolve role '{role_str}': {err}")

        elif hasattr(self.librarian, "resolve_agent_id") and callable(
            self.librarian.resolve_agent_id
        ):
            try:
                resolved = self.librarian.resolve_agent_id(role_str)
                if resolved:
                    return str(resolved).strip()
            except Exception as err:
                logger.debug(f"[Discovery] SkillLibrarian failed to resolve agent ID for '{role_str}': {err}")

        return role_str

    def register_agent(self, agent_key: Any, agent_instance: BaseAgent) -> None:
        """Registers a live BaseAgent instance with the Coordinator discovery pool."""
        agent_str = self._resolve_agent_id(agent_key)
        if not agent_str:
            raise RoleConfigurationError("[Discovery] Cannot register agent instance with empty agent identifier.")

        self.agents[agent_str] = agent_instance
        logger.info(
            f"[Discovery] Registered live agent instance for '{agent_str}' ({getattr(agent_instance, 'name', 'unnamed')})"
        )

    def probe_agent(self, agent: Any, probe_type: str = "full") -> Dict[str, Any]:
        """Probes a specific registered agent instance for runtime health and dynamic capabilities."""
        agent_str = self._resolve_agent_id(agent)
        agent_instance = self.agents.get(agent_str)

        if agent_instance and hasattr(agent_instance, "probe"):
            return agent_instance.probe(probe_type=probe_type)

        return {
            "healthy": False,
            "status": f"Agent instance for '{agent_str}' not registered in runtime pool.",
            "details": {},
        }

    def probe_all_agents(self, probe_type: str = "full") -> Dict[str, Dict[str, Any]]:
        """Probes all registered live agent instances."""
        return {
            agent_str: instance.probe(probe_type=probe_type)
            for agent_str, instance in self.agents.items()
            if hasattr(instance, "probe")
        }

    def preplan_and_build_profiles(
        self, prompt: str, metadata: Dict[str, Any]
    ) -> Dict[str, AgentProfile]:
        """Identifies target candidate agents and constructs dynamic AgentProfiles from the DB."""
        candidates = self._preplan_candidate_agents(prompt, metadata)
        self.active_profiles = self._build_agent_profiles(candidates)
        return self.active_profiles

    def _ensure_profile_active(self, agent: Any) -> Optional[AgentProfile]:
        """Ensures an AgentProfile exists in self.active_profiles, constructing it on-demand if missing."""
        agent_str = self._resolve_agent_id(agent)
        if not agent_str:
            return None

        if agent_str in self.active_profiles:
            return self.active_profiles[agent_str]

        logger.info(
            f"[Discovery] Performing on-demand hydration for unplanned agent/role '{agent_str}'."
        )
        built = self._build_agent_profiles([agent_str])
        if agent_str in built:
            self.active_profiles[agent_str] = built[agent_str]
            return self.active_profiles[agent_str]

        return None

    def _preplan_candidate_agents(
        self, prompt: str, metadata: Dict[str, Any]
    ) -> List[str]:
        """Dynamically queries SkillLibrarian for matching agents based on intent metadata."""
        candidates: Set[str] = set()

        # 1. Extract from metadata routing hints
        for source_key in ["intent_extraction", "routing_payload", "routing_hint"]:
            source = metadata.get(source_key)
            if not source:
                continue

            agent_val = (
                getattr(source, "role", None)
                or getattr(source, "agent", None)
                or (source.get("role") if isinstance(source, dict) else None)
                or (source.get("agent") if isinstance(source, dict) else None)
                or (source.get("target_role") if isinstance(source, dict) else None)
                or (source.get("target_agent") if isinstance(source, dict) else None)
            )
            if agent_val:
                resolved = self._resolve_agent_id(agent_val)
                if resolved:
                    candidates.add(resolved)

        # 2. Extract explicit overrides
        override = metadata.get("role_override") or metadata.get("agent_override")
        if override:
            resolved_override = self._resolve_agent_id(override)
            if resolved_override:
                candidates.add(resolved_override)

        # 3. Query DB Semantic Matcher
        if hasattr(self.librarian, "search_skills") and callable(self.librarian.search_skills):
            try:
                matched_results = self.librarian.search_skills(prompt)
                if matched_results:
                    matched_agents = [
                        self._resolve_agent_id(res.get("role_id") or res.get("agent_id"))
                        for res in matched_results
                        if isinstance(res, dict) and (res.get("role_id") or res.get("agent_id"))
                    ]
                    matched_agents = [a for a in matched_agents if a]
                    if matched_agents:
                        logger.info(
                            f"[Discovery] Fast-path DB hit for prompt: Matched agents -> {matched_agents}"
                        )
                        return matched_agents
            except Exception as err:
                logger.warning(f"[Discovery] Skill matching probe failed gracefully: {err}")

        # 4. Query registered DB roles
        if not candidates and hasattr(self.librarian, "list_registered_roles") and callable(
            self.librarian.list_registered_roles
        ):
            try:
                registered = self.librarian.list_registered_roles()
                if registered:
                    candidates.update(
                        resolved
                        for resolved in (self._resolve_agent_id(r) for r in registered)
                        if resolved
                    )
            except Exception as err:
                logger.warning(f"[Discovery] Error querying registered roles from DB: {err}")

        # 5. Check in-memory registered agents pool
        if not candidates:
            candidates.update(self.agents.keys())

        return list(candidates)

    def _details_to_contract(
        self, details: Dict[str, Any], fallback_agent: Any
    ) -> Optional[CapabilityContract]:
        """Converts raw librarian action details into a formal CapabilityContract object if ACTIVE."""
        if details.get("status", "ACTIVE") != "ACTIVE":
            logger.debug(f"[Discovery] Skipping inactive capability '{details.get('action_name')}'")
            return None

        raw_agent = (
            details.get("role")
            or details.get("agent")
            or details.get("primary_role_id")
            or details.get("primary_agent_id")
            or details.get("agent_id")
        )
        fallback_str = self._resolve_agent_id(fallback_agent)
        target_agent = self._resolve_agent_id(raw_agent) if raw_agent else fallback_str

        esc_level = details.get("escalation_level")
        if esc_level is None:
            esc_level = get_default_escalation_level()

        req_binaries = details.get("system_requirements") or details.get("required_binaries") or []
        cap_name = details.get("action_name") or details.get("capability_name") or details.get("skill_id", "")

        return CapabilityContract(
            capability_name=cap_name,
            agent=target_agent,
            description=details.get("description", ""),
            consumed_artifacts=details.get("consumed_artifacts", []),
            produced_artifacts=details.get("produced_artifacts", []),
            escalation_level=esc_level,
            required_binaries=req_binaries,
        )

    def _build_agent_profiles(
        self, candidate_agents: List[Any]
    ) -> Dict[str, AgentProfile]:
        """Builds AgentProfiles populated strictly with capabilities resolved via SkillLibrarian."""
        profiles: Dict[str, AgentProfile] = {}

        for agent in candidate_agents:
            agent_str = self._resolve_agent_id(agent)
            if not agent_str:
                continue

            try:
                manifest = get_agent_manifest(agent_str)
            except Exception:
                manifest = None

            if isinstance(manifest, dict):
                manifest_name = manifest.get("name", agent_str)
                default_action = manifest.get("default_action")
            else:
                manifest_name = getattr(manifest, "name", agent_str)
                default_action = getattr(manifest, "default_action", None)

            action_names: List[str] = []
            if hasattr(self.librarian, "list_available_actions") and callable(
                self.librarian.list_available_actions
            ):
                try:
                    action_names = self.librarian.list_available_actions(agent_str) or []
                except Exception as err:
                    logger.warning(f"[Discovery] DB Error listing actions for '{agent_str}': {err}")

            cap_dict: Dict[str, CapabilityContract] = {}
            for name in action_names:
                details = self.librarian.get_action_details(name)
                if details:
                    contract = self._details_to_contract(details, agent_str)
                    if contract:
                        cap_dict[contract.capability_name] = contract
                        if details.get("action_name"):
                            cap_dict[details["action_name"]] = contract
                        if details.get("skill_id"):
                            cap_dict[details["skill_id"]] = contract

            if default_action:
                default_details = self.librarian.get_action_details(default_action)
                if default_details:
                    default_contract = self._details_to_contract(default_details, agent_str)
                    if default_contract:
                        cap_dict[default_contract.capability_name] = default_contract
                        if default_details.get("action_name"):
                            cap_dict[default_details["action_name"]] = default_contract
                        if default_details.get("skill_id"):
                            cap_dict[default_details["skill_id"]] = default_contract

            is_healthy = True
            health_info: Dict[str, Any] = {"healthy": True, "status": "Operational"}
            agent_instance = self.agents.get(agent_str)

            if agent_instance and hasattr(agent_instance, "probe"):
                try:
                    probe_data = agent_instance.probe(probe_type="full")
                    health_info = probe_data.get("health", health_info)
                    is_healthy = bool(health_info.get("healthy", True))

                    probed_caps = probe_data.get("capabilities", {}).get("actions", {})
                    if isinstance(probed_caps, dict):
                        for cap_key in probed_caps.keys():
                            if cap_key not in cap_dict:
                                details = self.librarian.get_action_details(cap_key)
                                if details:
                                    contract = self._details_to_contract(details, agent_str)
                                    if contract:
                                        cap_dict[cap_key] = contract
                except Exception as e:
                    logger.error(f"[Discovery] Runtime probe faulted for '{agent_str}': {e}")
                    is_healthy = False
                    health_info = {"healthy": False, "status": f"Probe Exception: {e}"}

            verified_bins: Set[str] = set()
            missing_bins: Set[str] = set()

            for cap in cap_dict.values():
                for binary in cap.required_binaries:
                    if shutil.which(binary):
                        verified_bins.add(binary)
                    else:
                        missing_bins.add(binary)

            profiles[agent_str] = AgentProfile(
                agent=agent_str,
                name=manifest_name,
                manifest=manifest,
                capabilities=cap_dict,
                verified_binaries=verified_bins,
                missing_binaries=missing_bins,
                is_healthy=is_healthy,
                health_status=health_info,
            )

        return profiles

    def discover_equipped_agent(
        self, requirement: UnfulfilledRequirement, blackboard: TaskBlackboard
    ) -> Tuple[AgentProfile, CapabilityContract]:
        """
        Finds an active agent profile equipped to handle the given requirement.
        Strict Zero-Fallback Policy: Raises a RoleConfigurationError immediately if
        no equipped agent or valid skill data can be resolved through SkillLibrarian.
        """
        target_cap_name = requirement.capability_required
        available_artifacts = blackboard.available_artifact_keys

        target_details = self.librarian.get_action_details(target_cap_name)

        # 1. Direct role/agent override lookup
        override_agent = getattr(requirement, "assigned_role_override", None) or getattr(
            requirement, "assigned_agent_override", None
        )
        if override_agent:
            target_str = self._resolve_agent_id(override_agent)
            profile = self._ensure_profile_active(target_str)
            if profile:
                cap_contract = profile.capabilities.get(target_cap_name) or (
                    self._details_to_contract(target_details, target_str) if target_details else None
                )
                if cap_contract:
                    if target_cap_name not in profile.capabilities:
                        profile.capabilities[target_cap_name] = cap_contract

                    equip_res = profile.is_equipped(target_cap_name, available_artifacts)
                    equipped = equip_res[0] if isinstance(equip_res, tuple) else bool(equip_res)
                    if equipped:
                        return profile, cap_contract

        # 2. Direct action owner or mapped agent lookup via SkillLibrarian
        candidate_agents: List[str] = []
        if target_details:
            raw_owners = (
                target_details.get("agents")
                or target_details.get("roles")
                or [
                    target_details.get(k)
                    for k in ("role", "agent", "primary_role_id", "primary_agent_id", "agent_id")
                    if target_details.get(k)
                ]
            )
            if isinstance(raw_owners, (str, bytes)):
                candidate_agents.append(str(raw_owners))
            elif isinstance(raw_owners, list):
                candidate_agents.extend([str(o) for o in raw_owners if o])

        for method_name in ("get_agents_for_action", "get_agents_for_skill", "resolve_agents_for_action"):
            if hasattr(self.librarian, method_name) and callable(getattr(self.librarian, method_name)):
                try:
                    res = getattr(self.librarian, method_name)(target_cap_name)
                    if res:
                        if isinstance(res, list):
                            candidate_agents.extend([str(x) for x in res if x])
                        elif isinstance(res, str):
                            candidate_agents.append(res)
                        break
                except Exception as err:
                    logger.debug(f"[Discovery] SkillLibrarian.{method_name} query failed: {err}")

        for c_agent in candidate_agents:
            c_str = self._resolve_agent_id(c_agent)
            if not c_str:
                continue
            profile = self._ensure_profile_active(c_str)
            if profile:
                contract = profile.capabilities.get(target_cap_name) or (
                    self._details_to_contract(target_details, c_str) if target_details else None
                )
                if contract:
                    if target_cap_name not in profile.capabilities:
                        profile.capabilities[target_cap_name] = contract

                    equip_res = profile.is_equipped(target_cap_name, available_artifacts)
                    equipped = equip_res[0] if isinstance(equip_res, tuple) else bool(equip_res)
                    if equipped:
                        return profile, contract

        # 3. Check active profiles currently in memory (including manifest default actions)
        for profile in self.active_profiles.values():
            contract = profile.capabilities.get(target_cap_name)
            if not contract and target_details:
                manifest_default = None
                if isinstance(profile.manifest, dict):
                    manifest_default = profile.manifest.get("default_action")
                elif profile.manifest:
                    manifest_default = getattr(profile.manifest, "default_action", None)

                if manifest_default and str(manifest_default).lower() == str(target_cap_name).lower():
                    contract = self._details_to_contract(target_details, profile.agent)
                    if contract:
                        profile.capabilities[target_cap_name] = contract

            if contract:
                equip_res = profile.is_equipped(target_cap_name, available_artifacts)
                equipped = equip_res[0] if isinstance(equip_res, tuple) else bool(equip_res)
                if equipped:
                    return profile, contract

        # 4. CAPABILITY GAP DETECTED -> Fail Fast
        gap_msg = f"Capability Gap: No registered agent is equipped with action '{target_cap_name}'."
        blackboard.log_gap(gap_msg)

        raise RoleConfigurationError(
            f"[FATAL DISCOVERY FAULT] Required capability '{target_cap_name}' cannot be resolved to an equipped, "
            f"active agent. Ensure the skill is mapped in SkillLibrarian and that mandatory artifacts are available."
        )
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/coordinator/engine.py`

```python
"""
charon/core/coordinator/engine.py
System Version: v0.8.0 | File Revision: 8.0.0

Module: Core Reflection Engine and Multi-Intent Coordinator Facade.
Orchestrates prompt decomposition, contract negotiations, dynamic agent discovery,
diagnostic gap dynamic re-routing, blueprint capturing, and stateful reflection loops
aligned with Revision 3 CBAC database schema & trigger guardrails.
Enforces canonical role & agent lookup via SkillLibrarian SSOT.
"""

import asyncio
import concurrent.futures
import inspect
import logging
import time
from typing import Any, Dict, Optional, Tuple, Union

from charon.agents.base import BaseAgent
from charon.core.contracts import (
    CapabilityNegotiation,
    ContractResponse,
    DiagnosticGap,
    ExecutionStatus,
    GapType,
    SkillBlueprint,
)
from charon.core.coordinator.blackboard import (
    TaskBlackboard,
    TaskStatus,
    UnfulfilledRequirement,
)
from charon.core.coordinator.decomposer import RequirementDecomposer
from charon.core.coordinator.discovery import AgentDiscoveryManager
from charon.core.coordinator.escalation import EscalationManager
from charon.core.coordinator.profile import (
    CapabilityContract,
    get_default_escalation_level,
)
from charon.core.skills import SkillLibrarian
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

logger = logging.getLogger("charon.core.coordinator")

MAX_LOOP_LIMIT = 25


def _resolve_agent_id(agent_or_role: Any) -> str:
    """Resolves a role name, enum, or identifier to a canonical agent_id via SkillLibrarian SSOT."""
    if not agent_or_role:
        return ""

    role_str = str(getattr(agent_or_role, "value", agent_or_role)).strip()
    if not role_str:
        return ""

    librarian = SkillLibrarian.get_instance()
    if hasattr(librarian, "resolve_agent_id_for_role") and callable(
        librarian.resolve_agent_id_for_role
    ):
        try:
            resolved = librarian.resolve_agent_id_for_role(role_str)
            if resolved:
                return str(resolved).strip()
        except Exception as err:
            logger.debug(f"[Engine] SkillLibrarian failed to resolve role '{role_str}': {err}")

    elif hasattr(librarian, "resolve_agent_id") and callable(librarian.resolve_agent_id):
        try:
            resolved = librarian.resolve_agent_id(role_str)
            if resolved:
                return str(resolved).strip()
        except Exception as err:
            logger.debug(f"[Engine] SkillLibrarian failed to resolve agent ID for '{role_str}': {err}")

    return role_str


def get_capability(
    capability_name: str, agent: Optional[Union[str, Any]] = None
) -> Optional[CapabilityContract]:
    """Dynamically resolves a CapabilityContract via SkillLibrarian, filtering for ACTIVE status."""
    librarian = SkillLibrarian.get_instance()
    details = librarian.get_action_details(capability_name)
    if not details:
        return None

    # Schema Compliance: Verify skill status is ACTIVE
    skill_status = details.get("status", "ACTIVE")
    if skill_status != "ACTIVE":
        logger.warning(
            f"[COORDINATOR] Skill '{capability_name}' requested but is currently in '{skill_status}' state."
        )
        return None

    # Schema Compliance: Resolve system roles -> active agent_id
    default_agent = (
        librarian.resolve_agent_id_for_role("system_fallback")
        if hasattr(librarian, "resolve_agent_id_for_role")
        else getattr(librarian, "get_system_fallback", lambda: "system_fallback")()
    )
    raw_agent = agent or details.get("primary_agent_id", default_agent)
    target_agent = _resolve_agent_id(raw_agent)

    return CapabilityContract(
        capability_name=details.get(
            "capability_name", details.get("action_name", capability_name)
        ),
        agent=target_agent,
        description=details.get("description", ""),
        consumed_artifacts=details.get("consumed_artifacts", []),
        produced_artifacts=details.get("produced_artifacts", []),
        escalation_level=details.get("escalation_level") or get_default_escalation_level(),
        required_binaries=details.get("system_requirements", details.get("required_binaries", [])),
    )


def _exec_sync_or_async(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Executes a function safely whether it is a synchronous method or an async coroutine function."""
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
    """The Reflection & Coordination Engine governing the Charon execution loop."""

    def __init__(self, agents: Optional[Dict[Union[str, Any], BaseAgent]] = None) -> None:
        self.discovery = AgentDiscoveryManager()
        self.decomposer = RequirementDecomposer()
        self.escalator = EscalationManager()

        if agents:
            for key, instance in agents.items():
                self.register_agent(key, instance)

    @property
    def agents(self) -> Dict[Union[str, Any], BaseAgent]:
        return self.discovery.agents

    @property
    def active_profiles(self) -> Dict[Union[str, Any], Any]:
        return self.discovery.active_profiles

    def register_agent(self, agent_key: Union[str, Any], agent_instance: BaseAgent) -> None:
        canonical_key = _resolve_agent_id(agent_key)
        self.discovery.register_agent(canonical_key, agent_instance)

    def probe_agent(self, agent: Union[str, Any], probe_type: str = "full") -> Dict[str, Any]:
        canonical_key = _resolve_agent_id(agent)
        return self.discovery.probe_agent(canonical_key, probe_type=probe_type)

    def probe_all_agents(self, probe_type: str = "full") -> Dict[str, Dict[str, Any]]:
        return self.discovery.probe_all_agents(probe_type=probe_type)

    def _get_diagnostic_engineer(self) -> str:
        """Resolves the diagnostic engineer agent ID via system_roles table lookup."""
        librarian = SkillLibrarian.get_instance()

        if hasattr(librarian, "get_diagnostic_agent") and callable(librarian.get_diagnostic_agent):
            res = librarian.get_diagnostic_agent()
            if res:
                return _resolve_agent_id(res)

        if hasattr(librarian, "resolve_agent_id_for_role") and callable(librarian.resolve_agent_id_for_role):
            res = librarian.resolve_agent_id_for_role("system_engineer")
            if res:
                return _resolve_agent_id(res)

        for agent_id, agent_obj in self.agents.items():
            if getattr(agent_obj, "is_active", True):
                return _resolve_agent_id(agent_id)

        return "system_engineer"

    def _get_agent_default_action(self, agent_id: str) -> str:
        """Dynamically resolves default interface action for an agent_id via SkillLibrarian.

        Raises:
            ValueError: If the target agent manifest does not define a default_action.
        """
        canonical_agent = _resolve_agent_id(agent_id)
        librarian = SkillLibrarian.get_instance()

        if hasattr(librarian, "get_agent_default_action") and callable(librarian.get_agent_default_action):
            action = librarian.get_agent_default_action(canonical_agent)
            if action:
                return str(action)

        manifest = (
            librarian.get_agent_manifest(canonical_agent)
            if hasattr(librarian, "get_agent_manifest")
            else None
        )
        if isinstance(manifest, dict) and manifest.get("default_action"):
            return str(manifest["default_action"])
        elif manifest and getattr(manifest, "default_action", None):
            return str(getattr(manifest, "default_action"))

        raise ValueError(
            f"[COORDINATOR ERROR] Cannot route task to agent '{canonical_agent}': "
            "Agent manifest is missing a required 'default_action' contract."
        )

    def initialize_blackboard(
        self,
        prompt: str,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskBlackboard:
        """Decomposes prompt, builds agent profiles, and initializes TaskBlackboard."""
        metadata = metadata or {}
        engine_task_id = task_id or metadata.get("task_id")

        kwargs: Dict[str, Any] = {
            "original_prompt": prompt,
            "status": TaskStatus.IN_PROGRESS,
            "metadata": metadata,
        }

        if engine_task_id:
            kwargs["task_id"] = engine_task_id

        blackboard = TaskBlackboard(**kwargs)

        profiles = self.discovery.preplan_and_build_profiles(prompt, metadata)
        blackboard.set_artifact("active_agent_profiles", [p.name for p in profiles.values()])

        self.decomposer.decompose(prompt, blackboard, metadata=metadata)
        return blackboard

    def select_next_execution_step(
        self, blackboard: TaskBlackboard
    ) -> Optional[Tuple[UnfulfilledRequirement, CapabilityContract, Dict[str, Any]]]:
        """Selects the next executable step using agent discovery and dependency resolution."""
        if not blackboard.unfulfilled_requirements:
            return None

        req = blackboard.unfulfilled_requirements[0]
        discovery_match = self.discovery.discover_equipped_agent(req, blackboard)

        if not discovery_match:
            capability = get_capability(req.capability_required)
            if capability:
                missing = [art for art in capability.consumed_artifacts if not blackboard.has_artifact(art)]
                if missing:
                    for idx, cand_req in enumerate(blackboard.unfulfilled_requirements[1:], start=1):
                        cand_cap = get_capability(cand_req.capability_required)
                        if cand_cap and any(art in cand_cap.produced_artifacts for art in missing):
                            promoted = blackboard.unfulfilled_requirements.pop(idx)
                            blackboard.unfulfilled_requirements.insert(0, promoted)
                            return self.select_next_execution_step(blackboard)

            self.escalator.escalate(
                blackboard, req, f"No equipped agent discovered for capability '{req.capability_required}'."
            )
            return None

        profile, capability = discovery_match
        bound_params = dict(req.parameters)
        for art_key in capability.consumed_artifacts:
            bound_params[art_key] = blackboard.get_artifact(art_key)

        if req.preferred_tool:
            bound_params["preferred_tool"] = req.preferred_tool

        return req, capability, bound_params

    def negotiate_contract(
        self, agent: Union[str, Any], requirement: UnfulfilledRequirement, blackboard: TaskBlackboard
    ) -> ContractResponse:
        """Conducts pre-turn contract negotiation with target agent and logs trace telemetry."""
        agent_key = _resolve_agent_id(agent)
        agent_instance = self.agents.get(agent_key) or self.agents.get(agent)
        agent_name = getattr(agent_instance, "name", agent_key)

        if agent_instance and hasattr(agent_instance, "is_active") and not agent_instance.is_active:
            engineer_agent_id = self._get_diagnostic_engineer()
            return ContractResponse(
                agent_name=agent_name,
                status=ExecutionStatus.INCAPABLE,
                reason=f"Agent '{agent_name}' is inactive (DB Guard Constraint).",
                diagnostics=DiagnosticGap(
                    gap_type=GapType.AGENT_INCAPABLE,
                    description=f"Target agent '{agent_name}' is deactivated in agent_registry.",
                    suggested_remediation=f"Re-route task to active engineer ({engineer_agent_id}).",
                ),
            )

        negotiation = CapabilityNegotiation(
            agent_name=agent_name,
            target_action=requirement.capability_required,
            parameters=requirement.parameters,
            context_keys_available=list(blackboard.available_artifact_keys),
        )

        if not agent_instance:
            engineer_agent_id = self._get_diagnostic_engineer()
            response = ContractResponse(
                agent_name=agent_name,
                status=ExecutionStatus.INCAPABLE,
                reason=f"Agent '{agent_name}' not registered.",
                diagnostics=DiagnosticGap(
                    gap_type=GapType.AGENT_INCAPABLE,
                    description=f"Target agent '{agent_name}' is not registered in runtime.",
                    suggested_remediation=f"Re-route task to fallback engineer ({engineer_agent_id}) or register target agent.",
                ),
            )
        else:
            if hasattr(agent_instance, "evaluate_capability"):
                response = _exec_sync_or_async(agent_instance.evaluate_capability, negotiation)
            else:
                response = ContractResponse(
                    agent_name=agent_instance.name,
                    status=ExecutionStatus.SATISFIED,
                    accomplishments=["Default capability negotiation validation passed."],
                )

        if response.status == ExecutionStatus.INCAPABLE and response.diagnostics:
            logger.info(
                f"[COORDINATOR] Negotiation Gap ({response.diagnostics.gap_type.value}): "
                f"{response.diagnostics.description}"
            )

        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.NEGOTIATION,
                agent_name=agent_name,
                action=requirement.capability_required,
                details={
                    "status": response.status.value,
                    "reason": response.reason,
                    "requirement_id": requirement.requirement_id,
                    "escalation_level": requirement.escalation_level.value,
                    "diagnostics": response.diagnostics.model_dump() if response.diagnostics else None,
                },
            )
        )
        return response

    def execute_contract_step(
        self,
        blackboard: TaskBlackboard,
        requirement: UnfulfilledRequirement,
        capability: CapabilityContract,
        parameters: Dict[str, Any],
    ) -> ContractResponse:
        """Executes negotiated contract step, evaluates DiagnosticGap payloads, logs blueprints,
        and triggers auto-rerouting or escalation as required.
        """
        override_agent = getattr(requirement, "assigned_agent_override", None)
        if override_agent:
            target_agent_key = _resolve_agent_id(override_agent)
        else:
            target_agent_key = _resolve_agent_id(capability.agent)

        agent_instance = self.agents.get(target_agent_key) or self.agents.get(override_agent or capability.agent)
        agent_name = getattr(agent_instance, "name", target_agent_key)

        if not agent_instance:
            response = ContractResponse(
                agent_name=agent_name,
                status=ExecutionStatus.FAILED,
                reason=f"No live agent instance registered for {target_agent_key}.",
                diagnostics=DiagnosticGap(
                    gap_type=GapType.AGENT_INCAPABLE,
                    description=f"Agent ID '{target_agent_key}' has no active instance registered.",
                ),
            )
            blackboard.record_contract_response(response, action=requirement.capability_required)
            self._handle_step_failure(blackboard, requirement, target_agent_key, response)
            return response

        negotiation = CapabilityNegotiation(
            agent_name=agent_name,
            target_action=requirement.capability_required,
            parameters=parameters,
            context_keys_available=list(blackboard.available_artifact_keys),
        )

        start_time = time.perf_counter()
        try:
            if hasattr(agent_instance, "process_contract"):
                response = _exec_sync_or_async(
                    agent_instance.process_contract,
                    negotiation=negotiation,
                    raw_prompt=blackboard.original_prompt,
                )
            else:
                res = _exec_sync_or_async(
                    agent_instance.execute,
                    action=requirement.capability_required,
                    parameters=parameters,
                    raw_prompt=blackboard.original_prompt,
                )
                response = ContractResponse(
                    agent_name=agent_name,
                    status=ExecutionStatus.SATISFIED,
                    accomplishments=[str(res)[:300] if res else "Executed successfully."],
                )
        except Exception as exc:
            engineer_agent_id = self._get_diagnostic_engineer()
            response = ContractResponse(
                agent_name=agent_name,
                status=ExecutionStatus.FAILED,
                reason=str(exc),
                diagnostics=DiagnosticGap(
                    gap_type=GapType.EXECUTION_ERROR,
                    description=f"Unhandled exception during contract execution: {str(exc)}",
                    suggested_remediation=f"Re-route to {engineer_agent_id} for ad-hoc repair.",
                ),
            )

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        produced_map = {}

        is_success = response.status in (ExecutionStatus.SATISFIED, ExecutionStatus.SUCCESS)

        if capability.produced_artifacts and is_success:
            for art_key in capability.produced_artifacts:
                if blackboard.has_artifact(art_key):
                    produced_map[art_key] = blackboard.get_artifact(art_key)

        if response.skill_blueprint:
            logger.info(
                f"[COORDINATOR] Captured SkillBlueprint '{response.skill_blueprint.suggested_skill_name}' "
                f"from {agent_name}."
            )
            blackboard.set_artifact(
                f"blueprint_{response.skill_blueprint.action_name}",
                response.skill_blueprint.model_dump(),
            )

        blackboard.record_contract_response(
            response=response,
            action=requirement.capability_required,
            produced_artifacts_map=produced_map,
        )

        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.EXECUTION,
                agent_name=agent_name,
                action=requirement.capability_required,
                duration_ms=duration_ms,
                details={
                    "status": response.status.value,
                    "produced_artifacts": list(produced_map.keys()),
                    "reason": response.reason,
                    "accomplishments": response.accomplishments,
                    "diagnostics": response.diagnostics.model_dump() if response.diagnostics else None,
                    "has_blueprint": response.skill_blueprint is not None,
                },
            )
        )

        if is_success:
            blackboard.pop_requirement(requirement.requirement_id)
        else:
            self._handle_step_failure(blackboard, requirement, target_agent_key, response)

        return response

    def _handle_step_failure(
        self,
        blackboard: TaskBlackboard,
        requirement: UnfulfilledRequirement,
        current_agent: Union[str, Any],
        response: ContractResponse,
    ) -> None:
        """Evaluates step failure and DiagnosticGap to perform dynamic re-routing or escalation."""
        agent_str = _resolve_agent_id(current_agent)
        diag = response.diagnostics
        engineer_agent_id = self._get_diagnostic_engineer()

        if diag and diag.gap_type == GapType.MISSING_TOOL:
            librarian = SkillLibrarian.get_instance()
            if hasattr(librarian, "record_skill_gap"):
                librarian.record_skill_gap(
                    action_name=requirement.capability_required,
                    requesting_agent=agent_str,
                    missing_prerequisites=requirement.parameters.get("missing_prerequisites", []),
                )

        if agent_str != engineer_agent_id and (
            not diag or diag.gap_type in [GapType.MISSING_TOOL, GapType.AGENT_INCAPABLE, GapType.EXECUTION_ERROR]
        ):
            logger.warning(
                f"[COORDINATOR] Auto-rerouting requirement '{requirement.requirement_id}' "
                f"from {agent_str} -> {engineer_agent_id} due to diagnostic gap: "
                f"{diag.description if diag else response.reason}"
            )

            if not hasattr(requirement, "parameters") or requirement.parameters is None:
                requirement.parameters = {}
            requirement.parameters["failed_action"] = requirement.capability_required
            requirement.parameters["failure_reason"] = diag.description if diag else response.reason
            requirement.capability_required = self._get_agent_default_action(engineer_agent_id)
            requirement.assigned_agent_override = engineer_agent_id
            return

        self.escalator.escalate(
            blackboard,
            requirement,
            response.reason or "Contract step execution failed.",
        )

    def run_turn(self, blackboard: TaskBlackboard) -> TaskBlackboard:
        """Executes full reflection loop, dispatching steps and publishing telemetry events."""
        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.SYSTEM,
                agent_name="Coordinator",
                action="run_turn_start",
                details={
                    "task_id": str(blackboard.task_id),
                    "pending_requirements": len(blackboard.unfulfilled_requirements),
                    "available_artifacts": list(blackboard.available_artifact_keys),
                },
            )
        )

        step_count = 0
        engineer_agent_id = self._get_diagnostic_engineer()

        while (
            blackboard.status in (TaskStatus.IN_PROGRESS, TaskStatus.NEEDS_ESCALATION)
            and blackboard.unfulfilled_requirements
            and step_count < MAX_LOOP_LIMIT
        ):
            if blackboard.status == TaskStatus.NEEDS_ESCALATION:
                blackboard.status = TaskStatus.IN_PROGRESS

            step_tuple = self.select_next_execution_step(blackboard)
            if not step_tuple:
                break

            req, cap, params = step_tuple
            step_count += 1

            override_agent = getattr(req, "assigned_agent_override", None)
            if override_agent:
                target_agent = override_agent
            else:
                target_agent = cap.agent

            negotiation_resp = self.negotiate_contract(target_agent, req, blackboard)
            if negotiation_resp.status == ExecutionStatus.INCAPABLE:
                target_str = _resolve_agent_id(target_agent)
                if target_str != engineer_agent_id:
                    logger.warning(
                        f"[COORDINATOR] Agent {target_str} incapable during negotiation. "
                        f"Overriding requirement target to {engineer_agent_id}."
                    )

                    if not hasattr(req, "parameters") or req.parameters is None:
                        req.parameters = {}
                    req.parameters["failed_action"] = req.capability_required
                    req.parameters["failure_reason"] = negotiation_resp.reason or "Agent incapable of action."
                    req.capability_required = self._get_agent_default_action(engineer_agent_id)
                    req.assigned_agent_override = engineer_agent_id
                    continue

                self.escalator.escalate(
                    blackboard, req, negotiation_resp.reason or "Agent incapable of action."
                )
                continue

            self.execute_contract_step(blackboard, req, cap, params)

        if not blackboard.unfulfilled_requirements and blackboard.status == TaskStatus.IN_PROGRESS:
            blackboard.status = TaskStatus.COMPLETED

        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.SYSTEM,
                agent_name="Coordinator",
                action="run_turn_complete",
                details={
                    "task_id": str(blackboard.task_id),
                    "final_status": blackboard.status.value,
                    "total_steps_executed": step_count,
                    "remaining_requirements": len(blackboard.unfulfilled_requirements),
                },
            )
        )

        return blackboard
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/coordinator/escalation.py`

```python
"""
charon/core/coordinator/escalation.py
System Version: v0.8.0 | File Revision: 8.0.0

Module: 4-Level Self-Healing Escalation Engine.
Manages automatic step recovery with live TelemetryBus trace emissions,
strict DB role-to-agent resolution via SkillLibrarian,
and fail-fast assertions when system roles or default agents are unassigned.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from charon.core.coordinator.blackboard import (
    EscalationLevel,
    TaskBlackboard,
    TaskStatus,
    UnfulfilledRequirement,
)
from charon.core.skills.librarian import SkillLibrarian
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

logger = logging.getLogger("charon.core.coordinator.escalation")


class RoleConfigurationError(RuntimeError):
    """Raised when a required system role or default agent is not assigned in SkillLibrarian state."""


class EscalationManager:
    """Manages system failure escalations and updates task blackboards with fail-fast assertions."""

    def __init__(self, librarian: Optional[SkillLibrarian] = None) -> None:
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _resolve_agent_target(
        self, details: Dict[str, Any], default_system_role: str
    ) -> Tuple[str, str]:
        """Resolves (role_name, agent_id) from action details or system_roles lookup via SkillLibrarian.

        Strictly relies on DB resolution without string mutation or synthetic fallbacks.
        Fails fast if the role or agent cannot be resolved from database state.
        """
        raw_role = (
            details.get("primary_role_id")
            or details.get("role")
            or default_system_role
        )
        if not raw_role:
            raise RoleConfigurationError(
                "[FATAL ESCALATION FAULT] No valid role identifier provided or resolved from action details."
            )

        role_name = str(getattr(raw_role, "value", raw_role)).strip()

        raw_agent = details.get("primary_agent_id") or details.get("agent")
        agent_id = str(raw_agent).strip() if raw_agent else None

        # Resolve agent_id via librarian if not directly supplied by action details
        if not agent_id:
            if hasattr(self.librarian, "resolve_agent_id_for_role") and callable(
                self.librarian.resolve_agent_id_for_role
            ):
                agent_id = self.librarian.resolve_agent_id_for_role(role_name)
            elif hasattr(self.librarian, "resolve_agent_id") and callable(
                self.librarian.resolve_agent_id
            ):
                agent_id = self.librarian.resolve_agent_id(role_name)

        # Fail-fast assertion: synthetic string fallbacks (e.g., agent_id = role_name) are prohibited
        if not agent_id:
            raise RoleConfigurationError(
                f"[FATAL ESCALATION FAULT] Required system role '{role_name}' "
                f"is not mapped to an active agent in SkillLibrarian state."
            )

        return role_name, str(agent_id)

    def escalate(
        self,
        blackboard: TaskBlackboard,
        requirement: UnfulfilledRequirement,
        failure_reason: str,
    ) -> None:
        """Triggers the 4-Level Self-Healing Escalation Pathway and emits telemetry events."""
        current_level = requirement.escalation_level
        failed_cap_name = requirement.capability_required

        # Preserve root failed capability on blackboard prior to rewriting requirement
        if not blackboard.has_artifact("failed_capability"):
            blackboard.set_artifact("failed_capability", failed_cap_name)

        logger.warning(
            f"[Escalation] Escalating requirement '{failed_cap_name}' "
            f"from Level {getattr(current_level, 'value', current_level)} "
            f"(Reason: {failure_reason})"
        )

        if current_level == EscalationLevel.L1_SPECIALIST:
            action_name = "execute_system_command"
            l2_details = self.librarian.get_action_details(action_name) or {}
            new_level = EscalationLevel.L2_OS_AUTOMATION
            new_cap = l2_details.get("capability_name", l2_details.get("action_name", action_name))

            role_name, agent_id = self._resolve_agent_target(l2_details, "system_generalist")
            requirement.assigned_role_override = role_name
            requirement.assigned_agent_override = agent_id

        elif current_level == EscalationLevel.L2_OS_AUTOMATION:
            action_name = "diagnose_environment"
            l3_details = self.librarian.get_action_details(action_name) or {}
            new_level = EscalationLevel.L3_DIAGNOSTIC
            new_cap = l3_details.get("capability_name", l3_details.get("action_name", action_name))

            role_name, agent_id = self._resolve_agent_target(l3_details, "system_engineer")
            requirement.assigned_role_override = role_name
            requirement.assigned_agent_override = agent_id

        elif current_level == EscalationLevel.L3_DIAGNOSTIC:
            action_name = "synthesize_script_fallback"
            l4_details = self.librarian.get_action_details(action_name) or {}
            new_level = EscalationLevel.L4_ENGINEER_FALLBACK
            new_cap = l4_details.get("capability_name", l4_details.get("action_name", action_name))

            role_name, agent_id = self._resolve_agent_target(l4_details, "system_engineer")
            requirement.assigned_role_override = role_name
            requirement.assigned_agent_override = agent_id

        else:
            logger.critical(
                f"[Escalation] Task {blackboard.task_id} reached Level 4 Escalation failure. Terminal state."
            )
            blackboard.status = TaskStatus.FAILED
            blackboard.unfulfilled_requirements.clear()

            telemetry_bus.emit(
                TraceEvent(
                    event_type=TraceEventType.ESCALATION,
                    agent_name="Coordinator",
                    action=failed_cap_name,
                    details={
                        "task_id": str(blackboard.task_id),
                        "from_level": getattr(current_level, "value", current_level),
                        "to_level": "TERMINAL_FAILURE",
                        "reason": failure_reason,
                        "terminal": True,
                    },
                )
            )
            return

        requirement.escalation_level = new_level
        requirement.capability_required = new_cap
        blackboard.escalate(reason=failure_reason)

        telemetry_bus.emit(
            TraceEvent(
                event_type=TraceEventType.ESCALATION,
                agent_name="Coordinator",
                action=failed_cap_name,
                details={
                    "task_id": str(blackboard.task_id),
                    "from_level": getattr(current_level, "value", current_level),
                    "to_level": getattr(new_level, "value", new_level),
                    "new_capability": new_cap,
                    "reason": failure_reason,
                    "terminal": False,
                },
            )
        )
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/coordinator/profile.py`

```python
"""
charon/core/coordinator/profile.py
System Version: v0.8.0 | File Revision: 8.0.0

Module: Agent profile definition and capability mapping.
Defines CapabilityContract and AgentProfile integrated with dynamic SkillLibrarian SSOT.
Enforces database-first agent and role resolution, active skill status checks, and strict schema alignment.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from pydantic import BaseModel, Field

from charon.core.coordinator.blackboard import EscalationLevel
from charon.core.skills.librarian import SkillLibrarian

logger = logging.getLogger("charon.core.coordinator.profile")


def _resolve_agent_id(agent_or_role: Any, librarian: Optional[SkillLibrarian] = None) -> str:
    """Resolves a role name, enum, or identifier to a canonical agent_id via SkillLibrarian SSOT."""
    if not agent_or_role:
        return ""

    role_str = str(getattr(agent_or_role, "value", agent_or_role)).strip()
    if not role_str:
        return ""

    lib = librarian or SkillLibrarian.get_instance()
    if hasattr(lib, "resolve_agent_id_for_role") and callable(lib.resolve_agent_id_for_role):
        try:
            resolved = lib.resolve_agent_id_for_role(role_str)
            if resolved:
                return str(resolved).strip()
        except Exception as err:
            logger.debug(f"[Profile] SkillLibrarian failed to resolve role '{role_str}': {err}")

    elif hasattr(lib, "resolve_agent_id") and callable(lib.resolve_agent_id):
        try:
            resolved = lib.resolve_agent_id(role_str)
            if resolved:
                return str(resolved).strip()
        except Exception as err:
            logger.debug(f"[Profile] SkillLibrarian failed to resolve agent ID for '{role_str}': {err}")

    return role_str


def get_default_escalation_level() -> EscalationLevel:
    """Safely retrieves default escalation level attribute from EscalationLevel enum."""
    return getattr(EscalationLevel, "L1_SPECIALIST", list(EscalationLevel)[0])


class CapabilityContract(BaseModel):
    """Contract definition for an agent/role capability / action."""

    capability_name: str
    agent: str
    description: str = ""
    consumed_artifacts: List[str] = Field(default_factory=list)
    produced_artifacts: List[str] = Field(default_factory=list)
    escalation_level: Any = Field(default_factory=get_default_escalation_level)
    required_binaries: List[str] = Field(default_factory=list)

    @property
    def role(self) -> str:
        """Alias property for agent identification for role-based system callers."""
        return self.agent


class AgentProfile:
    """Represents an agent's registered capabilities and operational metadata."""

    def __init__(
        self,
        agent: Union[str, Any],
        name: str = "",
        manifest: Any = None,
        capabilities: Optional[Dict[str, CapabilityContract]] = None,
        verified_binaries: Optional[Set[str]] = None,
        missing_binaries: Optional[Set[str]] = None,
        is_healthy: bool = True,
        health_status: Optional[Dict[str, Any]] = None,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.librarian = librarian or SkillLibrarian.get_instance()
        self.agent = agent
        agent_str = _resolve_agent_id(agent, self.librarian)

        display_name = name
        if not display_name:
            if hasattr(self.librarian, "get_display_name_for_agent") and callable(
                self.librarian.get_display_name_for_agent
            ):
                display_name = self.librarian.get_display_name_for_agent(agent_str)
            elif hasattr(self.librarian, "get_display_name_for_role") and callable(
                self.librarian.get_display_name_for_role
            ):
                display_name = self.librarian.get_display_name_for_role(agent_str)

        self.name = display_name or agent_str
        self.manifest = manifest
        self._capabilities = capabilities or {}
        self.verified_binaries = verified_binaries or set()
        self.missing_binaries = missing_binaries or set()
        self.is_healthy = is_healthy
        self.health_status = health_status or {"healthy": True, "status": "Operational"}

    @property
    def agent_id(self) -> str:
        """Returns the canonical string representation of the agent ID resolved from DB."""
        return _resolve_agent_id(self.agent, self.librarian)

    @property
    def role_id(self) -> str:
        """Alias property for agent_id to support role abstraction."""
        return self.agent_id

    @property
    def role(self) -> Any:
        """Alias property for agent object to support role abstraction."""
        return self.agent

    def _build_contract(self, name: str, details: Dict[str, Any]) -> Optional[CapabilityContract]:
        """Constructs a CapabilityContract instance from librarian action details if ACTIVE."""
        if details.get("status", "ACTIVE") != "ACTIVE":
            logger.debug(f"[Profile] Skipping inactive capability '{name}' (status: {details.get('status')})")
            return None

        target_agent = (
            details.get("agent")
            or details.get("role")
            or details.get("primary_agent_id")
            or details.get("primary_role_id")
            or self.agent_id
        )
        target_agent_str = _resolve_agent_id(target_agent, self.librarian)

        req_binaries = details.get("system_requirements") or details.get("required_binaries") or []

        return CapabilityContract(
            capability_name=details.get(
                "capability_name", details.get("action_name", name)
            ),
            agent=target_agent_str,
            description=details.get("description", ""),
            consumed_artifacts=details.get("consumed_artifacts", []),
            produced_artifacts=details.get("produced_artifacts", []),
            escalation_level=details.get(
                "escalation_level", get_default_escalation_level()
            ),
            required_binaries=req_binaries,
        )

    @property
    def capabilities(self) -> Dict[str, CapabilityContract]:
        """Returns registered capabilities dict, lazily populated via SkillLibrarian if empty."""
        if not self._capabilities and hasattr(self.librarian, "list_available_actions"):
            action_names = self.librarian.list_available_actions(self.agent_id) or []
            for name in action_names:
                details = self.librarian.get_action_details(name)
                if details:
                    contract = self._build_contract(name, details)
                    if contract:
                        self._capabilities[name] = contract
        return self._capabilities

    def get_capability(self, capability_name: str) -> Optional[CapabilityContract]:
        """Finds a specific capability contract by name."""
        if capability_name in self.capabilities:
            return self.capabilities[capability_name]

        details = self.librarian.get_action_details(capability_name)
        if details:
            contract = self._build_contract(capability_name, details)
            if contract:
                self._capabilities[capability_name] = contract
                return contract
        return None

    def is_equipped(
        self, capability_name: str, available_artifacts: List[str]
    ) -> Tuple[bool, List[str]]:
        """Checks if the profile has required binaries and artifacts available."""
        cap = self.get_capability(capability_name)
        if not cap:
            return False, [f"Missing capability contract: {capability_name}"]

        missing_reqs = []
        for artifact in cap.consumed_artifacts:
            if artifact not in available_artifacts:
                missing_reqs.append(f"Missing artifact: {artifact}")

        for binary in cap.required_binaries:
            if binary in self.missing_binaries:
                missing_reqs.append(f"Missing system binary: {binary}")

        return len(missing_reqs) == 0, missing_reqs
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/dispatcher/__init__.py`

```python
"""
charon/core/dispatcher/__init__.py
System Version: v0.1.0 | Package Revision: 3.2.1

Package entrypoint for specialist agent dispatching.
Exposes the core AgentDispatcher class lazily to prevent circular import loops.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from charon.core.dispatcher.dispatcher import AgentDispatcher

__all__ = ["AgentDispatcher"]


def __getattr__(name: str) -> Any:
    """Lazy-load AgentDispatcher on demand."""
    if name == "AgentDispatcher":
        from charon.core.dispatcher.dispatcher import AgentDispatcher

        return AgentDispatcher
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/dispatcher/artifacts.py`

```python
"""
charon/core/dispatcher/artifacts.py
System Version: v0.4.0 | File Revision: 1.3.0

Module: Artifact extraction utilities for inspecting step execution results.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.core.skills.librarian import SkillLibrarian


def extract_artifacts_from_result(
    action: str,
    result: Any,
    parameters: Dict[str, Any],
    capability_info: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[Path, str]] = None,
) -> Dict[str, Any]:
    """Inspects step output and automatically extracts produced ground truth artifacts."""
    produced: Dict[str, Any] = {}
    res_str = str(result)

    if capability_info is None:
        librarian = SkillLibrarian.get_instance(db_path)
        capability_info = librarian.get_action_details(action) or {}

    expected_artifacts = capability_info.get("produced_artifacts", [])

    # Handle stringified JSON arrays from SQLite Schema V2
    if isinstance(expected_artifacts, str):
        try:
            expected_artifacts = json.loads(expected_artifacts)
        except Exception:
            expected_artifacts = [expected_artifacts]

    if not isinstance(expected_artifacts, (list, tuple, set)):
        expected_artifacts = []

    # 1. Path extraction for file-producing capabilities (POSIX & Windows compatible)
    if not expected_artifacts or any(
        k in expected_artifacts for k in ("resolved_file_path", "file_path", "target_path")
    ):
        path_pattern = (
            r'(?:[a-zA-Z]:[/\\][^\s\'"\n]+|/[^\s\'"\n]+)'
            r'\.(?:pdf|png|jpg|jpeg|txt|csv|json|py|gcode|stl|step|igs|dxf|dwg|xlsx|md)'
        )
        path_match = re.search(path_pattern, res_str)
        if path_match:
            produced["resolved_file_path"] = path_match.group(0)
        elif "target_path" in parameters:
            produced["resolved_file_path"] = parameters["target_path"]
        elif "resolved_file_path" in parameters:
            produced["resolved_file_path"] = parameters["resolved_file_path"]

    # 2. Status / PID extraction for OS GUI launching
    if "launch_status" in expected_artifacts or action in (
        "launch_gui_viewer",
        "open_file",
        "execute_command",
    ):
        produced["launch_status"] = "LAUNCHED"
        produced["last_executed_command"] = parameters.get("command", "")

    # 3. Output text synthesis
    produced["response_text"] = res_str

    return produced
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/dispatcher/dispatcher.py`

```python
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
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/dispatcher/router.py`

```python
"""
charon/core/dispatcher/router.py
System Version: v0.4.0 | File Revision: 8.3.0

Core Routing Engine & Dynamic Agent Resolver backed by SQLite route_registry.
Enforces strict dynamic routing with zero hardcoded agent strings.
Instantiates data-driven RuntimeAgent instances hydrated dynamically via SkillLibrarian.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from charon.config.paths import STATE_DB_PATH
from charon.core.skills.librarian import SkillLibrarian
from charon.db.repositories import RouteRepository

logger = logging.getLogger("Charon.Router")


class RouteConfigError(Exception):
    """Raised when an illegal operation is attempted on an immutable route."""

    pass


class AgentRouter:
    """Manages dynamic agent lookup, route resolution, and RuntimeAgent instantiation via SkillLibrarian."""

    def __init__(self, db_path: Optional[Union[Path, str]] = None):
        target_path = Path(db_path) if db_path else STATE_DB_PATH

        if target_path.is_dir():
            logger.warning(
                f"[ROUTER] Directory path provided '{target_path}'. "
                f"Auto-correcting to STATE_DB_PATH '{STATE_DB_PATH}'."
            )
            target_path = STATE_DB_PATH

        self.db_path: Path = target_path
        self._route_cache: Dict[str, Tuple[str, str]] = {}
        self._system_fallback_cache: Optional[str] = None

    def clear_cache(self) -> None:
        """Flushes the in-memory route cache."""
        self._route_cache.clear()
        self._system_fallback_cache = None

    def get_system_fallback(self) -> str:
        """Retrieves system fallback role directly from RouteRepository DB or SkillLibrarian."""
        if self._system_fallback_cache:
            return self._system_fallback_cache

        if not self.db_path.exists():
            librarian = SkillLibrarian.get_instance(self.db_path)
            return librarian.get_default_agent_id()

        try:
            repo = RouteRepository(str(self.db_path))
            fallback = repo.get_system_fallback()

            if fallback:
                self._system_fallback_cache = fallback
                return fallback
        except Exception as e:
            logger.warning(f"[ROUTER] Failed querying system fallback from RouteRepository: {e}")

        librarian = SkillLibrarian.get_instance(self.db_path)
        default_agent = librarian.get_default_agent_id()
        self._system_fallback_cache = default_agent
        return default_agent

    def resolve_route(
        self,
        action_trigger: str = "",
        default_role: Optional[str] = None,
        **kwargs: Any,
    ) -> Tuple[str, str]:
        """Resolves an action trigger to (target_role, fallback_role) via RouteRepository."""
        action_trigger = kwargs.get("action_name", action_trigger)
        default_role = kwargs.get("default_agent", default_role)

        if action_trigger and action_trigger in self._route_cache:
            return self._route_cache[action_trigger]

        ultimate_fallback = default_role or self.get_system_fallback()

        if not self.db_path.exists():
            return ultimate_fallback, ultimate_fallback

        try:
            repo = RouteRepository(str(self.db_path))
            route_data = repo.resolve_and_track_route(action_trigger)

            if route_data:
                if isinstance(route_data, (tuple, list)):
                    target_role, fallback_role = route_data[0], route_data[1]
                elif isinstance(route_data, dict):
                    target_role = route_data.get("target_role", ultimate_fallback)
                    fallback_role = route_data.get("fallback_role")
                else:
                    target_role = getattr(route_data, "target_role", ultimate_fallback)
                    fallback_role = getattr(route_data, "fallback_role", None)

                fallback_role = fallback_role or ultimate_fallback

                if action_trigger:
                    self._route_cache[action_trigger] = (target_role, fallback_role)

                return target_role, fallback_role
        except Exception as e:
            logger.error(f"[ROUTER] Route resolution database query failed for '{action_trigger}': {e}")

        return ultimate_fallback, ultimate_fallback

    def get_agent_instance(
        self,
        target_role: Optional[str] = None,
        heavy_model: str = "",
        archivist: Optional[Any] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Dynamically resolves a target role or agent_id to its canonical database entry
        and returns a RuntimeAgent instance hydrated with metadata from SkillLibrarian.
        Zero legacy file imports or hardcoded agent class paths.
        """
        # Safely extract and remove keys to prevent duplication in **kwargs
        target_role = kwargs.pop("agent_id", target_role)
        heavy_model = kwargs.pop("heavy_model", heavy_model)
        archivist = kwargs.pop("archivist", archivist)
        kwargs.pop("target_role", None)

        if not target_role:
            raise ValueError("Must supply either 'target_role' or 'agent_id' to get_agent_instance.")

        librarian = SkillLibrarian.get_instance(self.db_path)

        # 1. Resolve target input (role alias or system_role) to canonical agent_id
        resolved_agent_id = librarian.resolve_agent_id_for_role(target_role) or target_role

        # 2. Fetch agent manifest/persona configuration directly from Librarian cache
        manifest = librarian.get_agent_manifest(resolved_agent_id) or librarian.get_agent_manifest(target_role)

        if not manifest or not isinstance(manifest, dict):
            raise RuntimeError(
                f"[ROUTER FAULT] No database manifest registered for target '{target_role}' "
                f"(Resolved ID: '{resolved_agent_id}'). Check agent_registry in state database."
            )

        # 3. Check Agent Lifecycle / Status Compliance (Schema V2)
        status = str(manifest.get("status", manifest.get("agent_status", "ACTIVE"))).upper()
        if status in ("QUARANTINED", "DISABLED", "ARCHIVED"):
            raise PermissionError(
                f"[ROUTER BLOCKED] Agent '{resolved_agent_id}' cannot be instantiated. "
                f"Current status: {status}."
            )

        # 4. Import concrete universal agent class
        from charon.agents.runtime import RuntimeAgent

        # 5. If passed pre-instantiated archivist/agent matches target ID, reuse directly
        if archivist is not None and getattr(archivist, "agent_id", None) == resolved_agent_id:
            return archivist

        # 6. Extract configuration payload from DB manifest
        display_name = manifest.get("display_name") or librarian.get_display_name_for_agent(resolved_agent_id)
        description = manifest.get("description", "")
        system_prompt = manifest.get("system_prompt", "")
        active_tools = manifest.get("active_tools") or manifest.get("tools", [])
        priority_weight = float(manifest.get("priority_weight", 1.0))

        # 7. Instantiate and return concrete RuntimeAgent
        return RuntimeAgent(
            agent_id=resolved_agent_id,
            display_name=display_name,
            description=description,
            system_prompt=system_prompt,
            active_tools=active_tools,
            priority_weight=priority_weight,
            heavy_model=heavy_model,
            librarian=librarian,
            **kwargs,
        )

    def register_route(
        self,
        action_trigger: str,
        target_role: str,
        route_type: str = "DYNAMIC_AUTO",
        fallback_role: Optional[str] = None,
        description: str = "",
        created_by: str = "agent",
        force: bool = False,
    ) -> None:
        """Registers a dynamic or system route in the route_registry DB table."""
        librarian = SkillLibrarian.get_instance(self.db_path)

        # Canonicalize target_role and fallback_role before DB insertion
        canonical_target = librarian.resolve_agent_id_for_role(target_role) or target_role
        canonical_fallback = (
            librarian.resolve_agent_id_for_role(fallback_role) if fallback_role else None
        ) or fallback_role

        repo = RouteRepository(str(self.db_path))
        existing_type = repo.get_route_type(action_trigger)

        if existing_type == "SYSTEM" and not force and route_type != "USER_OVERRIDE":
            raise RouteConfigError(
                f"Cannot override IMMUTABLE system route '{action_trigger}'. "
                f"Route type '{route_type}' lacks sufficient permission."
            )

        repo.upsert_route(
            action_trigger,
            canonical_target,
            canonical_fallback,
            route_type,
            description,
            created_by,
        )
        self.clear_cache()

        display_name = librarian.get_display_name_for_agent(canonical_target) or canonical_target

        logger.info(
            f"[ROUTER] Registered route: '{action_trigger}' -> '{display_name}' ({canonical_target}) [{route_type}]"
        )
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/dispatcher/router_tool.py`

```python
"""
charon/core/dispatcher/router_tool.py
System Version: v0.4.0 | File Revision: 2.3.0

Module: Visualization and tuning tool for the routing engine.
Provides CLI-friendly utilities for monitoring, overriding, and quarantining dispatch routes.
Updated to strictly align with SQLite schema column definitions (action_trigger, target_role).
"""

import sqlite3
from pathlib import Path
from typing import Union

from charon.core.dispatcher.router import AgentRouter
from charon.core.skills.librarian import SkillLibrarian
from charon.db.connection import get_connection


class RouterManagerTool:
    """Admin tool for visualizing, editing, and quarantining dispatcher routes."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.router = AgentRouter(self.db_path)

    def render_route_table_ascii(self) -> str:
        """Renders an ASCII visualization table of all registered routes."""
        if not self.db_path.exists():
            return "Database not initialized."

        try:
            with get_connection(self.db_path, read_only=True) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT action_trigger, target_role, fallback_role, route_type, is_active, execution_count, created_by
                    FROM route_registry
                    ORDER BY route_type ASC, action_trigger ASC;
                """)
                rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
            return f"Database query failed on 'route_registry': {e}"

        if not rows:
            return "No routes registered in route_registry."

        header = f"{'ACTION TRIGGER':<28} | {'TARGET ROLE':<20} | {'FALLBACK ROLE':<18} | {'TYPE':<14} | {'STATUS':<8} | {'CALLS':<6} | {'OWNER':<12}"
        divider = "-" * len(header)
        lines = [header, divider]

        for row in rows:
            action = row["action_trigger"]
            role = row["target_role"]
            fallback = row["fallback_role"]
            rtype = row["route_type"]
            active = row["is_active"]
            calls = row["execution_count"]
            owner = row["created_by"]

            status = "ACTIVE" if active else "DISABLED"
            action_str = str(action)[:28] if action else "UNKNOWN"
            role_str = str(role)[:20] if role else "UNASSIGNED"
            fallback_str = str(fallback)[:18] if fallback else "NONE"
            rtype_str = str(rtype)[:14] if rtype else "DEFAULT"
            owner_str = str(owner)[:12] if owner else "SYSTEM"
            calls_str = str(calls) if calls is not None else "0"

            lines.append(
                f"{action_str:<28} | {role_str:<20} | {fallback_str:<18} | {rtype_str:<14} | {status:<8} | {calls_str:<6} | {owner_str:<12}"
            )

        return "\n".join(lines)

    def set_route_override(
        self, action_trigger: str, target_role: str, description: str = ""
    ) -> str:
        """Sets a high-priority USER_OVERRIDE on an action trigger."""
        try:
            self.router.register_route(
                action_trigger=action_trigger,
                target_role=target_role,
                route_type="USER_OVERRIDE",
                description=description,
                created_by="operator_cli",
                force=True,
            )
            librarian = SkillLibrarian.get_instance(self.db_path)
            canonical_target = librarian.resolve_agent_id_for_role(target_role) or target_role
            return f"Successfully applied USER_OVERRIDE for '{action_trigger}' -> '{canonical_target}'"
        except Exception as e:
            return f"Failed to set route override: {e}"

    def set_route_status(self, action_trigger: str, is_active: bool) -> str:
        """Quarantines or re-enables a route by action_trigger without deleting it."""
        if not self.db_path.exists():
            return "Failed to set status: Database not found."

        try:
            with get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE route_registry SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE action_trigger = ?",
                    (1 if is_active else 0, action_trigger),
                )
                affected = cursor.rowcount
        except sqlite3.OperationalError as e:
            return f"Database error while updating route status: {e}"

        # Invalidate cache so the router picks up the quarantined status immediately
        self.router.clear_cache()

        if affected > 0:
            status_str = "ENABLED" if is_active else "QUARANTINED"
            return f"Route '{action_trigger}' is now {status_str}."
        return f"Route '{action_trigger}' not found."

    def delete_route(self, action_trigger: str) -> str:
        """Deletes a custom dynamic or override route from route_registry."""
        if not self.db_path.exists():
            return "Failed to delete route: Database not found."

        try:
            with get_connection(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT route_type FROM route_registry WHERE action_trigger = ?", (action_trigger,))
                row = cursor.fetchone()

                if not row:
                    return f"Route '{action_trigger}' not found."

                if row["route_type"] == "SYSTEM":
                    return f"Cannot delete SYSTEM route '{action_trigger}'. Use quarantining (set_route_status) instead."

                cursor.execute("DELETE FROM route_registry WHERE action_trigger = ?", (action_trigger,))
        except sqlite3.OperationalError as e:
            return f"Database error while deleting route: {e}"

        self.router.clear_cache()
        return f"Successfully deleted route for '{action_trigger}'."
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/dispatcher/telemetry.py`

```python
"""
charon/core/dispatcher/telemetry.py
System Version: v0.4.0 | File Revision: 2.1.0

Module: Telemetry dispatch utilities for async streaming to WebSockets and event listeners.
Enforces a strict TelemetryBus Protocol.
"""

import inspect
import logging
from typing import Any, Dict, Protocol, runtime_checkable

import charon.telemetry.trace as trace_module
from charon.telemetry.trace import TraceEvent, TraceEventType

logger = logging.getLogger("Charon.Dispatcher.Telemetry")


@runtime_checkable
class TelemetryBus(Protocol):
    """
    Strict interface for telemetry dispatching.
    Any bus injected into the system MUST implement this protocol.
    """

    async def emit(self, event: Dict[str, Any]) -> None:
        """Dispatches a telemetry event to all connected listeners or sinks."""
        ...


def get_trace_event_type(name: str) -> Any:
    """Safely resolves enum attribute on TraceEventType with dynamic fallbacks."""
    if not name:
        return list(TraceEventType)[0]

    # 1. Exact match
    if hasattr(TraceEventType, name):
        return getattr(TraceEventType, name)

    # 2. Case-insensitive lookup
    upper_name = name.upper()
    if hasattr(TraceEventType, upper_name):
        return getattr(TraceEventType, upper_name)

    for member in TraceEventType:
        if member.name.upper() == upper_name:
            return member

    # 3. Priority fallback strategy
    for fallback in ("STEP", "ACTION", "EXECUTION_STEP", "TASK_STEP", "INITIALIZATION"):
        if hasattr(TraceEventType, fallback):
            return getattr(TraceEventType, fallback)

    return list(TraceEventType)[0]


async def emit_telemetry(event: TraceEvent) -> None:
    """Async dispatch of trace events through a strongly-typed TelemetryBus interface."""
    # Resolve the active bus dynamically from trace module state
    bus = getattr(trace_module, "telemetry_bus", None)
    if bus is None:
        return

    # Enforce the Protocol contract
    if not isinstance(bus, TelemetryBus) and not hasattr(bus, "emit"):
        logger.warning(
            f"Invalid telemetry_bus injected: {type(bus).__name__}. "
            "Must implement the TelemetryBus Protocol (missing 'emit' method)."
        )
        return

    try:
        # Dump event as JSON-compatible dict inside try block to isolate serialization errors
        if hasattr(event, "model_dump"):
            event_dict = event.model_dump(mode="json")
        elif hasattr(event, "dict"):
            event_dict = event.dict()
        else:
            event_dict = event  # type: ignore

        res = bus.emit(event_dict)
        # Forgiving await in case a synchronous testing stub was injected
        if inspect.isawaitable(res):
            await res
    except Exception as err:
        logger.error(f"TelemetryBus emit call failed: {err}", exc_info=True)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/engine/__init__.py`

```python
"""
charon/core/engine/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: charon.core.engine package.
Exports OrchestrationEngine alongside sub-modules.
"""

from charon.core.engine.dag_executor import DAGPlanExecutor
from charon.core.engine.engine import OrchestrationEngine
from charon.core.engine.self_healing import SelfHealingHandler
from charon.core.engine.synthesizer import OutputSynthesizer

__all__ = [
    "OrchestrationEngine",
    "OutputSynthesizer",
    "SelfHealingHandler",
    "DAGPlanExecutor",
]

```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/engine/dag_executor.py`

```python
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

from charon.core.engine.self_healing import SelfHealingHandler
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
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/engine/engine.py`

```python
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
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/engine/self_healing.py`

```python
"""
charon/core/engine/self_healing.py
System Version: v0.6.3 | File Revision: 4.0.0

Module: Diagnostic intercept and self-healing handler for Charon.
Refactored to query system_roles schema directly, raise explicit fail-fast
runtime errors if mandatory roles are unbound, and protect context limits.
Enforces direct librarian role/action resolution without defensive hasattr checks.
"""

import inspect
import logging
from typing import Any, Callable, Optional, Union

from charon.core.ledger import ExecutionLedger
from charon.core.session import SessionGateway
from charon.core.skills.librarian import SkillLibrarian
from charon.core.skills.roles import RoleResolutionError

logger = logging.getLogger("Charon.Engine.SelfHealing")


class SelfHealingHandler:
    """Inspects step outputs for execution errors and dispatches diagnostic tasks dynamically."""

    def __init__(
        self,
        orchestrator: SessionGateway,
        ledger: Optional[ExecutionLedger] = None,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.orchestrator = orchestrator
        self.ledger = ledger
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _resolve_diagnostic_agent(self) -> str:
        """Dynamically query the Librarian for the agent assigned to diagnostics."""
        # 1. Action-based dynamic resolution
        try:
            diag_agent = self.librarian.resolve_agent_id_for_action("diagnose")
            if diag_agent:
                return diag_agent
        except RoleResolutionError:
            pass

        # 2. Prefer system_engineer role for diagnostic execution
        try:
            engineer_id = self.librarian.resolve_agent_id_for_role("system_engineer")
            if engineer_id:
                return engineer_id
        except RoleResolutionError:
            pass

        # 3. Secondary system_planner fallback
        try:
            planner_id = self.librarian.resolve_agent_id_for_role("system_planner")
            if planner_id:
                return planner_id
        except RoleResolutionError:
            pass

        # Fail Fast: Raise explicit error rather than hallucinating fallbacks
        raise RuntimeError(
            "Bootstrap Error: Neither 'system_engineer' nor 'system_planner' mandatory "
            "roles could be resolved in system_roles for self-healing diagnostics."
        )

    def _truncate_log_for_context(self, log_text: str, max_chars: int = 4000) -> str:
        """Truncates diagnostic log content to fit comfortably within model context windows."""
        if len(log_text) <= max_chars:
            return log_text
        half = max_chars // 2
        truncated_count = len(log_text) - max_chars
        return (
            f"{log_text[:half]}\n\n"
            f"[... Charon Self-Healing Context Guard: Truncated {truncated_count} log characters ...]\n\n"
            f"{log_text[-half:]}"
        )

    async def handle_if_needed(
        self,
        step_num: Union[int, str],
        agent_name: str,
        step_result: Any,
        raw_prompt: str,
        stream_cb: Optional[Callable[[str], None]] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """Inspects step results for failure indicators and invokes a diagnostic action."""
        if step_result is None:
            return ""

        step_result_str = str(step_result)
        if not step_result_str.strip():
            return step_result_str

        # Explicit Authorization & Dependency Guardrails / Loop Prevention
        auth_prefixes = (
            "[Awaiting Authorization]",
            "[Authorization Denied]",
            "[Authorization Error]",
            "[Dependency Error]",
            "[System Error]",
        )
        if any(step_result_str.startswith(prefix) for prefix in auth_prefixes) or "[Self-Healing" in step_result_str:
            logger.debug(
                f"Step {step_num} result indicates policy/status control or existing diagnosis. "
                f"Bypassing self-healing diagnosis."
            )
            return step_result_str

        failure_triggers = [
            "[Runtime Error]",
            "Execution aborted",
            "command not found",
            "Traceback (most recent call last)",
            "SyntaxError:",
            "TypeError:",
            "KeyError:",
            "NameError:",
        ]
        has_error = any(trigger.lower() in step_result_str.lower() for trigger in failure_triggers)

        if not has_error:
            return step_result_str

        logger.warning(f"Step {step_num} ({agent_name}) hit an execution issue. Initiating self-healing...")

        if self.ledger and task_id:
            await self.ledger.log_event(
                task_id=task_id,
                event_type="step_self_healing_triggered",
                data={"step": step_num, "agent": agent_name, "error_preview": step_result_str[:300]},
            )

        if stream_cb:
            stream_cb("\n⚠️ *Step execution failed. Intercepting log output for self-healing diagnosis...*\n")

        try:
            diagnostic_agent_id = self._resolve_diagnostic_agent()
            diagnostic_agent = self.orchestrator.dispatcher._resolve_agent(diagnostic_agent_id)

            sanitized_log = self._truncate_log_for_context(step_result_str, max_chars=4000)

            # Build execution kwargs
            exec_kwargs = {
                "action": "diagnose",
                "parameters": {
                    "log_content": sanitized_log,
                    "failing_agent": agent_name,
                    "step_num": step_num,
                },
                "raw_prompt": raw_prompt,
            }

            # Inspect signature including **kwargs support
            execute_fn = getattr(diagnostic_agent, "execute", None)
            sig = inspect.signature(execute_fn) if execute_fn else None
            if sig:
                has_kwargs = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD
                    for p in sig.parameters.values()
                )
                if "stream_cb" in sig.parameters or has_kwargs:
                    exec_kwargs["stream_cb"] = stream_cb
                elif "stream_callback" in sig.parameters:
                    exec_kwargs["stream_callback"] = stream_cb

            diag_res = diagnostic_agent.execute(**exec_kwargs)
            diagnosis = await diag_res if inspect.isawaitable(diag_res) else diag_res

            if self.ledger and task_id:
                await self.ledger.log_event(
                    task_id=task_id,
                    event_type="step_self_healing_resolved",
                    data={"step": step_num, "diagnosis_preview": str(diagnosis)[:300]},
                )

            return f"{step_result_str}\n\n[Self-Healing Recovery Intercept]:\n{diagnosis}"

        except Exception as diag_err:
            logger.error(f"Failed to execute self-healing diagnosis: {diag_err}", exc_info=True)
            if self.ledger and task_id:
                await self.ledger.log_event(
                    task_id=task_id,
                    event_type="step_self_healing_failed",
                    data={"step": step_num, "error": str(diag_err)},
                )
            return f"{step_result_str}\n\n[Self-Healing Failed]: {str(diag_err)}"
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/engine/synthesizer.py`

```python
"""
charon/core/engine/synthesizer.py
System Version: v0.4.0 | File Revision: 3.0.0

Module: Response synthesis module via dynamic agent routing.
Updated to route synthesis directly through the 'synthesize' DB action SSOT.
"""

import inspect
import logging
from typing import Any, Callable, Optional

from charon.core.session import SessionGateway
from charon.core.skills.librarian import SkillLibrarian

logger = logging.getLogger("Charon.Engine.Synthesizer")


class OutputSynthesizer:
    """Formulates specialist agent outputs into user-facing responses using dynamic agents."""

    def __init__(
        self,
        orchestrator: SessionGateway,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.orchestrator = orchestrator
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _get_synthesis_agent_id(self) -> str:
        """Queries the Librarian SSOT to determine the synthesis agent ID."""
        # 1. Look for explicit candidates authorized for the 'synthesize' action
        if hasattr(self.librarian, "get_agents_for_action"):
            agents = self.librarian.get_agents_for_action("synthesize")
            if agents:
                return agents[0]

        # 2. System generalist / planner fallback resolution
        generalist_id = self.librarian.resolve_agent_id_for_role("system_generalist")
        if generalist_id:
            return generalist_id

        # Fail Fast: Enforce database bootstrap integrity
        raise RuntimeError(
            "[FAIL-FAST] Mandatory 'synthesize' action or 'system_generalist' role not registered in database."
        )

    def _truncate_raw_output_for_context(self, text: str, max_chars: int = 6000) -> str:
        """Truncates raw output from the middle to prevent LLM context window overflows."""
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        truncated_count = len(text) - max_chars
        return (
            f"{text[:half]}\n\n"
            f"[... Charon Synthesis Guard: Truncated {truncated_count} raw characters ...]\n\n"
            f"{text[-half:]}"
        )

    async def synthesize(
        self,
        user_query: str,
        agent: str,
        raw_output: Any,
        stream_cb: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Synthesizes raw specialist tool outputs into clean, user-facing responses."""
        raw_str = str(raw_output) if raw_output is not None else ""

        if not raw_str.strip():
            return "Task executed successfully with no output returned."

        # Resolve display name for logger & prompt
        display_agent = (
            self.librarian.get_display_name_for_agent(agent)
            if hasattr(self.librarian, "get_display_name_for_agent")
            else str(agent)
        )

        logger.info(f"Synthesizing raw tool output from '{display_agent}'...")
        sanitized_context = self._truncate_raw_output_for_context(raw_str, max_chars=6000)

        try:
            # 1. Resolve agent authorized for action 'synthesize'
            synth_agent_id = self._get_synthesis_agent_id()

            # 2. Retrieve agent instance from dispatcher
            synth_agent = self.orchestrator.dispatcher._resolve_agent(synth_agent_id)

            # 3. Construct parameters targeting strict DB action 'synthesize'
            exec_kwargs = {
                "action": "synthesize",
                "parameters": {
                    "user_query": user_query,
                    "raw_output": raw_str,
                    "context": sanitized_context,
                    "executing_agent": display_agent,
                },
                "raw_prompt": user_query,
            }

            sig = inspect.signature(synth_agent.execute) if hasattr(synth_agent, "execute") else None
            if sig:
                has_kwargs = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD
                    for p in sig.parameters.values()
                )
                if "stream_cb" in sig.parameters or has_kwargs:
                    exec_kwargs["stream_cb"] = stream_cb
                elif "stream_callback" in sig.parameters:
                    exec_kwargs["stream_callback"] = stream_cb

            exec_res = synth_agent.execute(**exec_kwargs)
            synthesized = await exec_res if inspect.isawaitable(exec_res) else exec_res

            res_str = str(synthesized).strip() if synthesized else ""

            if not res_str:
                logger.warning(
                    f"Agent '{synth_agent_id}' returned empty synthesis. Falling back to raw output."
                )
                if stream_cb and raw_str:
                    stream_cb(f"{raw_str}\n")
                return raw_str

            return res_str

        except Exception as synth_err:
            logger.warning(f"Synthesis failed; returning raw execution output: {synth_err}")
            if stream_cb and raw_str:
                stream_cb(f"{raw_str}\n")
            return raw_str
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/ledger.py`

```python
"""
charon/core/ledger.py
System Version: v0.1.0 | File Revision: 1.2.1

Module: Execution Audit Ledger
Append-only operational event logger recording agent interactions,
tool executions, gatekeeper decisions, and engine state transitions.
Guarantees strict database separation using LEDGER_DB_PATH.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from charon.config.paths import LEDGER_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.Core.Ledger")


class ExecutionLedger:
    """Thread-safe, append-only operational event journal backed by SQLite WAL."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or LEDGER_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize append-only audit trail tables."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    agent TEXT,
                    tool_name TEXT,
                    data_json TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ledger_task ON audit_ledger(task_id);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ledger_type ON audit_ledger(event_type);
                """
            )
        logger.info(f"ExecutionLedger initialized at: {self.db_path}")

    async def log_event(
        self,
        task_id: str,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        agent: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> int:
        """Append an event entry to the audit log."""
        payload_str = json.dumps(data or {})

        def _exec() -> int:
            with get_connection(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO audit_ledger (task_id, event_type, agent, tool_name, data_json)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (task_id, event_type, agent, tool_name, payload_str),
                )
                return cursor.lastrowid or 0

        return await asyncio.to_thread(_exec)

    async def get_task_history(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieve full chronological execution history for a task."""

        def _exec() -> List[Dict[str, Any]]:
            with get_connection(self.db_path, read_only=True) as conn:
                cursor = conn.execute(
                    """
                    SELECT id, task_id, event_type, agent, tool_name, data_json, timestamp
                    FROM audit_ledger
                    WHERE task_id = ?
                    ORDER BY id ASC;
                    """,
                    (task_id,),
                )
                results = []
                for row in cursor.fetchall():
                    item = dict(row)
                    try:
                        item["data"] = json.loads(item.pop("data_json") or "{}")
                    except json.JSONDecodeError:
                        item["data"] = {}
                    results.append(item)
                return results

        return await asyncio.to_thread(_exec)

    async def purge_task_history(self, task_id: str) -> int:
        """Purge audit history records for a specified task."""

        def _exec() -> int:
            with get_connection(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM audit_ledger WHERE task_id = ?;", (task_id,)
                )
                return cursor.rowcount

        return await asyncio.to_thread(_exec)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/parser.py`

```python
"""
charon/core/parser.py
System Version: v0.2.0 | File Revision: 2.4.1

Module: Pass 1 (Triage Routing) and Pass 2 (Schema Extraction) intent parser
with Tiered Fallback Recovery, Manifest-Driven Routing, and Dynamic Skill Bus Interception.
Refactored to completely remove hardcoded skill strings and enforce Database/Librarian
as the sole source of truth for actions and fallback roles.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import ollama
from pydantic import BaseModel, ValidationError, create_model

from charon.core.prompts import CHARON_ROUTING_PROMPT, EXTRACTION_SYSTEM_PROMPT
from charon.core.skills import SkillLibrarian
from charon.core.utils import clean_json_string, get_schema_json
from charon.intent.manifests import get_agent_manifest, get_triage_agent_descriptions
from charon.intent.routing import RoutingPayload
from charon.utils.memory import ConversationBuffer

logger = logging.getLogger("Charon.Parser")


def _extract_ollama_response_text(response: Any) -> str:
    """Extract raw response string from either dict or Pydantic response objects."""
    if isinstance(response, dict):
        return response.get("response", "{}")
    return getattr(response, "response", "{}")


class IntentParser:
    """Handles LLM-driven classification (routing) and payload parameter extraction with tiered fallback guarantees."""

    def __init__(
        self,
        ollama_client: ollama.AsyncClient,
        triage_model: str,
        heavy_model: str,
        memory: ConversationBuffer,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.ollama_client = ollama_client
        self.triage_model = triage_model
        self.heavy_model = heavy_model
        self.memory = memory
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _get_fallback_agent(self, action_name: Optional[str] = None) -> str:
        """Dynamically resolves a fallback agent via librarian/database roles without hardcoded skill checks."""
        try:
            # If an explicit action was requested, attempt dynamic database resolution for that skill
            if action_name and hasattr(self.librarian, "resolve_agent_id_for_action"):
                resolved_action_agent = self.librarian.resolve_agent_id_for_action(action_name)
                if resolved_action_agent:
                    return resolved_action_agent

            # Primary DB role lookup using standard canonical name
            resolved_planner = self.librarian.resolve_agent_id_for_role("system_planner")
            if resolved_planner:
                return resolved_planner

            resolved_fallback = self.librarian.resolve_agent_id_for_role("system_fallback")
            if resolved_fallback:
                return resolved_fallback
        except Exception as e:
            logger.debug(f"Failed to fetch dynamic fallback role via Librarian: {e}")

        fatal_msg = (
            "CRITICAL ROUTING FAILURE: Could not resolve mandatory fallback system roles "
            "('system_fallback' or 'system_planner') from the database."
        )
        logger.critical(fatal_msg)
        raise RuntimeError(fatal_msg)

    def _get_active_agents_list(self) -> List[str]:
        """Retrieves a list of all active agent IDs via the SkillLibrarian."""
        try:
            if hasattr(self.librarian, "get_active_agent_ids"):
                return self.librarian.get_active_agent_ids()
        except Exception as e:
            logger.error(f"Failed to fetch active agents list from Librarian: {e}")
        return []

    def _get_schema_for_agent(self, agent_id: str) -> type[BaseModel]:
        """Dynamically retrieves or constructs the extraction payload schema for an agent."""
        try:
            if hasattr(self.librarian, "get_agent_schema") and callable(self.librarian.get_agent_schema):
                schema = self.librarian.get_agent_schema(agent_id)
                if schema:
                    return schema
        except Exception as e:
            logger.debug(f"Could not retrieve dynamic schema for {agent_id} from Librarian: {e}")

        # Defensive fallback schema construction
        return create_model(
            f"{agent_id}Payload",
            action=(str, ...),
            prompt=(str, ...),
            query=(Optional[str], None),
            objective=(Optional[str], None),
            problem=(Optional[str], None),
            target_device=(Optional[str], None),
            __base__=BaseModel,
        )

    async def parse_routing(
        self,
        user_input: str,
        rejected_agents: Optional[List[str]] = None,
    ) -> Optional[RoutingPayload]:
        """Pass 1: Dynamic Skill interception, falling back to manifest-grounded classification."""

        # --- PHASE 1: DYNAMIC SKILL BUS FAST-PATH ---
        try:
            matched_skill = self.librarian.find_matching_action(user_input)

            if matched_skill:
                if isinstance(matched_skill, dict):
                    target_agent = matched_skill.get("primary_agent_id") or matched_skill.get("agent_id")
                    skill_name = matched_skill.get("action_name") or matched_skill.get("name")
                else:
                    target_agent = getattr(matched_skill, "primary_agent_id", None) or getattr(
                        matched_skill, "agent_id", None
                    )
                    skill_name = getattr(matched_skill, "action_name", None) or getattr(
                        matched_skill, "name", None
                    )

                if not target_agent:
                    target_agent = self._get_fallback_agent(action_name=skill_name)

                logger.info(f"Skill Bus Intercept: Fast-path routed '{skill_name}' to {target_agent}")
                return RoutingPayload(agent=target_agent)

        except RuntimeError:
            raise  # Bubble up hard runtime errors from missing DB roles
        except Exception as e:
            logger.warning(
                f"SkillLibrarian fast-path check failed: {e}. Falling back to standard LLM triage."
            )
        # --------------------------------------------

        # --- STANDARD CONVERSATIONAL/STATIC TRIAGE ---
        active_agents_list = self._get_active_agents_list()
        valid_agents = ", ".join([f'"{a}"' for a in active_agents_list])
        manifest_descriptions = get_triage_agent_descriptions()

        rejection_prompt = ""
        if rejected_agents:
            rejection_prompt = (
                f"\nCRITICAL CONSTRAINT: The following agents have REJECTED this task: "
                f"{', '.join(rejected_agents)}. DO NOT select them again.\n"
            )

        recent_history = self.memory.get_context_string() if hasattr(self.memory, "get_context_string") else ""
        history_context = (
            f"Recent Conversational Context:\n{recent_history}\n\n" if recent_history else ""
        )

        prompt = (
            f"You are the intent triage classifier for Charon. Examine the user query and select the best agent based on their capabilities:\n\n"
            f"### Available Agents & Manifests:\n{manifest_descriptions}\n\n"
            f"ROUTING RULES:\n"
            f"1. Select your planning/orchestration agent for multi-step sequences, unknown task paths, or file/document discovery.\n"
            f"2. Select your hardware specialist agent for hardware datasheets, electronics components, microcontrollers, or pinouts.\n"
            f"3. Select your baseline agent ONLY for simple, direct OS commands. DO NOT route desktop application launches or file viewing here.\n"
            f"4. For single-action domain requests, select the exact specialist matching the capabilities above.\n"
            f"5. Respond with a simple JSON object containing ONLY the 'agent' key.\n"
            f"Example format: {{\"agent\": \"{active_agents_list[0] if active_agents_list else 'Agent_Name'}\"}}\n\n"
            f"Allowed agent values: {valid_agents}\n{rejection_prompt}\n"
            f"{history_context}"
            f"User Command: {user_input}\n"
            f"JSON Output:"
        )

        try:
            response = await self.ollama_client.generate(
                model=self.triage_model,
                system=CHARON_ROUTING_PROMPT,
                prompt=prompt,
                format="json",
            )
            raw_response = _extract_ollama_response_text(response)
            clean_json = clean_json_string(raw_response)

            # Tier 1: Direct Pydantic Validation
            try:
                payload = RoutingPayload.model_validate_json(clean_json)
                logger.info(f"Triage routed task to: {payload.agent}")
                return payload
            except Exception as direct_err:
                logger.debug(
                    f"Direct routing validation failed: {direct_err}. Attempting key alias extraction."
                )

            # Tier 2: Key Alias Unwrapping
            parsed_dict = json.loads(clean_json)
            agent_candidate = None
            for key in ("agent", "primary_agent", "target_agent", "selected_agent", "destination"):
                if key in parsed_dict and parsed_dict[key]:
                    agent_candidate = parsed_dict[key]
                    break

            if agent_candidate:
                logger.info(f"Triage recovered alias routing to: {agent_candidate}")
                return RoutingPayload(agent=agent_candidate)

            raise ValueError("No recognizable agent key found in triage payload.")

        except Exception as e:
            fallback_agent = self._get_fallback_agent()
            logger.error(f"Failed to parse routing intent: {e}. Defaulting to {fallback_agent}.")
            return RoutingPayload(agent=fallback_agent)

    async def parse_extraction(
        self,
        user_input: str,
        agent: str,
        ledger_context: str = "",
    ) -> BaseModel:
        """Pass 2: Extract parameters using agent-specific Pydantic intent with 3-tier recovery guarantees."""
        schema_class = self._get_schema_for_agent(agent)

        recent_history = self.memory.get_context_string() if hasattr(self.memory, "get_context_string") else ""
        schema_dump = json.dumps(get_schema_json(schema_class), indent=2)

        prompt = (
            f"System Ledger Context:\n{ledger_context}\n\n"
            f"Recent Conversational Context:\n{recent_history}\n\n"
            f"You must respond with a JSON object matching this schema:\n{schema_dump}\n\n"
            f"User Command: {user_input}\n"
            f"JSON Output:"
        )

        try:
            response = await self.ollama_client.generate(
                model=self.heavy_model,
                system=EXTRACTION_SYSTEM_PROMPT,
                prompt=prompt,
                format="json",
            )
            raw_response = _extract_ollama_response_text(response)
            clean_json = clean_json_string(raw_response)

            extraction = None

            # Tier 1: Direct JSON model validation
            try:
                extraction = schema_class.model_validate_json(clean_json)
            except Exception as t1_err:
                logger.debug(f"Tier 1 extraction validation failed for {agent}: {t1_err}")

            # Tier 2: Nested wrapper dict unwrapping & dictionary validation
            if extraction is None:
                try:
                    parsed_dict = json.loads(clean_json)
                    for wrapper_key in ("parameters", "payload", "result", "extracted_payload", "data"):
                        if wrapper_key in parsed_dict and isinstance(parsed_dict[wrapper_key], dict):
                            parsed_dict = parsed_dict[wrapper_key]
                            break

                    extraction = schema_class.model_validate(parsed_dict)
                    logger.info(f"Tier 2 recovery successfully unwrapped payload for {agent}")
                except Exception as t2_err:
                    logger.debug(f"Tier 2 dictionary validation failed for {agent}: {t2_err}")

            # Tier 3: Defensive Fallback
            if extraction is None:
                logger.warning(
                    f"Pass 2 extraction failed for {agent}. Triggering defensive payload fallback."
                )
                extraction = self._build_fallback_payload(schema_class, agent, user_input)

            # Stage 2 Prompt Enrichment
            if hasattr(extraction, "prompt") or hasattr(extraction, "objective") or hasattr(extraction, "problem"):
                current_prompt = (
                    getattr(extraction, "prompt", None)
                    or getattr(extraction, "objective", None)
                    or getattr(extraction, "problem", None)
                    or user_input
                )
                if "Ledger records retrieved:" in ledger_context:
                    enriched = (
                        f"PRIMARY USER COMMAND (STRICT TARGET PATH MUST BE PRESERVED): {current_prompt}\n\n"
                        f"[SYSTEM LEDGER RULES & COMPLIANCE REQUIREMENTS]:\n"
                        f"Note: Use the rules below ONLY to identify required files, subdirectories, or standards. "
                        f"NEVER modify, truncate, or overwrite the target directory path specified in the PRIMARY USER COMMAND.\n"
                        f"{ledger_context}"
                    )
                    updates = {
                        attr: enriched
                        for attr in ("prompt", "objective", "problem")
                        if hasattr(extraction, attr) and getattr(extraction, attr, None) is not None
                    }
                    if updates:
                        try:
                            extraction = extraction.model_copy(update=updates)
                        except Exception:
                            for k, v in updates.items():
                                setattr(extraction, k, v)

            return extraction

        except Exception as e:
            logger.warning(f"Unexpected exception during extraction for {agent}: {e}. Falling back.")
            return self._build_fallback_payload(schema_class, agent, user_input)

    def _build_fallback_payload(
        self,
        schema_class: type,
        agent_id: str,
        user_input: str,
    ) -> BaseModel:
        """Constructs a resilient default payload fetching the default action dynamically from the DB."""
        manifest = get_agent_manifest(agent_id)

        # 1. Check agent manifest default action
        default_action = manifest.default_action if manifest else None

        # 2. Query SkillLibrarian for default action registered in DB
        if not default_action and hasattr(self.librarian, "get_default_action_for_agent"):
            default_action = self.librarian.get_default_action_for_agent(agent_id)

        # 3. Query SkillLibrarian for any primary registered action in DB
        if not default_action and hasattr(self.librarian, "get_primary_action_for_agent"):
            default_action = self.librarian.get_primary_action_for_agent(agent_id)

        # Fail fast if DB contains no action mapping for this agent
        if not default_action:
            fatal_msg = (
                f"DATABASE INTEGRITY ERROR: Agent '{agent_id}' has no registered default action "
                f"or skills in the database. Cannot assemble fallback payload."
            )
            logger.critical(fatal_msg)
            raise RuntimeError(fatal_msg)

        fallback_data: Dict[str, Any] = {
            "action": default_action,
            "prompt": user_input,
            "query": user_input,
            "command": user_input,
            "problem": user_input,
            "objective": user_input,
            "expression": user_input,
            "target_device": user_input,
            "fact": user_input,
        }

        try:
            return schema_class.model_validate(fallback_data)
        except ValidationError:
            pass

        try:
            return schema_class.model_construct(**fallback_data)
        except Exception as err:
            logger.error(f"Critical schema construct failure for {agent_id}: {err}")
            return schema_class.model_construct(action=default_action, prompt=user_input)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/prompts.py`

```python
"""
charon/core/prompts.py
System Version: v0.4.0 | File Revision: 4.0.0

Module: Pure DB-driven prompt generation and ACK formatting adhering strictly to
dynamic routing tables (dynamic_routing_rules, route_registry, system_roles).
Zero hardcoded string bias. Zero static fallbacks.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.config.paths import STATE_DB_PATH
from charon.core.skills.librarian import SkillLibrarian
from charon.db.connection import get_connection
from charon.db.repositories.prompts import PromptRepository

logger = logging.getLogger("Charon.Core.Prompts")


class DynamicRoutingError(RuntimeError):
    """Raised when the database contains no active routing rules or system roles."""
    pass


def fetch_dynamic_routing_context(db_path: Union[str, Path] = STATE_DB_PATH) -> str:
    """
    Constructs the routing context strictly from dynamic_routing_rules.
    """
    query = """
        SELECT trigger, agent_id, description 
        FROM dynamic_routing_rules
        ORDER BY trigger ASC;
    """
    try:
        with get_connection(db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(query)
            rules = cursor.fetchall()

        if not rules:
            return ""

        rule_lines = [
            f"- IF request matches '{r['trigger']}' -> ROUTE TO '{r['agent_id']}' ({r['description']})"
            for r in rules
        ]
        return "\n".join(rule_lines)
    except Exception as err:
        logger.error(f"[Prompts] Failed to query dynamic_routing_rules: {err}")
        return ""


def build_routing_prompt(
    target_role_or_agent: Optional[str] = None,
    repo: Optional[PromptRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> str:
    """
    Dynamically builds the routing prompt purely from active system roles and
    dynamic routing rules in SQLite. Fails fast if no DB state is present.
    """
    repo = repo or PromptRepository(db_path)

    # 1. Fetch active role roster
    roster_items = repo.get_active_role_roster() if hasattr(repo, "get_active_role_roster") else []

    # 2. Fetch dynamic routing rules
    routing_rules = fetch_dynamic_routing_context(db_path)

    if not roster_items and not routing_rules:
        raise DynamicRoutingError(
            "[FATAL] Cannot build routing prompt: No active system_roles or dynamic_routing_rules "
            "found in charon_state.db."
        )

    roster_lines = [
        f"- Role '{item['role_name']}': {item['description']}"
        for item in roster_items
        if isinstance(item, dict)
    ]

    prompt_parts = []

    # Optional role-specific system prompt override from agent_registry
    if target_role_or_agent and hasattr(repo, "get_system_prompt_template"):
        custom_base = repo.get_system_prompt_template(target_role_or_agent)
        if custom_base:
            prompt_parts.append(custom_base)

    if roster_lines:
        prompt_parts.append("ACTIVE ROLES:\n" + "\n".join(roster_lines))

    if routing_rules:
        prompt_parts.append("DYNAMIC ROUTING RULES:\n" + routing_rules)

    return "\n\n".join(prompt_parts)


def build_extraction_prompt(
    target_role_or_agent: Optional[str] = None,
    repo: Optional[PromptRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> str:
    """
    Dynamically builds capability extraction schemas mapped across active roles
    and skill registries directly from SQLite.
    """
    repo = repo or PromptRepository(db_path)

    capabilities = repo.get_role_capabilities() if hasattr(repo, "get_role_capabilities") else []
    if not capabilities:
        raise DynamicRoutingError(
            "[FATAL] Cannot build extraction prompt: No active skill schemas registered in skill_registry."
        )

    capability_lines = []
    current_role = ""

    for row in capabilities:
        if not isinstance(row, dict):
            continue
        role_name = row.get("role_name", "UNKNOWN")
        if role_name != current_role:
            capability_lines.append(f"\nFOR ROLE {role_name.upper()}:")
            current_role = role_name

        action = row.get("action_name", "")
        desc = row.get("description", "")
        params = row.get("parameters") or "{}"

        capability_lines.append(
            f'    - {desc} -> Action: "{action}", Schema: {params}'
        )

    prompt_parts = []

    if target_role_or_agent and hasattr(repo, "get_system_prompt_template"):
        custom_base = repo.get_system_prompt_template(target_role_or_agent)
        if custom_base:
            prompt_parts.append(custom_base)

    prompt_parts.append("ACTIVE CAPABILITIES:\n" + "\n".join(capability_lines))

    return "\n\n".join(prompt_parts)


def get_agent_ack(
    agent_id_or_role: str,
    action: str = "",
    parameters: Optional[Dict[str, Any]] = None,
    repo: Optional[PromptRepository] = None,
    db_path: Union[str, Path] = STATE_DB_PATH,
) -> str:
    """
    Formats a status acknowledgment using SkillLibrarian presentation accessors
    to resolve human-readable display names dynamically from DB state.
    """
    params = parameters or {}
    target = params.get("target_path") or params.get("query") or params.get("command") or ""

    display_name = SkillLibrarian.get_display_name_for_role(agent_id_or_role)
    if display_name == agent_id_or_role:
        display_name = SkillLibrarian.get_display_name_for_agent(agent_id_or_role)

    if target:
        clean_target = str(target).replace(os.path.expanduser("~"), "~")
        return f"[{display_name}: Executing {action} on '{clean_target}']"

    repo = repo or PromptRepository(db_path)
    fallback = "Processing request."
    try:
        if hasattr(repo, "get_default_action_for_identifier") and callable(repo.get_default_action_for_identifier):
            fallback = repo.get_default_action_for_identifier(agent_id_or_role) or fallback
    except Exception as err:
        logger.debug(f"[Prompts] Failed to query default action for identifier '{agent_id_or_role}': {err}")

    return f"[{display_name}: {fallback}]"


def __getattr__(name: str) -> Any:
    """Backward-compatibility interface resolving dynamic calls via DB getters."""
    if name == "CHARON_ROUTING_PROMPT":
        return build_routing_prompt()
    if name == "EXTRACTION_SYSTEM_PROMPT":
        return build_extraction_prompt()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/queue.py`

```python
"""
charon/core/queue.py
System Version: v0.3.3 | File Revision: 1.1.0

Module: Persistent SQLite Task Queue
Thread-safe, persistent task queue backing daemon job orchestration.
Replaces volatile in-memory queues and provides restart recovery.
Adheres to the Janitorial Working Anchor by enforcing role-aware abstractions.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Union

from charon.core.state import StateManager, TaskStatus

logger = logging.getLogger("Charon.Core.Queue")


class PersistentTaskQueue:
    """Async queue interface backed by persistent SQLite task state."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_mgr = state_manager
        self._async_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

    async def initialize_and_recover(self) -> int:
        """
        On daemon startup, recover pending or interrupted tasks from SQLite database
        and re-populate the memory scheduling queue.

        Resilient against individual row corruption to guarantee daemon startup recovery.
        """
        try:
            unfinished = await self.state_mgr.get_unfinished_tasks()
        except Exception as e:
            logger.error(f"Failed to fetch unfinished tasks during queue recovery: {e}")
            return 0

        recovered_count = 0

        for task in unfinished:
            try:
                task_id = self._extract_field(task, "task_id")
                raw_status = self._extract_field(task, "status")

                if not task_id:
                    logger.warning("Skipping malformed unfinished task record with missing 'task_id'.")
                    continue

                # Normalize status string/enum representation
                status_val = raw_status.value if hasattr(raw_status, "value") else str(raw_status)

                # Janitorial Anchor: Reset stuck RUNNING tasks back to PENDING for re-execution
                if status_val == TaskStatus.RUNNING.value:
                    logger.warning(
                        f"Janitorial Anchor Recovery: Resetting interrupted task '{task_id}' (RUNNING -> PENDING)."
                    )
                    await self.state_mgr.update_status(task_id, TaskStatus.PENDING)

                # Construct sanitized task payload adhering to Janitorial role abstractions
                task_payload = {
                    "task_id": task_id,
                    "client_id": self._extract_field(task, "client_id"),
                    "prompt": self._extract_field(task, "prompt", default=""),
                    "agent_override": self._extract_field(task, "agent_override"),
                    "target_role": self._extract_field(task, "target_role"),
                    "action_name": self._extract_field(task, "action_name") or self._extract_field(task, "action"),
                }

                await self._async_queue.put(task_payload)
                recovered_count += 1

            except Exception as e:
                logger.error(f"Failed to recover individual task during queue boot: {e}", exc_info=True)

        logger.info(f"Task queue recovery complete. Reloaded {recovered_count} task(s).")
        return recovered_count

    async def put(self, task_data: Dict[str, Any]) -> str:
        """Enqueue a new task into state storage and async worker queue.

        Ensures routing metadata (action_name, target_role, agent_override) is properly
        persisted while masking concrete raw agent IDs.
        """
        task_id = task_data["task_id"]
        prompt = task_data.get("prompt", "")
        client_id = task_data.get("client_id")

        # Preserve Janitorial Role Abstraction: accept target_role or agent_override
        agent_override = task_data.get("agent_override") or task_data.get("target_role")
        action_name = task_data.get("action_name") or task_data.get("action")

        # 1. Persist to SQLite State DB
        await self.state_mgr.create_task(
            task_id=task_id,
            prompt=prompt,
            client_id=client_id,
            agent_override=agent_override,
        )

        # Normalize in-memory dict payload for downstream AgentDispatcher compatibility
        normalized_data = dict(task_data)
        normalized_data.setdefault("agent_override", agent_override)
        normalized_data.setdefault("action_name", action_name)

        # 2. Add to in-memory scheduling worker
        await self._async_queue.put(normalized_data)
        logger.info(f"Queued task '{task_id}' (Queue Depth: {self._async_queue.qsize()})")
        return task_id

    async def get(self) -> Dict[str, Any]:
        """Fetch next pending task for execution."""
        return await self._async_queue.get()

    def task_done(self) -> None:
        """Acknowledge item processing completion in async queue."""
        self._async_queue.task_done()

    def qsize(self) -> int:
        """Return active queue depth."""
        return self._async_queue.qsize()

    @staticmethod
    def _extract_field(item: Any, key: str, default: Any = None) -> Any:
        """Safely extract field values across dicts, sqlite3.Row, or objects."""
        if isinstance(item, dict):
            return item.get(key, default)
        if hasattr(item, "__getitem__"):
            try:
                return item[key]
            except (KeyError, IndexError):
                return default
        return getattr(item, key, default)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/registry.py`

```python
"""
charon/core/registry.py
System Version: v0.3.3 | File Revision: 1.1.0

Module: Skill Gap Registry & Escalation Counter.
Tracks recurring capability gaps handled during dynamic escalation,
enforcing frequency thresholds before recommending permanent skill forging.
Adheres to the Janitorial Working Anchor by masking concrete agent strings.
"""

import logging
import threading
from typing import Any, Dict, List, Optional, Union

from charon.core.contracts import SkillBlueprint

logger = logging.getLogger("Charon.Core.Registry")


class SkillGapRegistry:
    """Central registry for tracking capability gap frequencies and skill forge eligibility.

    Thread-safe singleton pattern enforcing role-neutral capability tracking.
    """

    _instance: Optional["SkillGapRegistry"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self, threshold: int = 3) -> None:
        self.threshold = threshold
        self._gap_counts: Dict[str, int] = {}
        self._blueprints: Dict[str, SkillBlueprint] = {}

    @classmethod
    def get_instance(cls, default_threshold: int = 3) -> "SkillGapRegistry":
        """Returns thread-safe singleton instance of SkillGapRegistry."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = SkillGapRegistry(threshold=default_threshold)
        return cls._instance

    def log_escalation(
        self, blueprint: Union[SkillBlueprint, Dict[str, Any]], target_role: Optional[str] = None
    ) -> Optional[SkillBlueprint]:
        """Logs an escalation gap event.

        Returns the `SkillBlueprint` ONLY if the occurrence count meets or exceeds the threshold.
        """
        action = self._extract_action(blueprint)
        if not action:
            logger.warning("[GAP_REGISTRY] Attempted to log escalation with invalid or missing action name.")
            return None

        with self._lock:
            self._gap_counts[action] = self._gap_counts.get(action, 0) + 1
            if isinstance(blueprint, SkillBlueprint):
                self._blueprints[action] = blueprint

            count = self._gap_counts[action]
            role_str = f" ({target_role})" if target_role else ""

            logger.info(
                f"[GAP_REGISTRY] Logged escalation gap for action '{action}'{role_str}. "
                f"Frequency: {count}/{self.threshold}"
            )

            if count >= self.threshold:
                logger.warning(
                    f"[GAP_REGISTRY] Threshold reached for action '{action}' ({count} occurrences). "
                    f"Recommending skill forge."
                )
                return self._blueprints.get(action)

        return None

    def get_gap_count(self, action_name: str) -> int:
        """Returns the current frequency count for a given action gap."""
        with self._lock:
            return self._gap_counts.get(action_name, 0)

    def list_pending_blueprints(self) -> List[SkillBlueprint]:
        """Returns all blueprints that have reached or passed the forge threshold."""
        with self._lock:
            return [
                bp
                for action, bp in self._blueprints.items()
                if self._gap_counts.get(action, 0) >= self.threshold
            ]

    def reset_gap(self, action_name: str) -> None:
        """Resets tracking for an action after a permanent skill has been forged and loaded."""
        with self._lock:
            if action_name in self._gap_counts:
                del self._gap_counts[action_name]
            if action_name in self._blueprints:
                del self._blueprints[action_name]
        logger.info(f"[GAP_REGISTRY] Reset gap counter for '{action_name}'.")

    def clear(self) -> None:
        """Flushes all gap counts and stored blueprints (useful for daemon reset or testing)."""
        with self._lock:
            self._gap_counts.clear()
            self._blueprints.clear()

    @staticmethod
    def _extract_action(blueprint: Union[SkillBlueprint, Dict[str, Any]]) -> Optional[str]:
        """Safely extracts the action name from a blueprint object or dictionary."""
        if isinstance(blueprint, dict):
            return blueprint.get("action_name") or blueprint.get("action")
        return getattr(blueprint, "action_name", getattr(blueprint, "action", None))
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/session.py`

```python
"""
charon/core/session.py
System Version: v0.3.0 | File Revision: 3.0.1

Module: Core session gateway for Charon.
Manages manifest-driven triage routing, parameter extraction, and agent dispatch.
Acts as a front controller between incoming requests and the lower-level DAG execution coordinator,
handling identity resolution and short-term memory buffering.
"""

import logging
from typing import Any, Dict, List, Optional

import ollama
from pydantic import BaseModel

from charon.core.dispatcher import AgentDispatcher
from charon.core.parser import IntentParser
from charon.core.prompts import get_agent_ack
from charon.core.skills import SkillLibrarian
from charon.intent.manifests import get_agent_manifest
from charon.intent.routing import RoutingPayload
from charon.utils.memory import ConversationBuffer

logger = logging.getLogger("Charon.SessionGateway")


class SessionGateway:
    """The front desk managing session memory, triage parsing, and request pass-through to execution chains."""

    def __init__(
        self,
        heavy_model: str = "llama3.1",
        triage_model: str = "llama3.1",
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.heavy_model = heavy_model
        self.triage_model = triage_model

        self.librarian = librarian or SkillLibrarian.get_instance()
        self.ollama_client = ollama.AsyncClient()
        self.memory = ConversationBuffer(max_turns=5)

        self.parser = IntentParser(
            ollama_client=self.ollama_client,
            triage_model=self.triage_model,
            heavy_model=self.heavy_model,
            memory=self.memory,
            librarian=self.librarian,
        )

        self.dispatcher = AgentDispatcher(
            heavy_model=self.heavy_model,
        )

    def _resolve_agent_id(self, agent_or_role: str) -> str:
        """Resolves a system role name or agent identifier to a dynamic database ID via SkillLibrarian."""
        if hasattr(self.librarian, "resolve_agent_id_for_role"):
            resolved = self.librarian.resolve_agent_id_for_role(agent_or_role)
            if resolved:
                return resolved
        if hasattr(self.librarian, "resolve_agent_id"):
            resolved = self.librarian.resolve_agent_id(agent_or_role)
            if resolved:
                return resolved
        return agent_or_role

    def _get_agent_display_name(self, agent_or_role: str) -> str:
        """Fetches presentation labels via SkillLibrarian accessor functions."""
        resolved_id = self._resolve_agent_id(agent_or_role)
        if hasattr(self.librarian, "get_display_name_for_agent"):
            display_name = self.librarian.get_display_name_for_agent(resolved_id)
            if display_name:
                return display_name
        if hasattr(self.librarian, "get_display_name_for_role"):
            role_label = self.librarian.get_display_name_for_role(agent_or_role)
            if role_label:
                return role_label
        return agent_or_role

    def get_tool_schemas(self, agent: str) -> List[Dict[str, Any]]:
        """Retrieves OpenAI/Ollama tool specifications for the target agent via SkillLibrarian."""
        resolved_agent_id = self._resolve_agent_id(agent)
        if hasattr(self.librarian, "get_agent_tool_schemas"):
            return self.librarian.get_agent_tool_schemas(resolved_agent_id)
        return []

    def record_turn(self, user_input: str, agent_response: str) -> None:
        """Saves a completed interaction turn into short-term conversation history memory."""
        if not agent_response:
            return

        resp_str = str(agent_response).strip()
        intercept_prefixes = (
            "[Awaiting Authorization]",
            "🛡️ GATEKEEPER",
            "[Authorization Denied]",
            "[Task Cancelled]",
        )
        if resp_str.startswith(intercept_prefixes):
            logger.debug("Skipping memory recording for authorization intercept phrase.")
            return

        if hasattr(self.memory, "add_turn") and callable(getattr(self.memory, "add_turn")):
            self.memory.add_turn(user_input, resp_str)
        elif hasattr(self.memory, "append") and callable(getattr(self.memory, "append")):
            self.memory.append({"user": user_input, "assistant": resp_str})
        else:
            logger.warning("ConversationBuffer lacks add_turn/append method. Turn not recorded.")

    async def parse_routing(
        self,
        user_input: str,
        rejected_agents: Optional[List[str]] = None,
    ) -> Optional[RoutingPayload]:
        """Pass 1: Analytical classification determining target agent."""
        return await self.parser.parse_routing(user_input, rejected_agents)

    async def parse_extraction(
        self, user_input: str, agent: str
    ) -> BaseModel:
        """Pass 2: Extract parameters using agent-specific Pydantic intent."""
        resolved_agent_id = self._resolve_agent_id(agent)

        # Context retrieval has been delegated to the lower-level execution coordinator.
        # The parser only receives the raw user input and short-term memory to extract the schema.
        return await self.parser.parse_extraction(user_input, resolved_agent_id)

    async def execute_agent_task(
        self,
        agent: str,
        extraction: Optional[BaseModel],
        user_raw_input: str,
        stream_cb: Any = None,
    ) -> str:
        """Dispatches extracted parameters to specialist agents and records turn context."""
        resolved_agent_id = self._resolve_agent_id(agent)
        display_name = self._get_agent_display_name(resolved_agent_id)

        logger.info(f"Dispatching task to agent: '{display_name}' (ID: {resolved_agent_id})")

        output_text = await self.dispatcher.dispatch(
            agent_id=resolved_agent_id,
            extraction=extraction,
            user_raw_input=user_raw_input,
            stream_cb=stream_cb,
        )

        self.record_turn(user_raw_input, output_text)
        return output_text

    def get_acknowledgment(
        self,
        agent: str,
        action: Optional[str] = None,
        parameters: Optional[dict] = None,
    ) -> str:
        """Returns a thematic acknowledgment phrase for the routed agent."""
        resolved_agent_id = self._resolve_agent_id(agent)
        return get_agent_ack(
            agent_id=resolved_agent_id,
            action=action or "",
            parameters=parameters,
        )

    def get_agent_manifest_info(self, agent: str):
        """Retrieves the capability manifest for a given agent name or system role."""
        resolved_agent_id = self._resolve_agent_id(agent)
        return get_agent_manifest(resolved_agent_id)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/skills/__init__.py`

```python
"""
charon/core/skills/__init__.py

Module: Core Skills Package.
Re-exports the dynamic skills API to maintain backward compatibility.
"""

from charon.core.skills.base import BaseSkill
from charon.core.skills.executor import SkillExecutorMixin
from charon.core.skills.indexer import SkillIndexerMixin
from charon.core.skills.librarian import SkillLibrarian
from charon.core.skills.models import ActionMetadata, SkillManifest
from charon.core.skills.query import SkillQueryMixin
from charon.core.skills.roles import RoleResolverMixin
from charon.core.skills.routes import RouteManagerMixin

__all__ = [
    "BaseSkill",
    "ActionMetadata",
    "SkillManifest",
    "SkillLibrarian",
    "RoleResolverMixin",
    "RouteManagerMixin",
    "SkillIndexerMixin",
    "SkillQueryMixin",
    "SkillExecutorMixin",
]
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/skills/base.py`

```python
"""
charon/core/skills/base.py
System Version: v0.7.0 | File Revision: 7.0.0

Module: Abstract Base Class defining the contract for in-memory and dynamic skill plugins.
Establishes clean separation between code identity (skill_id) and prompt contract (action_name),
aligned with CBAC Schema V2 capability architecture and quarantine lifecycle management.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union


class BaseSkill(ABC):
    """Abstract Base Class for in-memory and modular Charon Skill Plugins."""

    # Unique code instance identifier (e.g., 'sk_slack_send_msg_v1')
    skill_id: str = "sk_unnamed_skill"

    # Action contract trigger name invoked by LLMs / Routers (e.g., 'send_slack_message')
    action_name: str = "unnamed_action"

    version: str = "1.0.0"
    category: str = "General"
    description: str = "Standard dynamic skill plugin."

    # Internal Python callable/method name inside the skill module
    handler_name: str = "execute"

    # Status state machine: 'ACTIVE', 'QUARANTINED', 'DISABLED'
    status: str = "ACTIVE"
    quarantine_reason: Optional[str] = None

    # Restrict checkout to specific agent IDs, or ["*"] for global availability
    allowed_agents: List[str] = ["*"]
    is_global: bool = False

    # Primitive permissions required by CBAC Schema V2
    required_permissions: List[str] = []

    system_requirements: List[str] = []
    consumed_artifacts: List[str] = []
    produced_artifacts: List[str] = []

    @abstractmethod
    def execute(
        self, agent_name: str, parameters: Dict[str, Any], raw_prompt: str = ""
    ) -> Union[str, Dict[str, Any]]:
        """Executes the skill logic given the agent identity and parameter payload."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Serializes skill metadata for indexing into skill_registry under CBAC Schema V2."""
        return {
            "skill_id": self.skill_id,
            "action_name": self.action_name,
            "version": self.version,
            "category": self.category,
            "description": self.description,
            "handler_name": self.handler_name,
            "status": self.status,
            "quarantine_reason": self.quarantine_reason,
            "allowed_agents": self.allowed_agents,
            "is_global": 1 if self.is_global else 0,
            "required_permissions": self.required_permissions,
            "system_requirements": self.system_requirements,
            "consumed_artifacts": self.consumed_artifacts,
            "produced_artifacts": self.produced_artifacts,
        }
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/skills/executor.py`

```python
"""
charon/core/skills/executor.py
System Version: v0.6.3 | File Revision: 7.0.0

Module: Dynamic module import and skill checkout execution mixin for SkillLibrarian.
Resolves skill_id and handler_name to safely load disk plugins into runtime callables.
Integrates CBAC Schema V2 permission gatechecking and Quarantine State verification.
Enforces strict fail-fast role resolution against database registry.
"""

import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from charon.core.skills.base import BaseSkill
from charon.core.skills.roles import RoleResolutionError

logger = logging.getLogger("Charon.Core.Skills.Executor")


class SkillExecutorMixin:
    """Skill checkout and runtime handler resolution for SkillLibrarian."""

    def check_out_skill(
        self, action: str, agent_name: str
    ) -> Optional[Callable[..., Union[str, Dict[str, Any]]]]:
        """
        Validates authorization constraints, quarantine states, and CBAC permissions,
        then signs out the plugin handler callable.
        Resolves action_name -> skill_id -> entry_file_path + handler_name.
        Fails fast if agent_name cannot be resolved to an active agent in SQLite.
        """
        # Ground Truth DB Lookup: Fails hard if unresolvable
        canonical_agent = self.resolve_agent_id_for_role(agent_name)

        # 1. Look up skill metadata row to identify skill_id and status
        row = self.repo.get_skill_by_action(action)
        if not row:
            row = self.get_action_details(action)
            if not row:
                logger.error(f"[LIBRARIAN] Action contract '{action}' not found in registry.")
                return None

        skill_id = (
            row.get("skill_id", "unknown")
            if isinstance(row, dict)
            else getattr(row, "skill_id", "unknown")
        )
        status = (
            row.get("status", "QUARANTINED")
            if isinstance(row, dict)
            else getattr(row, "status", "QUARANTINED")
        )

        # 2. Check quarantine state
        if status == "QUARANTINED":
            quarantine_reason = (
                row.get("quarantine_reason", "Skill is in dynamic quarantine.")
                if isinstance(row, dict)
                else getattr(row, "quarantine_reason", "Skill is in dynamic quarantine.")
            )
            logger.warning(
                f"[LIBRARIAN] Checkout blocked: Skill '{skill_id}' ({action}) is QUARANTINED. Reason: {quarantine_reason}"
            )
            return None
        elif status == "DISABLED":
            logger.warning(
                f"[LIBRARIAN] Checkout blocked: Skill '{skill_id}' ({action}) is DISABLED."
            )
            return None

        # 3. CBAC Authorization Gatecheck
        perm_repo = getattr(self, "permission_repo", None)
        if perm_repo is not None:
            authorized = perm_repo.authorize_execution(canonical_agent, skill_id)
            if not authorized:
                logger.warning(
                    f"[LIBRARIAN] CBAC Access Denied: Agent '{canonical_agent}' unauthorized for skill '{skill_id}' ({action})."
                )
                return None
        else:
            # Fallback capability check via agent_skill_map
            if not self.is_skill_available(action, canonical_agent):
                logger.warning(
                    f"[LIBRARIAN] Access denied or skill unavailable for action '{action}' -> agent '{canonical_agent}' (raw: '{agent_name}')."
                )
                return None

        # 4. Check in-memory registered skills cache
        skills_map = getattr(self, "_skills", {})
        if action in skills_map:
            in_mem_skill = skills_map[action]
            logger.info(f"[LIBRARIAN] In-memory skill contract '{action}' checked out.")
            if isinstance(in_mem_skill, BaseSkill):
                if inspect.iscoroutinefunction(in_mem_skill.execute):
                    async def async_in_mem_wrapper(
                        agent="", params=None, raw_prompt="", agent_name=None, parameters=None, **kwargs
                    ):
                        return await in_mem_skill.execute(
                            agent_name or agent,
                            parameters if parameters is not None else (params or {}),
                            raw_prompt,
                        )
                    return async_in_mem_wrapper

                return lambda agent="", params=None, raw_prompt="", agent_name=None, parameters=None, **kwargs: in_mem_skill.execute(
                    agent_name or agent,
                    parameters if parameters is not None else (params or {}),
                    raw_prompt,
                )
            elif callable(in_mem_skill):
                return self._wrap_callable(in_mem_skill, default_action=action)

        try:
            # Defensive property extraction
            raw_path = (
                row.get("entry_file_path")
                if isinstance(row, dict)
                else getattr(row, "entry_file_path", None)
            )
            handler_name = (
                row.get("handler_name")
                if isinstance(row, dict)
                else getattr(row, "handler_name", "execute")
            )

            # Pre-flight Guardrail 1: DB entry missing disk path definition
            if not raw_path:
                logger.critical(
                    f"[PHANTOM SKILL DETECTED] Action '{action}' is registered in database (skill_id: '{skill_id}'), "
                    f"but lacks a valid 'entry_file_path' property."
                )
                return None

            entry_file_path = Path(raw_path)

            # Pre-flight Guardrail 2: DB/Disk Desync
            if not entry_file_path.exists() or not entry_file_path.is_file():
                logger.critical(
                    f"[PHANTOM SKILL DETECTED] Action '{action}' is registered in database (skill_id: '{skill_id}'), "
                    f"but plugin implementation file is missing on disk at '{entry_file_path}'. "
                    f"Database/Disk desync detected."
                )
                return None

            module_name = f"charon.skills_registry.dynamic.{skill_id}"
            spec = importlib.util.spec_from_file_location(module_name, entry_file_path)
            if spec is None or spec.loader is None:
                logger.error(f"[LIBRARIAN] Failed to load spec for {module_name} at '{entry_file_path}'.")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Resolution Priority 1: BaseSkill sub-class instantiation within module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    inspect.isclass(attr)
                    and issubclass(attr, BaseSkill)
                    and attr is not BaseSkill
                ):
                    instance = attr()
                    logger.info(
                        f"[LIBRARIAN] Checked out BaseSkill class '{attr_name}' for action '{action}' ({skill_id})."
                    )
                    if inspect.iscoroutinefunction(instance.execute):
                        async def async_base_skill_wrapper(
                            agent="", params=None, raw_prompt="", agent_name=None, parameters=None, **kwargs
                        ):
                            return await instance.execute(
                                agent_name or agent,
                                parameters if parameters is not None else (params or {}),
                                raw_prompt,
                            )
                        return async_base_skill_wrapper

                    return lambda agent="", params=None, raw_prompt="", agent_name=None, parameters=None, **kwargs: instance.execute(
                        agent_name or agent,
                        parameters if parameters is not None else (params or {}),
                        raw_prompt,
                    )

            # Resolution Priority 2: Explicit function corresponding to handler_name
            if handler_name and hasattr(module, handler_name):
                target_func = getattr(module, handler_name)
                logger.info(
                    f"[LIBRARIAN] Checked out handler function '{handler_name}' for action '{action}' ({skill_id})."
                )
                return self._wrap_callable(target_func, default_action=action)

            # Resolution Priority 3: Fallback module action entrypoint
            if hasattr(module, "execute_action"):
                target_func = getattr(module, "execute_action")
                logger.info(
                    f"[LIBRARIAN] Checked out 'execute_action' fallback for action '{action}' ({skill_id})."
                )

                if inspect.iscoroutinefunction(target_func):
                    async def async_fallback(
                        agent="", params=None, raw_prompt="", agent_name=None, parameters=None, **kwargs
                    ):
                        eff_params = parameters if parameters is not None else (params or {})
                        return await target_func(action, eff_params)
                    return async_fallback

                return lambda agent="", params=None, raw_prompt="", agent_name=None, parameters=None, **kwargs: target_func(
                    action,
                    parameters if parameters is not None else (params or {}),
                )

            logger.error(f"[LIBRARIAN] Execution handler '{handler_name}' missing in '{entry_file_path}'.")
            return None

        except Exception as e:
            logger.error(f"[LIBRARIAN] Exception during checkout for skill '{action}': {e}", exc_info=True)
            return None

    def _wrap_callable(
        self, target_func: Callable[..., Any], default_action: str = ""
    ) -> Callable[..., Any]:
        """Wraps target functions with signature inspection to normalize runtime parameter passing."""
        sig = inspect.signature(target_func)
        params_count = len(sig.parameters)
        is_async = inspect.iscoroutinefunction(target_func)

        if is_async:
            async def async_runtime_wrapper(
                agent_name: str = "",
                parameters: Optional[Dict[str, Any]] = None,
                raw_prompt: str = "",
                agent: str = "",
                params: Optional[Dict[str, Any]] = None,
                **kwargs: Any,
            ) -> Any:
                eff_agent = agent_name or agent
                eff_params = parameters if parameters is not None else (params if params is not None else {})

                if params_count >= 3:
                    return await target_func(eff_agent, eff_params, raw_prompt)
                elif params_count == 2:
                    return await target_func(eff_agent, eff_params)
                elif params_count == 1:
                    return await target_func(eff_params)
                else:
                    return await target_func()

            return async_runtime_wrapper

        def sync_runtime_wrapper(
            agent_name: str = "",
            parameters: Optional[Dict[str, Any]] = None,
            raw_prompt: str = "",
            agent: str = "",
            params: Optional[Dict[str, Any]] = None,
            **kwargs: Any,
        ) -> Any:
            eff_agent = agent_name or agent
            eff_params = parameters if parameters is not None else (params if params is not None else {})

            if params_count >= 3:
                return target_func(eff_agent, eff_params, raw_prompt)
            elif params_count == 2:
                return target_func(eff_agent, eff_params)
            elif params_count == 1:
                return target_func(eff_params)
            else:
                return target_func()

        return sync_runtime_wrapper

    checkout_skill = check_out_skill
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/skills/indexer.py`

```python
"""
charon/core/skills/indexer.py
System Version: v0.6.3 | File Revision: 7.0.0

Module: Dynamic discovery, skill promotion, route syncing, and database re-indexing mixin.
Maintains clean separation between immutable code identifiers (skill_id) and prompt contracts (action_name).
All direct SQL execution extracted to repository layer.
Integrates CBAC Schema V2 permission indexing and quarantine status preservation.
Enforces strict fail-fast role resolution against database registry.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from charon.config.paths import DYNAMIC_SKILLS_DIR
from charon.core.skills.base import BaseSkill
from charon.core.skills.models import SkillManifest
from charon.core.skills.roles import RoleResolutionError

logger = logging.getLogger("Charon.Core.Skills.Indexer")


class SkillIndexerMixin:
    """Disk discovery, dynamic promotion, route syncing, and database re-indexing methods."""

    def register_skill(self, skill: BaseSkill) -> None:
        """Registers an in-memory skill instance keyed by its prompt action contract."""
        self._skills[skill.action_name] = skill
        logger.info(
            f"[LIBRARIAN] In-memory skill '{skill.action_name}' (ID: {skill.skill_id}) registered."
        )

    def verify_system_requirements(self, requirements: List[str]) -> bool:
        """Validates shell dependencies against host environment PATH."""
        return all(shutil.which(req) is not None for req in requirements)

    def _discover_manifests(self, extra_paths: Optional[List[Path]] = None) -> List[Path]:
        """Scans search_paths and optional extra paths for manifest files."""
        manifests: List[Path] = []
        all_paths = list(self.search_paths)
        if extra_paths:
            all_paths.extend(extra_paths)

        for search_path in all_paths:
            expanded = search_path.expanduser().resolve()
            if expanded.exists() and expanded.is_dir():
                manifests.extend(expanded.rglob("manifest.json"))

        unique_manifests = list({m.resolve(): m for m in manifests}.values())
        return unique_manifests

    def _promote_skill_to_dynamic(self, source_manifest_path: Path) -> Path:
        """Copies staged skill directory into skills_registry/dynamic/<skill_id>/"""
        source_dir = source_manifest_path.parent
        raw_text = source_manifest_path.read_text(encoding="utf-8")
        manifest_data = json.loads(raw_text)
        skill_id = manifest_data.get("skill_id", source_dir.name)

        target_dir = (DYNAMIC_SKILLS_DIR / skill_id).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        if source_dir.resolve() != target_dir:
            for item in source_dir.glob("*"):
                if item.is_file():
                    shutil.copy2(item, target_dir / item.name)
                elif item.is_dir():
                    shutil.copytree(item, target_dir / item.name, dirs_exist_ok=True)
            logger.info(
                f"[LIBRARIAN] Promoted skill '{skill_id}' from {source_dir} -> {target_dir}"
            )

        return target_dir / "manifest.json"

    def reindex_skills(
        self, extra_paths: Optional[List[Path]] = None, auto_promote: bool = False
    ) -> None:
        """
        Unified pipeline for skill indexing and role-based route synchronization.
        Establishes skill_registry entries and maps agent capability FKs via agent_skill_map.
        Saves CBAC Schema V2 required permissions and preserves active quarantine states.
        Fails fast if any manifest references an invalid role or agent not present in SQLite.
        """
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("[LIBRARIAN] Executing skill reindexing pipeline...")

        try:
            # Ensure schema state across repositories safely
            if hasattr(self.repo, "ensure_schema"):
                self.repo.ensure_schema()
            if hasattr(self.agent_repo, "ensure_schema"):
                self.agent_repo.ensure_schema()
            if hasattr(self.route_repo, "ensure_schema"):
                self.route_repo.ensure_schema()
            if (
                hasattr(self, "permission_repo")
                and self.permission_repo is not None
                and hasattr(self.permission_repo, "ensure_schema")
            ):
                self.permission_repo.ensure_schema()

            # Clear existing agent-skill mappings via repository abstraction
            self.repo.clear_all_agent_skill_mappings()

            raw_manifests = self._discover_manifests(extra_paths=extra_paths)
            logger.info(f"[LIBRARIAN] Discovered {len(raw_manifests)} manifest(s).")

            processed_manifests: List[Path] = []
            for m_path in raw_manifests:
                try:
                    target_m_path = (
                        self._promote_skill_to_dynamic(m_path) if auto_promote else m_path
                    )
                    if target_m_path not in processed_manifests:
                        processed_manifests.append(target_m_path)
                except Exception as e:
                    logger.error(
                        f"[LIBRARIAN] Failed to process manifest {m_path}: {e}"
                    )

            # Pass 1: Index skills into skill_registry and populate agent_skill_map
            for manifest_path in processed_manifests:
                try:
                    raw_text = manifest_path.read_text(encoding="utf-8")
                    raw_json = json.loads(raw_text)
                    manifest = SkillManifest.model_validate_json(raw_text)
                    entry_file = manifest_path.parent / "plugin.py"

                    if not entry_file.exists():
                        logger.warning(
                            f"[LIBRARIAN] Plugin implementation file missing at '{entry_file}' for manifest '{manifest.skill_id}'."
                        )
                        continue

                    allowed_agents_list = getattr(manifest, "allowed_agents", []) or raw_json.get(
                        "allowed_agents", []
                    )
                    if isinstance(allowed_agents_list, str):
                        allowed_agents_list = [allowed_agents_list]

                    is_global = 1 if ("*" in allowed_agents_list or getattr(manifest, "is_global", False)) else 0
                    total_actions = len(manifest.supported_actions)

                    # CBAC Schema V2 fields
                    status = getattr(manifest, "status", "ACTIVE") or raw_json.get("status", "ACTIVE")
                    quarantine_reason = getattr(manifest, "quarantine_reason", None) or raw_json.get("quarantine_reason", None)
                    required_permissions = getattr(manifest, "required_permissions", []) or raw_json.get("required_permissions", [])

                    for action_name, action_def in manifest.supported_actions.items():
                        # Derive unique primary key skill_id per action contract entry
                        if total_actions > 1 and not manifest.skill_id.endswith(f"_{action_name}"):
                            action_skill_id = f"{manifest.skill_id}_{action_name}"
                        else:
                            action_skill_id = manifest.skill_id

                        if isinstance(action_def, dict):
                            desc = action_def.get(
                                "description",
                                manifest.description or f"Executes '{action_name}'",
                            )
                            handler_name = action_def.get("handler") or action_def.get("handler_name", f"handle_{action_name}")
                            params = action_def.get("parameters", {})
                        else:
                            desc = manifest.action_descriptions.get(
                                action_name,
                                manifest.description or f"Executes '{action_name}'",
                            )
                            handler_name = str(action_def)
                            params = manifest.action_parameters.get(action_name, {})

                        # Upsert skill contract record through SkillRepository
                        self.repo.upsert_skill(
                            skill_id=action_skill_id,
                            action_name=action_name,
                            version=manifest.version,
                            category=manifest.category,
                            description=desc,
                            parameters=params,
                            system_requirements=manifest.system_requirements,
                            consumed_artifacts=manifest.consumed_artifacts,
                            produced_artifacts=manifest.produced_artifacts,
                            entry_file_path=str(entry_file.resolve()),
                            handler_name=handler_name,
                            is_global=is_global,
                            status=status,
                            quarantine_reason=quarantine_reason,
                            required_permissions=required_permissions,
                        )

                        # Link active agents to agent_skill_map using (agent_id, skill_id)
                        if is_global:
                            active_agents = self.agent_repo.get_active_agent_ids()
                            for agent_id in active_agents:
                                self.repo.link_agent_to_skill(agent_id, action_skill_id)
                        else:
                            for raw_agent_id in allowed_agents_list:
                                if raw_agent_id == "*":
                                    continue
                                # Strict DB lookup: Fails immediately if raw_agent_id/role is unmapped in SQLite
                                canonical_id = self.resolve_agent_id_for_role(raw_agent_id)
                                self.repo.link_agent_to_skill(canonical_id, action_skill_id)

                except RoleResolutionError as rre:
                    logger.error(f"[LIBRARIAN] Role Resolution Error indexing manifest {manifest_path}: {rre}")
                    raise
                except Exception as e:
                    logger.warning(
                        f"[LIBRARIAN] Failed to index manifest {manifest_path}: {e}",
                        exc_info=True,
                    )

            # Pass 2: Sync route_registry via RouteRepository
            self.route_repo.sync_dynamic_routes()

            # Pass 3: Invalidate and reload in-memory manifest cache
            if hasattr(self, "reload_all_manifests"):
                self.reload_all_manifests()

            logger.info("[LIBRARIAN] Skill reindexing and routing sync complete.")
        except Exception as e:
            logger.error(f"[LIBRARIAN] Reindexing pipeline failed: {e}", exc_info=True)
            raise
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/skills/librarian.py`

```python
"""
charon/core/skills/librarian.py
System Version: v0.6.5 | File Revision: 10.3.0

Module: Central registry, hybrid DB/disk discovery hub, dynamic query bus, and authorization desk.
Combines RoleResolver, RouteManager, SkillIndexer, SkillQuery, and SkillExecutor mixins.
Integrates CBAC Schema V2 authorization, PermissionRepository, and Quarantine State controls.
Enforces strict fail-fast role resolution against database registry with dynamic defaults.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.core.skills.base import BaseSkill
from charon.core.skills.executor import SkillExecutorMixin
from charon.core.skills.indexer import SkillIndexerMixin
from charon.core.skills.query import SkillQueryMixin
from charon.core.skills.roles import RoleResolutionError, RoleResolverMixin
from charon.core.skills.routes import RouteManagerMixin
from charon.db.repositories import (
    AgentRepository,
    PermissionRepository,
    RoleRepository,
    RouteRepository,
    SkillRepository,
)

logger = logging.getLogger("Charon.Core.Skills")


class SkillLibrarian(
    RoleResolverMixin,
    RouteManagerMixin,
    SkillIndexerMixin,
    SkillQueryMixin,
    SkillExecutorMixin,
):
    """Central registry, dynamic query bus, role-resolver, and authorization manager for Charon."""

    _instance: Optional["SkillLibrarian"] = None

    def __init__(
        self,
        search_paths: Optional[List[Path]] = None,
        db_path: Union[Path, str] = STATE_DB_PATH,
        skill_repo: Optional[SkillRepository] = None,
        agent_repo: Optional[AgentRepository] = None,
        role_repo: Optional[RoleRepository] = None,
        route_repo: Optional[RouteRepository] = None,
        permission_repo: Optional[PermissionRepository] = None,
    ) -> None:
        self._skills: Dict[str, BaseSkill] = {}
        self.db_path: Path = Path(db_path)

        # Instantiate Data Access Layer (DAL) Repositories
        self.repo: SkillRepository = skill_repo or SkillRepository(self.db_path)
        self.agent_repo: AgentRepository = agent_repo or AgentRepository(self.db_path)
        self.role_repo: RoleRepository = role_repo or RoleRepository(self.db_path)
        self.route_repo: RouteRepository = route_repo or RouteRepository(self.db_path)
        self.permission_repo: PermissionRepository = (
            permission_repo or PermissionRepository(self.db_path)
        )

        # In-memory manifest cache for zero-latency triage lookups
        self._manifest_cache: Dict[str, Dict[str, Any]] = {}
        self.reload_all_manifests()

        default_paths = [
            PKG_DYNAMIC_SKILLS_DIR,
            PKG_STAGED_SKILLS_DIR,
        ]
        if DYNAMIC_SKILLS_DIR.exists():
            default_paths.append(DYNAMIC_SKILLS_DIR)

        self.search_paths: List[Path] = search_paths or default_paths

    @classmethod
    def get_instance(cls, db_path: Optional[Union[Path, str]] = None) -> "SkillLibrarian":
        """Singleton accessor for global agent capability lookup and manifest resolution."""
        target_path = Path(db_path) if db_path else STATE_DB_PATH
        if cls._instance is None:
            cls._instance = SkillLibrarian(db_path=target_path)
        elif db_path is not None and cls._instance.db_path != target_path:
            cls._instance = SkillLibrarian(db_path=target_path)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Flushes the singleton instance (primarily used for test teardowns or DB switches)."""
        cls._instance = None

    # =========================================================================
    # Skill Action Lookup & Authorization API
    # =========================================================================

    def get_action_manifest(
        self, action: str, agent_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieves action details/manifest for a given skill trigger after validating authorization.

        Gracefully returns None if role resolution fails or skill is unauthorized.
        """
        if not action:
            return None

        # Validate agent authorization if agent name/ID provided
        if agent_name:
            try:
                canonical_agent = self.resolve_agent_id_for_role(agent_name)
                if not self.is_skill_available(action, canonical_agent):
                    return None
            except RoleResolutionError:
                logger.debug(f"[SkillLibrarian] Unmapped agent/role '{agent_name}' for action '{action}'.")
                return None

        # Resolve skill action metadata from query mixin or repository
        details = self.get_action_details(action)
        if details:
            return details

        return self.repo.get_skill_by_action(action)

    def get_agents_for_action(self, action_name: str) -> List[str]:
        """Resolves candidate agent IDs authorized to perform an ACTIVE action capability contract.

        Delegates directly to SkillRepository SSOT query.
        """
        if not action_name:
            return []
        try:
            return self.repo.get_agents_for_action(action_name.strip())
        except Exception as err:
            logger.error(
                f"[SkillLibrarian] Error resolving candidate agents for action '{action_name}': {err}"
            )
            return []

    def list_available_actions(self, agent_or_role: str) -> List[str]:
        """Retrieves all active action capability names granted to an agent or role alias.

        Resolves role aliases to canonical agent IDs before querying SSOT state.
        """
        if not agent_or_role:
            return []
        try:
            canonical_id = self.resolve_agent_id_for_role(agent_or_role)
            return self.repo.get_actions_for_agent(canonical_id)
        except RoleResolutionError as rre:
            logger.warning(
                f"[SkillLibrarian] Could not resolve role '{agent_or_role}' for available actions: {rre}"
            )
            return []
        except Exception as err:
            logger.error(
                f"[SkillLibrarian] Error listing actions for target '{agent_or_role}': {err}"
            )
            return []

    # =========================================================================
    # Dynamic Router & Manifest Control API
    # =========================================================================

    def get_agent_default_action(self, agent_id: str) -> Optional[str]:
        """Retrieves the default interface action for an agent.

        Resolves canonical agent ID via RoleResolverMixin and queries cached manifests.
        """
        manifest = self.get_agent_manifest(agent_id)
        if manifest and "default_action" in manifest:
            return str(manifest["default_action"])
        return None

    def get_default_action_for_role(self, role_name: str) -> str:
        """Resolves and returns the default action_name for a given system role.

        Fails fast if role_name cannot be resolved to an agent in SQLite.
        """
        agent_id = self.resolve_agent_id_for_role(role_name)

        agent_manifest = self.get_agent_manifest(agent_id) or {}
        if isinstance(agent_manifest, dict):
            return agent_manifest.get("default_action") or ""

        return getattr(agent_manifest, "default_action", "")

    def reload_all_manifests(self) -> None:
        """Refreshes the in-memory manifest cache directly from AgentRepository."""
        try:
            self._manifest_cache = self.agent_repo.get_all_manifests()
            logger.info(
                f"[SkillLibrarian] Cached {len(self._manifest_cache)} agent manifest(s) in memory."
            )
        except Exception as e:
            logger.warning(
                f"[SkillLibrarian] Could not load agent manifests on startup: {e}"
            )

    def get_all_agent_manifests(self) -> Dict[str, Dict[str, Any]]:
        """Returns all cached agent manifests."""
        return self._manifest_cache

    def get_agent_manifest(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single manifest by resolving agent target via RoleResolverMixin.

        Fails fast if agent_id is an unmapped role/agent.
        """
        if not agent_id:
            return None
        try:
            canonical_id = self.resolve_agent_id_for_role(agent_id)
            return self._manifest_cache.get(canonical_id) or self._manifest_cache.get(agent_id)
        except RoleResolutionError:
            return None

    def update_agent_manifest(self, agent_id: str, update_data: Dict[str, Any]) -> bool:
        """Delegates manifest persistence to AgentRepository via resolved agent ID and refreshes cache."""
        canonical_id = self.resolve_agent_id_for_role(agent_id)
        success = self.agent_repo.update_manifest(canonical_id, update_data)
        if success:
            self.reload_agent_manifest(canonical_id)
        return success

    def reload_agent_manifest(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Hot-reloads a single agent manifest from AgentRepository into memory cache."""
        canonical_id = self.resolve_agent_id_for_role(agent_id)
        manifest = self.agent_repo.get_manifest(canonical_id)
        if manifest:
            self._manifest_cache[canonical_id] = manifest
        else:
            self._manifest_cache.pop(canonical_id, None)
        return manifest

    def set_tool_status(self, agent_id: str, tool_name: str, enabled: bool) -> bool:
        """Toggles agent capability via AgentRepository and hot-reloads the manifest cache."""
        canonical_id = self.resolve_agent_id_for_role(agent_id)
        success = self.agent_repo.set_tool_status(canonical_id, tool_name, enabled)

        if success:
            self.reload_agent_manifest(canonical_id)
        return success
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/skills/models.py`

```python
"""
charon/core/skills/models.py
System Version: v0.8.0 | File Revision: 8.0.0

Module: Pydantic schemas for dynamic skill manifests and action specifications.
Enforces Pydantic V2 validation and schema normalization for SkillManifest and ActionMetadata.
Integrates CBAC Schema V2 permission declarations and quarantine lifecycle states.
Preserves raw identifier fidelity without forced case conversions or prefix mutations.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class ActionMetadata(BaseModel):
    """Schema defining individual action capability specs inside a skill."""

    action_name: str = Field(..., description="Unique action capability key.")
    description: str = Field(
        default="", description="Human-readable summary of what the action does."
    )
    handler_name: str = Field(
        default="execute_action", description="Target python function name in plugin.py."
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema for parameters."
    )
    required_permissions: List[str] = Field(
        default_factory=list,
        description="CBAC Schema V2 permissions required to execute this action.",
    )
    consumed_artifacts: List[str] = Field(
        default_factory=list, description="Expected input artifact types."
    )
    produced_artifacts: List[str] = Field(
        default_factory=list, description="Expected output artifact types."
    )


class SkillManifest(BaseModel):
    """Pydantic v2 schema governing dynamic disk-based skill plugin manifests (manifest.json)."""

    skill_id: str = Field(..., description="Unique skill identifier, e.g. 'kicad_autoroute'")
    version: str = Field(default="1.0.0", description="SemVer version string for skill versioning")
    description: str = Field(default="", description="Package-level skill description")
    category: str = Field(default="General", description="Taxonomy category for skill organization")
    status: str = Field(
        default="ACTIVE",
        description="Lifecycle status of skill (ACTIVE, QUARANTINED, INACTIVE).",
    )
    quarantine_reason: Optional[str] = Field(
        default=None,
        description="Detailed explanation if skill is currently QUARANTINED.",
    )
    required_permissions: List[str] = Field(
        default_factory=list,
        description="CBAC Schema V2 system permissions required by this skill.",
    )
    author: str = Field(default="Charon Librarian", description="Author or maintainer name")
    primary_agent_id: str = Field(
        default="system_generalist",
        description="Primary system role owner or canonical agent identifier",
    )
    allowed_agents: List[str] = Field(
        default_factory=list,
        description="Explicit list of agent_ids permitted to execute this skill. Empty grants zero permissions.",
    )
    shelf_tags: List[str] = Field(
        default_factory=list,
        description="Search and discovery keywords or categories for skill taxonomy",
    )
    supported_actions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Mapping of action capability keys to action definitions or handler strings",
    )
    action_descriptions: Dict[str, str] = Field(
        default_factory=dict,
        description="Action capability descriptions for semantic routing and LLM tool prompts",
    )
    action_parameters: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="JSON Schema dictionary for each supported action capability",
    )
    system_requirements: List[str] = Field(
        default_factory=list,
        description="CLI binaries or system utilities required prior to execution",
    )
    consumed_artifacts: List[str] = Field(
        default_factory=list,
        description="Input artifact types or extensions expected by this skill",
    )
    produced_artifacts: List[str] = Field(
        default_factory=list,
        description="Output artifact types or extensions produced by this skill",
    )

    @classmethod
    def get_clean_schema(cls) -> Dict[str, Any]:
        """Provides defensive schema export for core utils extraction compatibility."""
        return cls.model_json_schema()

    @staticmethod
    def _clean_identifier(role_str: Any) -> str:
        """Trims whitespace and extracts string value without case mutation or forced prefixes."""
        if not role_str:
            return ""
        return str(getattr(role_str, "value", role_str)).strip()

    @field_validator("primary_agent_id", mode="before")
    @classmethod
    def sanitize_primary_agent(cls, v: Any) -> str:
        """Sanitizes primary_agent_id into clean trimmed format."""
        cleaned = cls._clean_identifier(v)
        return cleaned or "system_generalist"

    @field_validator("allowed_agents", mode="before")
    @classmethod
    def sanitize_allowed_agents(cls, v: Any) -> List[str]:
        """Coerces strings/lists into trimmed agent identifier list format."""
        if isinstance(v, str):
            v = [v]
        if isinstance(v, list):
            res = []
            for agent in v:
                cleaned = cls._clean_identifier(agent)
                if cleaned:
                    res.append(cleaned)
            return res
        return v

    @field_validator("required_permissions", mode="before")
    @classmethod
    def coerce_string_to_list(cls, v: Any) -> Any:
        """Coerces single string entries into a standard list prior to schema validation."""
        if isinstance(v, str):
            return [v]
        return v

    @model_validator(mode="before")
    @classmethod
    def normalize_manifest_structure(cls, data: Any) -> Any:
        """
        Normalizes template nested action objects and legacy manifest structures.
        """
        if not isinstance(data, dict):
            return data

        # 1. Alias legacy 'actions' key -> 'supported_actions'
        if "actions" in data and "supported_actions" not in data:
            data["supported_actions"] = data.pop("actions")

        raw_actions = data.get("supported_actions", {})
        descriptions = data.setdefault("action_descriptions", {})
        parameters = data.setdefault("action_parameters", {})

        # 2. Parse Template Format: {"action_name": {"description": "...", "parameters": {...}}}
        if isinstance(raw_actions, dict):
            normalized_supported: Dict[str, Any] = {}
            for act_name, act_val in raw_actions.items():
                if isinstance(act_val, dict):
                    if "description" in act_val and act_name not in descriptions:
                        descriptions[act_name] = act_val["description"]
                    if "parameters" in act_val and act_name not in parameters:
                        parameters[act_name] = act_val.get("parameters", {})
                    handler = (
                        act_val.get("handler")
                        or act_val.get("handler_name")
                        or f"handle_{act_name}"
                    )
                    normalized_supported[act_name] = handler
                elif isinstance(act_val, str):
                    normalized_supported[act_name] = act_val

            data["supported_actions"] = normalized_supported

        # 3. Handle legacy list format: ['action1'] -> {'action1': 'handle_action1'}
        elif isinstance(raw_actions, list):
            data["supported_actions"] = {
                act: f"handle_{act}" for act in raw_actions if isinstance(act, str)
            }

        if "category" not in data or not data["category"]:
            data["category"] = "General"

        return data
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/skills/query.py`

```python
"""
charon/core/skills/query.py
System Version: v0.6.6 | File Revision: 7.3.0

Capability matching and tool schema generation mixin for SkillLibrarian.
Delegates database queries to SkillRepository & AgentRepository (DAL) and performs
physical executable checks to filter phantom/hallucinated skills.
Strictly enforces fail-fast role resolution.
"""

import logging
import os
import shutil
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

from charon.core.skills.roles import RoleResolutionError

logger = logging.getLogger("Charon.Core.Skills.Query")


class SkillQueryMixin:
    """Action queries, tool schema generation, and authorization checks for SkillLibrarian."""

    def is_agent_active(self, agent_name: str) -> bool:
        """
        Validates if an agent persona exists and is currently active in AgentRepository.
        Prevents Engine triage from falling back during role verification.
        """
        if not agent_name or not isinstance(agent_name, str):
            return False

        try:
            canonical_agent = self.resolve_agent_id_for_role(agent_name)
            if hasattr(self, "agent_repo"):
                return self.agent_repo.get_active_agent(canonical_agent) is not None
            return False
        except (RoleResolutionError, Exception) as err:
            logger.debug(f"[LIBRARIAN] Failed active check for agent '{agent_name}': {err}")
            return False

    @lru_cache(maxsize=128)
    def _check_requirement_cached(self, req_clean: str) -> bool:
        """Helper to cache disk binary and Python package resolution."""
        import importlib.metadata
        import importlib.util

        if shutil.which(req_clean) or os.path.exists(req_clean):
            return True

        try:
            importlib.metadata.distribution(req_clean)
            return True
        except importlib.metadata.PackageNotFoundError:
            pass

        try:
            mod_name = req_clean.replace("-", "_")
            if importlib.util.find_spec(mod_name) is not None:
                return True
        except Exception:
            pass

        return False

    def _is_physically_executable(self, action_dict: Dict[str, Any]) -> bool:
        """
        Validates that an action's backing entry file and system requirements exist.
        Filters out hallucinated or orphan DB entries added by unverified agents.
        """
        entry_path = action_dict.get("entry_file_path")
        if entry_path and isinstance(entry_path, str) and entry_path.strip():
            expanded_path = os.path.expanduser(os.path.expandvars(entry_path.strip()))
            if not os.path.exists(expanded_path):
                logger.warning(
                    f"[LIBRARIAN] Suppressing hallucinated skill '{action_dict.get('action_name')}': "
                    f"entry file missing on disk ('{entry_path}')"
                )
                return False

        sys_reqs = action_dict.get("system_requirements", [])
        if isinstance(sys_reqs, list):
            for req in sys_reqs:
                if isinstance(req, str) and req.strip():
                    req_clean = req.strip()
                    if not self._check_requirement_cached(req_clean):
                        logger.warning(
                            f"[LIBRARIAN] Suppressing unequipped skill '{action_dict.get('action_name')}': "
                            f"missing requirement '{req_clean}'"
                        )
                        return False
        return True

    def get_actions_for_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Retrieves active, unquarantined, and physically verified action metadata for an agent persona.
        Fails fast if agent_name cannot be resolved to an active agent in SQLite.
        """
        canonical_agent = self.resolve_agent_id_for_role(agent_name)
        actions_by_name: Dict[str, Dict[str, Any]] = {}

        # 1. Fetch database skills via DAL
        db_actions: List[Dict[str, Any]] = self.repo.get_skills_for_agent(canonical_agent)
        for act in db_actions:
            act_status = act.get("status", "ACTIVE") or "ACTIVE"
            act_name = act.get("action_name")
            if act_status.upper() == "ACTIVE" and act_name:
                actions_by_name[act_name] = act

        # 2. Merge in-memory registered skills matching agent permissions
        for act_name, skill in getattr(self, "_skills", {}).items():
            if act_name in actions_by_name:
                continue  # Avoid duplicate evaluation if already loaded from DB

            s_status = getattr(skill, "status", "ACTIVE") or "ACTIVE"
            if s_status.upper() != "ACTIVE":
                continue

            allowed = getattr(skill, "allowed_agents", []) or []
            if "*" in allowed or canonical_agent in allowed:
                actions_by_name[act_name] = {
                    "action_name": getattr(skill, "action_name", act_name),
                    "skill_id": getattr(skill, "skill_id", act_name),
                    "version": getattr(skill, "version", "1.0.0"),
                    "category": getattr(skill, "category", "general"),
                    "status": s_status,
                    "quarantine_reason": getattr(skill, "quarantine_reason", None),
                    "required_permissions": getattr(skill, "required_permissions", []),
                    "description": getattr(skill, "description", ""),
                    "parameters": getattr(skill, "parameters", {}),
                    "system_requirements": getattr(skill, "system_requirements", []),
                    "entry_file_path": getattr(skill, "entry_file_path", ""),
                    "handler_name": getattr(skill, "handler_name", "execute"),
                }

        # 3. Perform physical verification once on deduplicated list
        verified_actions: List[Dict[str, Any]] = []
        for act in actions_by_name.values():
            if self._is_physically_executable(act):
                verified_actions.append(act)

        return verified_actions

    def list_available_actions(self, agent_name: str) -> List[str]:
        """
        Lists active, unquarantined, verified dynamic skill actions accessible to an agent.
        """
        canonical_agent = self.resolve_agent_id_for_role(agent_name)
        db_actions = self.get_actions_for_agent(canonical_agent)

        actions: Set[str] = set()
        for act in db_actions:
            if isinstance(act, dict) and "action_name" in act:
                actions.add(act["action_name"])
            elif isinstance(act, str):
                actions.add(act)

        return sorted(list(actions))

    def get_agent_tool_schemas(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Generates OpenAI/Ollama-compliant Function Tool JSON specs for active agent skills.
        """
        canonical_agent = self.resolve_agent_id_for_role(agent_name)
        actions = self.get_actions_for_agent(canonical_agent)
        tool_schemas: List[Dict[str, Any]] = []

        agent_manifest = (
            self.get_agent_manifest(canonical_agent)
            if hasattr(self, "get_agent_manifest")
            else None
        )
        configured_tools = agent_manifest.get("tools", {}) if agent_manifest else {}

        for act in actions:
            if act.get("status", "ACTIVE").upper() != "ACTIVE":
                continue

            action_name = act["action_name"]

            if action_name in configured_tools:
                tool_cfg = configured_tools[action_name]
                if isinstance(tool_cfg, dict) and not tool_cfg.get("enabled", True):
                    continue

            params = act.get("parameters", {})
            if not isinstance(params, dict):
                params = {}

            if "properties" not in params and "type" not in params:
                formatted_params = {
                    "type": "object",
                    "properties": params,
                    "required": [
                        p_name
                        for p_name, p_info in params.items()
                        if isinstance(p_info, dict) and p_info.get("required") is True
                    ],
                }
            else:
                formatted_params = params
                if "type" not in formatted_params:
                    formatted_params["type"] = "object"

            tool_schemas.append({
                "type": "function",
                "function": {
                    "name": action_name,
                    "description": act.get("description", f"Executes '{action_name}'"),
                    "parameters": formatted_params,
                },
            })

        return tool_schemas

    def is_skill_available(self, action: str, agent_name: str) -> bool:
        """
        Checks if an agent is authorized for an active, unquarantined, and verified skill.
        """
        canonical_agent = self.resolve_agent_id_for_role(agent_name)
        available_actions = self.list_available_actions(canonical_agent)

        if action in available_actions:
            details = self.get_action_details(action)
            if details:
                sys_reqs = details.get("system_requirements", [])
                return (
                    self.verify_system_requirements(sys_reqs)
                    if hasattr(self, "verify_system_requirements")
                    else True
                )

        return False

    def get_action_details(self, action_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves full action specification record directly via SkillRepository."""
        return self.repo.get_skill_by_action(action_name)

    def find_matching_action(
        self, query: str, agent_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Performs keyword matching against active, verified DB-indexed actions fetched from DAL."""
        query_lower = query.lower().strip()
        best_match: Optional[Dict[str, Any]] = None
        highest_score = 0.0

        if agent_name:
            canonical_agent = self.resolve_agent_id_for_role(agent_name)
            actions = self.get_actions_for_agent(canonical_agent)
        else:
            raw_actions = self.repo.get_all_active_skills()
            actions = [a for a in raw_actions if self._is_physically_executable(a)]

        for r_dict in actions:
            if r_dict.get("status", "ACTIVE").upper() != "ACTIVE":
                continue

            act_name = r_dict.get("action_name", "")
            skill_id = r_dict.get("skill_id", "")
            desc = (r_dict.get("description") or "").lower()

            score = 0.0
            if act_name.lower() in query_lower or query_lower in act_name.lower():
                score += 0.9
            elif skill_id.lower() in query_lower:
                score += 0.7

            overlap = set(desc.split()).intersection(set(query_lower.split()))
            if overlap:
                score += min(0.6, len(overlap) * 0.15)

            if score > highest_score and score >= 0.4:
                highest_score = score
                best_match = {
                    "action_name": act_name,
                    "skill_id": skill_id,
                    "description": r_dict.get("description"),
                    "entry_file_path": r_dict.get("entry_file_path"),
                    "match_score": round(score, 2),
                }

        return best_match
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/skills/roles.py`

```python
"""
charon/core/skills/roles.py
System Version: v0.6.3 | File Revision: 9.0.0

Strict database-driven role resolution and entrypoint discovery mixin for SkillLibrarian.
No in-memory fallback dictionaries. No string-stripping heuristics.
The database is the single source of truth. Unmapped roles raise RoleResolutionError immediately.
"""

import logging
from typing import Dict

from charon.db.repositories import RoleRepository

logger = logging.getLogger("Charon.Core.Skills.Roles")


class RoleResolutionError(KeyError):
    """Raised when a requested role cannot be resolved directly from the database registry."""
    pass


class RoleResolverMixin:
    """Strict DB-backed role normalization, canonical ID resolution, and entrypoint lookup mixin."""

    @property
    def _role_repo(self) -> RoleRepository:
        """Lazily provisions and caches the repository using the instance's db_path."""
        if not hasattr(self, "_cached_role_repo") or self._cached_role_repo is None:
            self._cached_role_repo = RoleRepository(getattr(self, "db_path", None))
        return self._cached_role_repo

    def _normalize_role_key(self, raw_role: str) -> str:
        """Normalizes raw role input string by trimming whitespace and lowercasing."""
        if not raw_role:
            return ""
        return raw_role.strip().lower()

    def get_default_agent_id(self) -> str:
        """
        Queries the database for the designated default system fallback agent.
        Hard-fails if the database query returns no default agent.
        """
        agent_id = self._role_repo.get_default_agent_id()
        if agent_id:
            return agent_id

        raise RoleResolutionError(
            "[LIBRARIAN] Critical Registry Failure: No default system agent configured in database."
        )

    def validate_core_roles(self) -> bool:
        """
        Validates that all required system roles are explicitly mapped to active agents in SQLite.
        Strictly read-only database query.
        """
        rows = self._role_repo.get_core_roles_status()
        if not rows:
            logger.error("[LIBRARIAN] Core role validation failed: `system_roles` table returned no records.")
            return False

        all_valid = True
        for role_name, agent_id, is_active in rows:
            if not agent_id or not is_active:
                logger.error(
                    f"[LIBRARIAN] Invalid database state: Role '{role_name}' is unmapped or mapped to an inactive agent ('{agent_id}')."
                )
                all_valid = False

        return all_valid

    def resolve_agent_id_for_role(self, role_input: str) -> str:
        """
        Queries the database directly for the agent_id bound to the given role.

        HARD FAIL: Raises `RoleResolutionError` immediately if input is blank or unmapped in DB.
        """
        if not role_input or not str(role_input).strip():
            raise RoleResolutionError("[LIBRARIAN] Role lookup rejected: Empty or missing role input.")

        norm = self._normalize_role_key(role_input)

        # Single Source of Truth: Database lookup
        resolved_id = self._role_repo.get_agent_id_for_role(norm)
        if resolved_id:
            return resolved_id

        # HARD FAIL: No in-memory guessing, no default fallback
        raise RoleResolutionError(
            f"[LIBRARIAN] Unresolvable Role: '{role_input}' (normalized: '{norm}') "
            f"has no active agent binding in the database."
        )

    def resolve_role(self, role_input: str) -> str:
        """Alias method for role resolution compatibility."""
        return self.resolve_agent_id_for_role(role_input)

    def get_agent_entrypoint(self, agent_id: str) -> Dict[str, str]:
        """
        Retrieves the Python module path and class name for a database-validated agent.
        Raises RoleResolutionError if the agent has no entrypoint in DB.
        """
        canonical_id = self.resolve_agent_id_for_role(agent_id)

        entrypoint_data = self._role_repo.get_agent_entrypoint_data(canonical_id)

        if entrypoint_data and entrypoint_data.get("module") and entrypoint_data.get("class_name"):
            return entrypoint_data

        if entrypoint_data is not None:
            class_name = "".join(part.capitalize() for part in canonical_id.split("_")) + "Agent"
            return {
                "module": f"charon.agents.{canonical_id}",
                "class_name": class_name,
            }

        raise RoleResolutionError(
            f"[LIBRARIAN] Entrypoint Resolution Failure: No module/class registered for canonical agent '{canonical_id}'."
        )

    def get_display_name_for_agent(self, agent_id: str) -> str:
        """Retrieves human-readable display_name for an agent directly from DB."""
        canonical_id = self.resolve_agent_id_for_role(agent_id)

        display_name = self._role_repo.get_agent_display_name(canonical_id)
        if display_name:
            return display_name

        raise RoleResolutionError(
            f"[LIBRARIAN] Display Name Failure: Agent '{canonical_id}' has no display name in database."
        )
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/skills/routes.py`

```python
"""
charon/core/skills/routes.py
System Version: v0.6.3 | File Revision: 7.0.0

Route lifecycle, provenance resolution, and operational telemetry tracking mixin for SkillLibrarian.
Enforces CBAC Schema V2 routing constraints and quarantine state filtering.
Enforces direct repository delegation without defensive hasattr checks.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("Charon.Core.Skills.Routes")


class RouteManagerMixin:
    """Route Provenance and Telemetry management for SkillLibrarian."""

    def resolve_route(self, action_or_route: str) -> Optional[Dict[str, Any]]:
        """
        Queries RouteRepository for route provenance and operational status.
        Precedence: USER_OVERRIDE > SYSTEM > DYNAMIC_AUTO > FALLBACK
        Filters out quarantined or inactive routes.
        """
        if not action_or_route:
            return None

        clean_trigger = action_or_route.strip().lower()

        try:
            route = self.route_repo.get_route(clean_trigger)
            if route and route.get("is_active", True):
                status = str(route.get("status", "ACTIVE")).upper()
                if status == "ACTIVE":
                    return route
        except Exception as e:
            logger.error(
                f"[LIBRARIAN] Error resolving route '{action_or_route}': {e}"
            )
        return None

    def record_route_execution(self, route_id: str) -> None:
        """Updates route operational telemetry (execution_count & last_executed_at)."""
        if not route_id:
            return

        try:
            self.route_repo.record_execution(route_id)
        except Exception as e:
            logger.warning(
                f"[LIBRARIAN] Telemetry update failed for route '{route_id}': {e}"
            )
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/state.py`

```python
"""
charon/core/state.py
System Version: v0.3.3 | File Revision: 1.4.0

Module: Persistent Task State Machine & Idle Ticker Feed Coordinator
Tracks task execution status, execution plans, step outputs, Gatekeeper approval state,
and idle notification ticker items across daemon restarts via DAL Repositories.
Adheres to the Janitorial Working Anchor by enforcing role-aware metadata & resilient state transitions.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import uuid

from charon.config.paths import STATE_DB_PATH
from charon.db.repositories import TaskRepository, TickerRepository

logger = logging.getLogger("Charon.Core.State")


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StateManager:
    """Thread-safe state machine wrapper coordinating persistence via DAL Repositories."""

    def __init__(self, db_path: Optional[Union[Path, str]] = None) -> None:
        # 1. Fallback to canonical STATE_DB_PATH if not provided
        target_path = Path(db_path) if db_path else STATE_DB_PATH

        # 2. Janitorial Guard: Protect against directory paths passed by callers
        if target_path.is_dir():
            logger.warning(
                f"StateManager received directory path '{target_path}'. "
                f"Auto-correcting to STATE_DB_PATH '{STATE_DB_PATH}'."
            )
            target_path = STATE_DB_PATH

        self.db_path = target_path
        self.task_repo = TaskRepository(self.db_path)
        self.ticker_repo = TickerRepository(self.db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize state tables via repositories."""
        try:
            self.task_repo.ensure_schema()
            self.ticker_repo.ensure_schema()
            logger.info(
                f"StateManager initialized with DAL repositories at: {self.db_path}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize state database schema at '{self.db_path}': {e}")
            raise

    # --------------------------------------------------------------------------
    # Task Management Methods
    # --------------------------------------------------------------------------

    async def create_task(
        self,
        task_id: str,
        prompt: str,
        client_id: Optional[str] = None,
        agent_override: Optional[str] = None,
        target_role: Optional[str] = None,
        action_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Insert new task entry into state ledger.

        Janitorial Working Anchor Compliance:
        - Normalizes role-based abstractions (`target_role` vs `agent_override`).
        - Captures `action_name` for dynamic route auditing.
        """
        # Preserve Janitorial Role Abstraction across parameter aliases
        effective_role = agent_override or target_role or kwargs.get("action")
        effective_action = action_name or kwargs.get("action_name") or kwargs.get("action")

        await asyncio.to_thread(
            self.task_repo.create_task,
            task_id=task_id,
            prompt=prompt,
            status=TaskStatus.PENDING.value,
            client_id=client_id,
            agent_override=effective_role,
        )

        return {
            "task_id": task_id,
            "status": TaskStatus.PENDING.value,
            "prompt": prompt,
            "client_id": client_id,
            "agent_override": effective_role,
            "target_role": target_role or effective_role,
            "action_name": effective_action,
        }

    async def update_status(
        self,
        task_id: str,
        status: Union[TaskStatus, str],
        error_message: Optional[str] = None,
        approval_id: Optional[str] = None,
    ) -> None:
        """Update task status and associated error or approval metadata safely."""
        status_val = status.value if isinstance(status, Enum) else str(status)

        await asyncio.to_thread(
            self.task_repo.update_status,
            task_id=task_id,
            status=status_val,
            error_message=error_message,
            approval_id=approval_id,
        )

    async def save_plan(
        self, task_id: str, plan_steps: List[Dict[str, Any]]
    ) -> None:
        """Persist generated orchestration execution plan with resilient JSON encoding."""
        try:
            plan_str = json.dumps(plan_steps, default=str)
        except Exception as e:
            logger.error(f"Failed to serialize plan steps for task '{task_id}': {e}")
            plan_str = json.dumps([{"error": "Serialization failed", "details": str(e)}])

        await asyncio.to_thread(
            self.task_repo.save_plan,
            task_id=task_id,
            plan_str=plan_str,
            total_steps=len(plan_steps),
        )

    async def update_step_progress(
        self,
        task_id: str,
        step_index: int,
        step_results: Dict[str, Any],
    ) -> None:
        """Update current step execution progress and store step output results."""
        try:
            results_str = json.dumps(step_results, default=str)
        except Exception as e:
            logger.error(f"Failed to serialize step results for task '{task_id}': {e}")
            results_str = json.dumps({"error": "Serialization failed", "details": str(e)})

        await asyncio.to_thread(
            self.task_repo.update_step_progress,
            task_id=task_id,
            step_index=step_index,
            results_str=results_str,
        )

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve task state dictionary by ID."""
        return await asyncio.to_thread(self.task_repo.get_task, task_id)

    async def get_unfinished_tasks(self) -> List[Dict[str, Any]]:
        """Fetch tasks interrupted during RUNNING or AWAITING_APPROVAL states for crash recovery."""
        target_statuses = [
            TaskStatus.PENDING.value,
            TaskStatus.RUNNING.value,
            TaskStatus.AWAITING_APPROVAL.value,
        ]
        return await asyncio.to_thread(
            self.task_repo.get_unfinished_tasks, target_statuses
        )

    # --------------------------------------------------------------------------
    # Idle Notification Ticker Methods
    # --------------------------------------------------------------------------

    async def add_ticker_item(
        self,
        message: str,
        category: str = "COMPLETED_TASK",
        ttl_minutes: int = 120,
    ) -> str:
        """Add a notification ticker item to be displayed in top bar during daemon idle state."""
        item_id = f"tick-{uuid.uuid4().hex[:6]}"
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=ttl_minutes)

        await asyncio.to_thread(
            self.ticker_repo.add_ticker_item,
            item_id=item_id,
            category=category,
            message=message,
            created_at_iso=now.isoformat(),
            expires_at_iso=expires.isoformat(),
        )
        logger.debug(
            f"Added idle ticker item [{item_id}]: '{message}' ({category})"
        )
        return item_id

    async def get_active_ticker_items(
        self, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Fetch undismissed and non-expired ticker items for heartbeat rotation."""
        now_iso = datetime.now(timezone.utc).isoformat()
        return await asyncio.to_thread(
            self.ticker_repo.get_active_ticker_items,
            now_iso=now_iso,
            limit=limit,
        )

    async def dismiss_ticker_item(self, item_id: str) -> None:
        """Dismiss a ticker item so it no longer appears in top bar rotations."""
        await asyncio.to_thread(self.ticker_repo.dismiss_ticker_item, item_id)
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/utils.py`

```python
"""
charon/core/utils.py
System Version: v0.3.3 | File Revision: 3.0.0

Module: Utility routines for JSON sanitization, dynamic agent ID normalization,
and defensive Pydantic schema extraction adhering to the Janitorial Working Anchor.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("Charon.Core.Utils")


def clean_json_string(raw_str: str) -> str:
    """
    Safely extracts and cleans raw JSON strings (objects or arrays) from LLM responses.
    Handles markdown code blocks, greedy fence artifacts, and trailing commas.
    """
    if not raw_str:
        return ""

    raw_str = raw_str.strip()

    # 1. Strip markdown code fences if present (non-greedy)
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_str, re.IGNORECASE)
    if fence_match:
        raw_str = fence_match.group(1).strip()
    else:
        # 2. Extract outermost JSON object {} or array [] structure
        bracket_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", raw_str)
        if bracket_match:
            raw_str = bracket_match.group(1).strip()

    # 3. Clean trailing commas before closing braces or brackets
    raw_str = re.sub(r",\s*([\}\]])", r"\1", raw_str)

    return raw_str


def normalize_agent_id(agent: Any) -> str:
    """
    Sanitizes and normalizes raw agent/role identifier strings.
    Strips surrounding quotes, markdown formatting, brackets, and LLM prefixes.
    """
    if not agent:
        return ""

    agent_str = str(agent).strip()

    # Strip quotes, brackets, angle brackets, and markdown backticks
    agent_str = re.sub(r"^[`'\"\[\(<]+|[`'\"\]\)>]+$", "", agent_str).strip()

    # Strip common LLM artifact prefixes (e.g., 'agent:', 'role:')
    if agent_str.lower().startswith(("agent:", "role:")):
        agent_str = agent_str.split(":", 1)[1].strip()

    return agent_str.lower()


def normalize_agent(agent: Any) -> str:
    """Backward-compatible function returning a sanitized string agent identifier."""
    return normalize_agent_id(agent)


def get_schema_json(schema_class: type) -> Dict[str, Any]:
    """
    Defensively retrieves JSON schema dict from payload classes across Pydantic versions.
    Fallback chain: custom get_clean_schema() -> Pydantic v2 model_json_schema() -> Pydantic v1 schema().
    """
    if not schema_class:
        return {}

    try:
        if hasattr(schema_class, "get_clean_schema") and callable(
            getattr(schema_class, "get_clean_schema")
        ):
            return schema_class.get_clean_schema()

        if hasattr(schema_class, "model_json_schema") and callable(
            getattr(schema_class, "model_json_schema")
        ):
            return schema_class.model_json_schema()

        if hasattr(schema_class, "schema") and callable(
            getattr(schema_class, "schema")
        ):
            return schema_class.schema()
    except Exception as e:
        logger.warning(f"[UTILS] Failed to extract schema from {schema_class}: {e}")

    return {}
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/version.py`

```python
"""
charon/core/version.py
System Version: v0.3.3 | File Revision: 2.0.0

Module: Runtime Git metadata extraction and SemVer context adhering to the
Janitorial Working Anchor.
"""

import logging
from pathlib import Path
import subprocess
from typing import Any, Dict

try:
    from charon.__version__ import __version__
except ImportError:
    __version__ = "0.3.3"

logger = logging.getLogger("Charon.Core.Version")

SUBPROCESS_TIMEOUT_SECONDS = 3


def get_git_revision(repo_root: Path | None = None) -> Dict[str, Any]:
    """
    Defensively extracts Git revision metadata (commit SHA, branch, dirty status).
    Handles non-git environments, timeouts, and missing subprocess binaries cleanly.
    """
    if repo_root is None:
        # charon/core/version.py -> parents[2] resolves to repository root
        repo_root = Path(__file__).resolve().parents[2]

    metadata: Dict[str, Any] = {
        "version": __version__,
        "git_sha": "uncommitted_workspace",
        "git_branch": "unknown",
        "is_dirty": False,
    }

    git_dir = repo_root / ".git"
    if not git_dir.exists():
        logger.debug(f"[VERSION] No .git directory found at '{repo_root}'. Skipping git rev-parse.")
        return metadata

    try:
        # 1. Get short commit hash
        sha_res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        metadata["git_sha"] = sha_res.stdout.strip()

        # 2. Get current branch name
        branch_res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        metadata["git_branch"] = branch_res.stdout.strip()

        # 3. Check workspace dirty status
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        metadata["is_dirty"] = len(status_res.stdout.strip()) > 0

    except FileNotFoundError:
        logger.warning("[VERSION] 'git' executable not found in system PATH.")
    except subprocess.TimeoutExpired:
        logger.warning(f"[VERSION] Git metadata extraction timed out (> {SUBPROCESS_TIMEOUT_SECONDS}s).")
    except subprocess.CalledProcessError as e:
        logger.debug(f"[VERSION] Git command failed: {e}")
    except Exception as e:
        logger.warning(f"[VERSION] Unexpected error extracting Git revision: {e}")

    return metadata


def get_version_string() -> str:
    """
    Returns a canonical runtime version string (e.g., 'v0.3.3-ga21c3ef (dirty)').
    Normalizes leading version prefixes to avoid duplicate 'v' formatting.
    """
    meta = get_git_revision()
    clean_version = str(meta["version"]).lstrip("vV")
    version_str = f"v{clean_version}"

    if meta["git_sha"] != "uncommitted_workspace":
        version_str += f"-g{meta['git_sha']}"
    if meta["is_dirty"]:
        version_str += " (dirty)"

    return version_str
```

────────────────────────────────────────────────────────────────────────────────

## Target File: `charon/core/workspace.py`

```python
"""
charon/core/workspace.py
System Version: v0.3.3 | File Revision: 2.0.0

Module: Isolated Task Workspace Manager.
Manages scoped directory sandboxes for execution tasks, preventing directory traversal
and cross-task workspace leaks adhering strictly to the Janitorial Working Anchor.
"""

import logging
from pathlib import Path
import shutil
from typing import List, Optional, Union

try:
    from charon.config.paths import DATA_DIR
except ImportError:
    from charon.config import DATA_DIR

logger = logging.getLogger("Charon.Core.Workspace")


class WorkspaceSecurityError(PermissionError):
    """Raised when a workspace operation attempts to escape its directory sandbox boundary."""
    pass


class WorkspaceManager:
    """Manages scoped task directory creation, file staging, and path isolation."""

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir: Path = (root_dir or (DATA_DIR / "workspaces")).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[WORKSPACE] Initialized sandbox root at: {self.root_dir}")

    def get_task_workspace(self, task_id: str, create: bool = True) -> Path:
        """
        Returns the absolute path for a task's workspace.
        Ensures the directory exists and stays within root boundary.
        """
        safe_task_id = "".join(c for c in str(task_id) if c.isalnum() or c in ("_", "-"))
        if not safe_task_id:
            raise ValueError(f"Invalid task_id string for workspace creation: '{task_id}'")

        workspace_path = (self.root_dir / safe_task_id).resolve()

        # Verify workspace remains strictly inside root_dir and is not root_dir itself
        self._verify_path_contained(workspace_path, boundary=self.root_dir)
        if workspace_path == self.root_dir:
            raise WorkspaceSecurityError("Task workspace cannot be identical to root sandbox directory.")

        if create:
            workspace_path.mkdir(parents=True, exist_ok=True)

        return workspace_path

    def _verify_path_contained(self, target_path: Path, boundary: Optional[Path] = None) -> None:
        """Guards against directory traversal by verifying target is inside the specified boundary."""
        limit = boundary.resolve() if boundary else self.root_dir
        resolved = target_path.resolve()

        try:
            resolved.relative_to(limit)
        except ValueError:
            raise WorkspaceSecurityError(
                f"Path traversal blocked: '{target_path}' escapes workspace boundary '{limit}'"
            )

    def write_file(self, task_id: str, relative_filename: str, content: Union[str, bytes]) -> Path:
        """Write text or bytes content safely into a file within the task's isolated workspace."""
        workspace = self.get_task_workspace(task_id, create=True)
        target_path = (workspace / relative_filename).resolve()

        # Enforce boundary containment strictly against THIS task's workspace
        self._verify_path_contained(target_path, boundary=workspace)

        target_path.parent.mkdir(parents=True, exist_ok=True)

        mode = "wb" if isinstance(content, bytes) else "w"
        encoding = None if isinstance(content, bytes) else "utf-8"

        with open(target_path, mode, encoding=encoding) as f:
            f.write(content)

        logger.debug(f"[WORKSPACE] Wrote file in workspace '{task_id}': {relative_filename}")
        return target_path

    def read_file(self, task_id: str, relative_filename: str) -> str:
        """Read text file safely from within a task workspace."""
        workspace = self.get_task_workspace(task_id, create=False)
        target_path = (workspace / relative_filename).resolve()

        self._verify_path_contained(target_path, boundary=workspace)

        if not target_path.exists():
            raise FileNotFoundError(
                f"File '{relative_filename}' not found in task workspace '{task_id}'"
            )

        return target_path.read_text(encoding="utf-8")

    def read_bytes(self, task_id: str, relative_filename: str) -> bytes:
        """Read binary file safely from within a task workspace."""
        workspace = self.get_task_workspace(task_id, create=False)
        target_path = (workspace / relative_filename).resolve()

        self._verify_path_contained(target_path, boundary=workspace)

        if not target_path.exists():
            raise FileNotFoundError(
                f"File '{relative_filename}' not found in task workspace '{task_id}'"
            )

        return target_path.read_bytes()

    def file_exists(self, task_id: str, relative_filename: str) -> bool:
        """Checks if a file exists within a task workspace without throwing an exception."""
        try:
            workspace = self.get_task_workspace(task_id, create=False)
            target_path = (workspace / relative_filename).resolve()
            self._verify_path_contained(target_path, boundary=workspace)
            return target_path.exists() and target_path.is_file()
        except Exception:
            return False

    def list_files(self, task_id: str) -> List[Path]:
        """List all relative file paths inside a task workspace."""
        workspace = self.get_task_workspace(task_id, create=False)
        if not workspace.exists():
            return []

        return [
            p.relative_to(workspace)
            for p in workspace.rglob("*")
            if p.is_file()
        ]

    def cleanup_workspace(self, task_id: str) -> bool:
        """Delete task workspace directory and all contained assets."""
        try:
            workspace = self.get_task_workspace(task_id, create=False)
            if workspace.exists():
                shutil.rmtree(workspace)
                logger.info(f"[WORKSPACE] Purged task workspace directory for '{task_id}'")
                return True
            return False
        except Exception as e:
            logger.error(f"[WORKSPACE] Failed to cleanup task workspace for '{task_id}': {e}")
            return False
```

────────────────────────────────────────────────────────────────────────────────

