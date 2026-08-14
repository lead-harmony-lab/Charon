"""
charon/ux/concierge.py
System Version: v2.0.0

Module: Post-execution proactive concierge assistant for Charon.
Provides LLM-driven proactive follow-up proposals using strict Pydantic structured outputs.
"""

import logging
import re
from typing import Any, Dict, Optional, Set
from pydantic import BaseModel, Field, ValidationInfo, model_validator, ValidationError

logger = logging.getLogger("Charon.UX.Concierge")

EXIT_PHRASES: Set[str] = {
    "that will be all", "thanks", "thank you", "done", "stop", "exit",
    "quit", "nothing else", "goodbye", "n/a", "no", "no thanks",
    "all good", "that is all", "that's all",
}

TRIVIAL_QUERY_PATTERNS = [
    re.compile(r"^(display|show|get|check|print)?\s*(the)?\s*(current)?\s*(system)?\s*(time|date|clock|uptime|whoami|hostname|pwd)\s*$", re.IGNORECASE),
    re.compile(r"^(time|date|whoami|uptime|pwd|hostname)$", re.IGNORECASE),
]

CONCIERGE_SYSTEM_PROMPT = """
You are Charon's Proactive Concierge Engine.
Analyze the completed user task, execution result, and blackboard artifacts to determine a logical, high-value follow-up action.

1. 'phrase' must be formal, polite, and executive ("Shall I...", "Would you like me to...").
2. 'suggested_prompt' MUST be an explicit natural language instruction.
3. If no grounded follow-up makes sense, or the task was trivial, return null/empty.
"""

class ConciergeProposal(BaseModel):
    """Pydantic schema representing a structured proactive suggestion."""
    phrase: str = Field(..., description="Formal, polite, executive phrasing for the proposal.")
    suggested_prompt: str = Field(..., description="High-intent natural language instruction for the next step.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score that this proposal is logical and helpful.")

    @model_validator(mode='after')
    def validate_guardrails(self, info: ValidationInfo) -> 'ConciergeProposal':
        """Enforces anti-looping, placeholder rejection, and scope grounding via validation context."""
        context = info.context or {}
        user_query = context.get("user_query", "").lower()
        full_corpus = context.get("full_corpus", "").lower()

        combined = f"{self.phrase} {self.suggested_prompt}".lower()
        norm_suggested = re.sub(r"[\s\-_/~.]+", " ", self.suggested_prompt.lower()).strip()
        norm_query = re.sub(r"[\s\-_/~.]+", " ", user_query).strip()

        # 1. Minimum Confidence Check
        min_conf = context.get("min_confidence", 0.7)
        if self.confidence < min_conf:
            raise ValueError(f"Confidence {self.confidence} is below minimum {min_conf}.")

        # 2. Reject unresolved placeholders
        invalid_placeholders = ["{", "}", "active project", "yourusername", "example_dir"]
        if any(ph in combined for ph in invalid_placeholders):
            raise ValueError("Proposal contains unresolved template placeholders.")

        # 3. Anti-Looping: Do not repeat the executed query
        if norm_suggested and (norm_suggested == norm_query or norm_suggested in norm_query):
            raise ValueError("Proposal is redundant and matches the executed query.")

        # 4. Strict Grounding: Proposed paths must exist in context
        suggested_paths = re.findall(r"(?:~|/home/[^/\s]+|/[a-zA-Z0-9_\-.]+)+/[a-zA-Z0-9_\-./]+", self.suggested_prompt)
        for p in suggested_paths:
            clean_p = p.rstrip("/").lower()
            base_p = clean_p.split("/")[-1]
            if clean_p not in full_corpus and base_p not in full_corpus:
                raise ValueError(f"Ungrounded path hallucination detected: {p}")

        return self


class ConciergeService:
    """Evaluates task execution state to generate contextual next-step proposals."""

    def __init__(self, llm_client: Any, model_name: str = "llama3.1", min_confidence: float = 0.7):
        self.client = llm_client
        self.model_name = model_name
        self.min_confidence = min_confidence

    async def get_next_step(
        self,
        user_query: str,
        completed_action: str,
        execution_result: str,
        blackboard_artifacts: str = "",
    ) -> Optional[ConciergeProposal]:
        """Evaluates completed tasks and returns a validated Pydantic proposal."""

        clean_query = user_query.strip().lower().rstrip(".!")

        # 1. Early Exits (Dismissals and Trivial Queries)
        if clean_query in EXIT_PHRASES:
            logger.debug("Exit phrase detected. Suppressing proposal.")
            return None

        if any(pattern.match(clean_query) for pattern in TRIVIAL_QUERY_PATTERNS):
            logger.debug("Trivial query detected. Suppressing proposal.")
            return None

        # 2. Construct State Context
        user_content = (
            f"USER QUERY: {user_query}\n"
            f"EXECUTED ACTION: {completed_action}\n"
            f"BLACKBOARD STATE:\n{blackboard_artifacts}\n"
            f"RESULT OUTPUT:\n{execution_result[:1500]}"
        )

        full_corpus = f"{user_query} {execution_result} {blackboard_artifacts}"

        try:
            # 3. Request Structured Output (Assuming client supports native structured outputs)
            response_data = await self.client.generate_structured(
                model=self.model_name,
                system=CONCIERGE_SYSTEM_PROMPT,
                prompt=user_content,
                response_format=ConciergeProposal.model_json_schema()
            )

            if not response_data:
                return None

            # 4. Hydrate and Validate via Pydantic
            proposal = ConciergeProposal.model_validate(
                response_data,
                context={
                    "user_query": user_query,
                    "full_corpus": full_corpus,
                    "min_confidence": self.min_confidence
                }
            )

            logger.info(f"Proposal accepted: {proposal.phrase} -> '{proposal.suggested_prompt}'")
            return proposal

        except ValidationError as ve:
            # Pydantic caught a guardrail violation (e.g., looping, hallucinations)
            logger.warning(f"Concierge proposal rejected by guardrails: {ve.errors()[0]['msg']}")
            return None
        except Exception as e:
            logger.error(f"Failed to generate dynamic proposal: {e}")
            return None