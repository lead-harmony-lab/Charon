"""
charon/concierge/schemas.py
System Version: v2.2.0

Module: Concierge Data Structures
Provides Pydantic models and strict validation guardrails for LLM outputs.
"""

import re
from typing import Optional
from pydantic import BaseModel, Field, ValidationInfo, model_validator

def _levenshtein_ratio(s1: str, s2: str) -> float:
    """Calculates semantic similarity ratio between 0.0 and 1.0 using Levenshtein distance."""
    if not s1 or not s2:
        return 0.0
    if len(s1) < len(s2):
        return _levenshtein_ratio(s2, s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    distance = previous_row[-1]
    max_len = max(len(s1), len(s2))
    return 1.0 - (distance / max_len)


class ConciergeProposal(BaseModel):
    """Pydantic schema representing a structured proactive suggestion."""
    phrase: str = Field(..., description="Formal, polite, executive phrasing for the proposal.")
    suggested_prompt: str = Field(..., description="High-intent natural language instruction for the next step.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score that this proposal is logical and helpful.")

    @model_validator(mode='after')
    def validate_guardrails(self, info: ValidationInfo) -> 'ConciergeProposal':
        context = info.context or {}
        user_query = context.get("user_query", "").lower()
        full_corpus = context.get("full_corpus", "").lower()

        combined = f"{self.phrase} {self.suggested_prompt}".lower()
        norm_suggested = re.sub(r"[\s\-_/~.]+", " ", self.suggested_prompt.lower()).strip()
        norm_query = re.sub(r"[\s\-_/~.]+", " ", user_query).strip()

        min_conf = context.get("min_confidence", 0.7)
        if self.confidence < min_conf:
            raise ValueError(f"Confidence {self.confidence} is below minimum {min_conf}.")

        invalid_placeholders = ["{", "}", "active project", "yourusername", "example_dir"]
        if any(ph in combined for ph in invalid_placeholders):
            raise ValueError("Proposal contains unresolved template placeholders.")

        similarity = _levenshtein_ratio(norm_suggested, norm_query)
        if similarity > 0.65 or norm_suggested in norm_query or norm_query in norm_suggested:
            raise ValueError(f"Proposal is redundant (Similarity: {similarity:.2f}). Matches executed query.")

        suggested_paths = re.findall(r"(?:~|/home/[^/\s]+|/[a-zA-Z0-9_\-.]+)+/[a-zA-Z0-9_\-./]+", self.suggested_prompt)
        for p in suggested_paths:
            clean_p = p.rstrip("/").lower()
            base_p = clean_p.split("/")[-1]
            if clean_p not in full_corpus and base_p not in full_corpus:
                raise ValueError(f"Ungrounded path hallucination detected: {p}")
        return self


class ConciergeResponse(BaseModel):
    """Parent schema providing an escape hatch to prevent forced hallucinations."""
    has_proposal: bool = Field(..., description="Set to false if no logical follow-up exists.")
    proposal: Optional[ConciergeProposal] = Field(None, description="The proposal details, if applicable.")