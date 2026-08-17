"""
charon/core/coordinator/decomposer.py
System Version: v0.9.3 | File Revision: 9.3.0

Module: Requirement Decomposition and Payload Parsing Engine.
Parses prompts and metadata into discrete blackboard requirements and seed artifacts.
Strictly enforces explicit metadata/payload routing with ZERO LLM triage or speculative fallbacks.
Strictly enforces Database as SSOT across all SkillLibrarian resolutions.
Raises RuntimeError on unmapped roles, missing metadata, or unrouted prompts.
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
from charon.core.utils import normalize_role_name

logger = logging.getLogger("charon.core.coordinator.decomposer")


class RequirementDecomposer:
    """Decomposes prompts into initial blackboard artifacts and unfulfilled requirements using SSOT skills."""

    def __init__(self, librarian: Optional[SkillLibrarian] = None):
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _resolve_agent_override(self, raw_override: Any) -> tuple[Optional[str], Optional[str]]:
        """Resolves raw role/agent inputs into canonical (role_name, agent_id) tuples via direct DB lookup."""
        if not raw_override:
            return None, None

        clean_id = str(getattr(raw_override, "value", raw_override)).strip()
        if not clean_id:
            return None, None

        clean_id = normalize_role_name(clean_id)

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
        """Dynamically resolves default interface action for an agent/role strictly via SkillLibrarian DB SSOT."""
        if not agent_or_role or not str(agent_or_role).strip():
            raise RuntimeError(
                "[DECOMPOSER FAULT] Cannot resolve default action: No agent or role identifier provided."
            )

        target_id = normalize_role_name(str(agent_or_role).strip())

        if hasattr(self.librarian, "get_agent_default_action") and callable(self.librarian.get_agent_default_action):
            action = self.librarian.get_agent_default_action(target_id)
            if action:
                return str(action)

        raise RuntimeError(
            f"[DECOMPOSER FAULT] Cannot resolve default action contract for identifier '{target_id}': "
            "No 'default_action' mapped in database state."
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

        for key in [
            "mpn",
            "part_number",
            "query",
            "command",
            "source_file",
            "script_path",
            "project_directory",
            "url",
        ]:
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
            or payload_dict.get("target_role")
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

    def decompose(
        self,
        prompt: str,
        blackboard: TaskBlackboard,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Populates blackboard with seed artifacts and initial requirement stack. Fast-fails if unrouted."""
        metadata = metadata or {}
        handled_by_payload = False

        # 1. MPN / Part Number Regex Extraction
        mpn_match = re.search(r"\b([A-Z0-9]+-[A-Z0-9_\-]+|[A-Z0-9]{5,})\b", prompt, re.IGNORECASE)
        if mpn_match:
            blackboard.set_artifact("target_part", mpn_match.group(1))

        blackboard.set_artifact("original_prompt", prompt)

        # 2. Check Typed Agent/Role Payloads
        payload_obj = (
            metadata.get("payload")
            or metadata.get("agent_payload")
            or metadata.get("role_payload")
        )
        if payload_obj:
            handled_by_payload = self._process_typed_payload(payload_obj, blackboard)

        # 3. Process Explicit Metadata Routing & Direct Requirements
        if not handled_by_payload and metadata:
            target_role = (
                metadata.get("target_role")
                or metadata.get("assigned_role")
                or metadata.get("role")
                or metadata.get("assigned_agent")
                or metadata.get("target_agent")
            )
            explicit_action = metadata.get("action") or metadata.get("target_action")

            if target_role or explicit_action:
                role_str, agent_id_str = (
                    self._resolve_agent_override(target_role) if target_role else (None, None)
                )

                if explicit_action:
                    act_name = str(explicit_action)
                elif role_str:
                    act_name = self._resolve_agent_default_action(role_str)
                else:
                    act_name = None

                if act_name:
                    cap_info = self.get_action_capability(act_name)
                    if not cap_info:
                        raise RuntimeError(
                            f"[DECOMPOSER FAULT] Metadata specified action '{act_name}', "
                            "but capability is missing or inactive in SkillLibrarian database."
                        )

                    cap_name = cap_info.get("capability_name") or cap_info.get("action_name", act_name)
                    produced = cap_info.get("produced_artifacts", [])
                    esc_level = cap_info.get("escalation_level", EscalationLevel.L1_SPECIALIST)

                    req_params = metadata.get("parameters", {})
                    if not isinstance(req_params, dict):
                        req_params = {}
                    req_params["prompt"] = prompt

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

        # 4. Strict Harness Fast-Fail (No LLM Triage or Silent Fallbacks)
        if not blackboard.unfulfilled_requirements:
            raise RuntimeError(
                f"[DECOMPOSER FAULT] Unrouted prompt detected. LLM triage and generalist fallbacks are disabled. "
                f"No explicit payload, target_role, or action provided in metadata for prompt: '{prompt}'"
            )