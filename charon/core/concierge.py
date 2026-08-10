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