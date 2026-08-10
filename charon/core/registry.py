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