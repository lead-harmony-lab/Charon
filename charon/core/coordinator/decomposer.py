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