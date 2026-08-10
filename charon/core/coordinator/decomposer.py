"""
charon/core/coordinator/decomposer.py
System Version: v0.3.2 | File Revision: 1.6.0

Module: Requirement Decomposition and Payload Parsing Engine.
Parses prompts and metadata into discrete blackboard requirements and seed artifacts.
Updated for dynamic SkillLibrarian queries, Revision 3 SQLite Schema compatibility,
and fail-fast default action contract resolution.
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

# Safe import for legacy manifest lookup
try:
    from charon.intent.manifests import get_agent_manifest
except ImportError:
    get_agent_manifest = lambda agent_id: None

logger = logging.getLogger("charon.core.coordinator.decomposer")


class RequirementDecomposer:
    """Decomposes prompts into initial blackboard artifacts and unfulfilled requirements using dynamic skills."""

    def __init__(self, librarian: Optional[SkillLibrarian] = None):
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _resolve_agent_override(self, raw_override: Any) -> tuple[Optional[str], Optional[str]]:
        """Resolves raw role/agent strings into (role_name, agent_id) matching system_roles / agent_registry FKs."""
        if not raw_override:
            return None, None

        raw_str = str(getattr(raw_override, "value", raw_override))
        role_name = raw_str
        agent_id = raw_str

        # Schema Compliance: Check if raw_override is a role_name mapped in system_roles
        if hasattr(self.librarian, "resolve_agent_id_for_role") and callable(self.librarian.resolve_agent_id_for_role):
            resolved = self.librarian.resolve_agent_id_for_role(raw_str)
            if resolved:
                agent_id = resolved

        return role_name, agent_id

    def _resolve_agent_default_action(self, agent_or_role: Optional[str] = None) -> str:
        """Dynamically resolves default interface action for an agent/role via SkillLibrarian or manifest.

        If agent_or_role is not provided, resolves default action for the system 'generalist' role.

        Raises:
            RuntimeError: If default action contract cannot be resolved.
        """
        target_agent = agent_or_role

        # 1. Resolve role_name -> agent_id if mapped
        if target_agent and hasattr(self.librarian, "resolve_agent_id_for_role") and callable(self.librarian.resolve_agent_id_for_role):
            resolved = self.librarian.resolve_agent_id_for_role(target_agent)
            if resolved:
                target_agent = resolved

        # 2. If no target provided, resolve system generalist role
        if not target_agent:
            for role_key in ["generalist", "default_generalist", "system_fallback"]:
                if hasattr(self.librarian, "resolve_agent_id_for_role") and callable(self.librarian.resolve_agent_id_for_role):
                    resolved = self.librarian.resolve_agent_id_for_role(role_key)
                    if resolved:
                        target_agent = resolved
                        break

        if target_agent:
            # Query SkillLibrarian API
            if hasattr(self.librarian, "get_agent_default_action") and callable(self.librarian.get_agent_default_action):
                action = self.librarian.get_agent_default_action(target_agent)
                if action:
                    return str(action)

            # Query Manifest Cache directly
            try:
                manifest = get_agent_manifest(target_agent)
                if manifest:
                    default_act = manifest.get("default_action") if isinstance(manifest, dict) else getattr(manifest, "default_action", None)
                    if default_act:
                        return str(default_act)
            except Exception:
                pass

        raise RuntimeError(
            f"[DECOMPOSER ERROR] Cannot resolve default action contract for target '{agent_or_role or 'generalist'}': "
            "No 'default_action' mapped in manifest or database state."
        )

    def get_action_capability(self, action_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves action metadata from the dynamic skill registry, filtering for ACTIVE status."""
        cap = self.librarian.get_action_details(action_name)
        if cap and cap.get("status", "ACTIVE") != "ACTIVE":
            logger.warning(f"[DECOMPOSER] Requested action '{action_name}' is not ACTIVE (status={cap.get('status')}).")
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

        # 1. MPN / Part Number Regex Extraction (Strict alphanumeric heuristics)
        mpn_match = re.search(r"\b([A-Z0-9]+-[A-Z0-9_\-]+|[A-Z0-9]{5,})\b", prompt, re.IGNORECASE)
        if mpn_match:
            blackboard.set_artifact("target_part", mpn_match.group(1))

        blackboard.set_artifact("original_prompt", prompt)
        handled_by_payload = False

        # 2. Check Typed Agent/Role Payloads / Dynamic Payloads
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
                    intent_extraction.get("parameters", {}) if isinstance(intent_extraction, dict) else {}
                )

                if action:
                    cap_info = self.get_action_capability(action) or {}
                    produced = cap_info.get("produced_artifacts", [])
                    esc_level = cap_info.get("escalation_level", EscalationLevel.L1_SPECIALIST)

                    blackboard.unfulfilled_requirements.append(
                        UnfulfilledRequirement(
                            capability_required=cap_info.get("capability_name", action),
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
                        agent_actions = self.librarian.list_available_actions(
                            getattr(manifest, "name", role_str) if manifest else role_str
                        )
                        if agent_actions:
                            cap_info = self.get_action_capability(agent_actions[0])
                        else:
                            fallback_action = self._resolve_agent_default_action(agent_id_str or role_str)
                            cap_info = self.get_action_capability(fallback_action)

                    if cap_info:
                        hint_params = (
                            routing_hint.get("parameters", {})
                            if isinstance(routing_hint, dict)
                            else {}
                        )
                        produced = cap_info.get("produced_artifacts", [])
                        esc_level = cap_info.get("escalation_level", EscalationLevel.L1_SPECIALIST)
                        blackboard.unfulfilled_requirements.append(
                            UnfulfilledRequirement(
                                capability_required=cap_info.get("capability_name", cap_info.get("action_name")),
                                target_artifact_key=produced[0] if produced else None,
                                escalation_level=esc_level,
                                assigned_role_override=role_str,
                                assigned_agent_override=agent_id_str,
                                parameters=hint_params,
                            )
                        )
                        handled_by_payload = True

        # 4. Default Fallback -> Conversational Query
        if not blackboard.unfulfilled_requirements:
            generalist_action = self._resolve_agent_default_action()
            cap_info = self.get_action_capability(generalist_action)
            if not cap_info:
                raise RuntimeError(
                    f"[DECOMPOSER ERROR] Default generalist action '{generalist_action}' "
                    "is missing or not active in database."
                )

            cap_name = cap_info.get("capability_name", generalist_action)
            esc_level = cap_info.get("escalation_level", EscalationLevel.L1_SPECIALIST)
            produced = cap_info.get("produced_artifacts", ["response_text"])

            blackboard.unfulfilled_requirements.append(
                UnfulfilledRequirement(
                    capability_required=cap_name,
                    target_artifact_key=produced[0] if produced else "response_text",
                    escalation_level=esc_level,
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

        cap_info = self.get_action_capability(action) or {}

        req_params = {k: v for k, v in payload_dict.items() if v is not None}
        req_params["requires_approval"] = requires_approval

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
                capability_required=cap_info.get("capability_name", action),
                target_artifact_key=produced[0] if produced else None,
                escalation_level=esc_level,
                assigned_role_override=role_str,
                assigned_agent_override=agent_id_str,
                parameters=req_params,
            )
        )
        return True