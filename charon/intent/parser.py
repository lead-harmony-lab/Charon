"""
charon/intent/parser.py
System Version: v0.1.0 | File Revision: 2.2.0

Module: Pass 1 Router Engine evaluating hard shortcuts, per-agent triggers, and priority scaling.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from charon.core.skills import SkillLibrarian
from charon.intent.routing import RoutingPayload
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

logger = logging.getLogger("Charon.Intent.Parser")


class IntentParser:
    """Evaluates shortcut dispatches, manages dynamic routing rules, and scales LLM triage confidence scores."""

    def __init__(
        self,
        librarian: Optional[SkillLibrarian] = None,
        ollama_client: Optional[Any] = None,
        **kwargs: Any,
    ):
        self.librarian = librarian or SkillLibrarian.get_instance()
        self.ollama_client = ollama_client
        self.extra_config = kwargs

    async def parse(
        self, prompt: str, context: Optional[Dict[str, Any]] = None
    ) -> RoutingPayload:
        """High-level async intent parsing interface for Orchestrator."""
        shortcut = self.check_hard_shortcuts(prompt)
        if shortcut:
            return RoutingPayload(agent=shortcut)

        return RoutingPayload(agent="coordinator")

    def parse_sync(
        self, prompt: str, context: Optional[Dict[str, Any]] = None
    ) -> RoutingPayload:
        """High-level sync intent parsing interface for Orchestrator."""
        shortcut = self.check_hard_shortcuts(prompt)
        if shortcut:
            return RoutingPayload(agent=shortcut)

        return RoutingPayload(agent="coordinator")

    def check_hard_shortcuts(self, prompt: str) -> Optional[str]:
        """
        Evaluates user prompts against global route table rules and per-agent trigger keywords.
        Returns target_agent ID if matched, or None.
        """
        clean_prompt = prompt.strip().lower()

        # 1. Check global dynamic routing override rules in RouteRepository
        try:
            override_rules = self.get_override_rules()
            for rule in override_rules:
                trigger = rule.get("trigger", "").lower()
                if clean_prompt.startswith(trigger) or trigger in clean_prompt.split():
                    logger.info(
                        f"[IntentParser] Matched dynamic shortcut: '{trigger}' -> '{rule.get('target_agent')}'"
                    )
                    return rule.get("target_agent")
        except Exception as err:
            logger.warning(
                f"[IntentParser] Dynamic shortcut evaluation error: {err}"
            )

        # 2. Check per-agent trigger words from AgentRepository manifests
        try:
            if hasattr(self.librarian, "agent_repo") and self.librarian.agent_repo:
                manifests = self.librarian.agent_repo.get_all_manifests()
                for agent_id, manifest in manifests.items():
                    for trig in manifest.get("override_triggers", []):
                        if trig.lower() in clean_prompt:
                            logger.info(
                                f"[IntentParser] Matched agent trigger: '{trig}' -> '{agent_id}'"
                            )
                            return agent_id
        except Exception as err:
            logger.warning(
                f"[IntentParser] Could not evaluate agent trigger shortcuts: {err}"
            )

        return None

    def evaluate_and_scale_triage(
        self, prompt: str, raw_llm_scores: Dict[str, float], task_id: Optional[str] = None
    ) -> Tuple[str, float, Dict[str, float]]:
        """
        Applies priority multipliers to raw Pass 1 triage scores and emits a TRIAGE_DECISION telemetry trace.

        Formula: Score_final = min(1.0, Score_raw * PriorityWeight)
        """
        manifests = {}
        try:
            if hasattr(self.librarian, "agent_repo") and self.librarian.agent_repo:
                manifests = self.librarian.agent_repo.get_all_manifests()
        except Exception as err:
            logger.warning(
                f"[IntentParser] Could not retrieve agent manifests for triage scaling: {err}"
            )

        weighted_scores: Dict[str, float] = {}

        for agent_id, raw_score in raw_llm_scores.items():
            manifest = manifests.get(agent_id, {})
            weight = float(manifest.get("priority_weight", 1.0))
            final_score = min(1.0, round(raw_score * weight, 4))
            weighted_scores[agent_id] = final_score

        if not weighted_scores:
            selected_agent = "default_agent"
            top_score = 1.0
            weighted_scores = {"default_agent": 1.0}
        else:
            selected_agent = max(weighted_scores, key=weighted_scores.get)
            top_score = weighted_scores[selected_agent]

        # Emit Pass 1 triage decision telemetry trace over TelemetryBus -> WebSockets
        try:
            telemetry_bus.emit(
                TraceEvent(
                    event_type=TraceEventType.TRIAGE_DECISION,
                    agent_name="IntentParser",
                    action="triage_evaluation",
                    details={
                        "task_id": task_id or "system",
                        "prompt": prompt,
                        "selected_agent": selected_agent,
                        "confidence_score": top_score,
                        "candidate_scores": weighted_scores,
                        "raw_llm_scores": raw_llm_scores,
                    },
                )
            )
        except Exception as err:
            logger.warning(f"[IntentParser] Failed to emit TRIAGE_DECISION trace: {err}")

        return selected_agent, top_score, weighted_scores

    # =========================================================================
    # Dynamic Route Rule Management Delegate Methods
    # =========================================================================

    def get_override_rules(self) -> List[Dict[str, Any]]:
        """Retrieves active global dynamic shortcut override rules."""
        if hasattr(self.librarian, "route_repo") and self.librarian.route_repo:
            return self.librarian.route_repo.get_override_rules()
        return []

    def add_override_rule(self, trigger: str, target_agent: str, description: str = "") -> str:
        """Adds a new shortcut rule into RouteRepository."""
        if hasattr(self.librarian, "route_repo") and self.librarian.route_repo:
            return self.librarian.route_repo.add_override_rule(
                trigger=trigger, target_agent=target_agent, description=description
            )
        raise RuntimeError("RouteRepository not bound to SkillLibrarian.")

    def remove_override_rule(self, rule_id: str) -> bool:
        """Removes a dynamic shortcut rule by rule ID."""
        if hasattr(self.librarian, "route_repo") and self.librarian.route_repo:
            return self.librarian.route_repo.remove_override_rule(rule_id)
        return False