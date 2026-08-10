"""
charon/core/skills/query.py
System Version: v0.6.0 | File Revision: 6.2.0

Capability matching and tool schema generation mixin for SkillLibrarian.
Delegates all database access to SkillRepository (DAL) and performs physical
executable checks to filter phantom/hallucinated skills.
"""

import logging
import os
import shutil
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("Charon.Core.Skills.Query")


class SkillQueryMixin:
    """Action queries, tool schema generation, and authorization checks for SkillLibrarian."""

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
                    if not shutil.which(req_clean) and not os.path.exists(req_clean):
                        logger.warning(
                            f"[LIBRARIAN] Suppressing unequipped skill '{action_dict.get('action_name')}': "
                            f"missing binary requirement '{req_clean}'"
                        )
                        return False
        return True

    def get_actions_for_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        """Retrieves active, unquarantined, and physically verified action metadata for an agent persona."""
        actions_by_name: Dict[str, Dict[str, Any]] = {}
        canonical_agent = (
            self.resolve_agent_id_for_role(agent_name)
            if hasattr(self, "resolve_agent_id_for_role")
            else agent_name
        )

        try:
            # Delegate SQL execution entirely to the DAL repository layer
            db_actions: List[Dict[str, Any]] = self.repo.get_skills_for_agent(
                canonical_agent, agent_name
            )

            for act in db_actions:
                act_status = act.get("status", "ACTIVE") or "ACTIVE"
                if act_status.upper() == "ACTIVE" and self._is_physically_executable(act):
                    actions_by_name[act["action_name"]] = act

        except Exception as e:
            logger.error(
                f"[LIBRARIAN] Error querying DB actions for agent '{agent_name}' ({canonical_agent}): {e}"
            )

        # Merge in-memory registered skills matching agent permissions and physical existence
        for act_name, skill in getattr(self, "_skills", {}).items():
            s_status = getattr(skill, "status", "ACTIVE") or "ACTIVE"
            if s_status.upper() != "ACTIVE":
                continue

            allowed = getattr(skill, "allowed_agents", []) or []
            if "*" in allowed or canonical_agent in allowed or agent_name in allowed:
                skill_dict = {
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
                if self._is_physically_executable(skill_dict):
                    actions_by_name[act_name] = skill_dict

        return list(actions_by_name.values())

    def list_available_actions(self, agent_name: str) -> List[str]:
        """Lists active, unquarantined, verified dynamic skill actions accessible to an agent persona."""
        actions: Set[str] = set()
        canonical_agent = (
            self.resolve_agent_id_for_role(agent_name)
            if hasattr(self, "resolve_agent_id_for_role")
            else agent_name
        )

        try:
            db_actions = self.get_actions_for_agent(canonical_agent)
            for act in db_actions:
                if isinstance(act, dict) and "action_name" in act:
                    actions.add(act["action_name"])
                elif isinstance(act, str):
                    actions.add(act)
        except Exception as e:
            logger.warning(
                f"[LIBRARIAN] Failed to query mapped actions for '{agent_name}': {e}"
            )

        return sorted(list(actions))

    def get_agent_tool_schemas(self, agent_name: str) -> List[Dict[str, Any]]:
        """Generates OpenAI/Ollama-compliant Function Tool JSON specs for active agent skills."""
        canonical_agent = (
            self.resolve_agent_id_for_role(agent_name)
            if hasattr(self, "resolve_agent_id_for_role")
            else agent_name
        )
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
        """Checks if an agent is authorized for an active, unquarantined, and verified skill."""
        canonical_agent = (
            self.resolve_agent_id_for_role(agent_name)
            if hasattr(self, "resolve_agent_id_for_role")
            else agent_name
        )

        try:
            details = self.get_action_details(action)
            if details and details.get("status", "ACTIVE").upper() == "ACTIVE":
                if not self._is_physically_executable(details):
                    return False
                available_actions = self.list_available_actions(canonical_agent)
                if action in available_actions:
                    sys_reqs = details.get("system_requirements", [])
                    return (
                        self.verify_system_requirements(sys_reqs)
                        if hasattr(self, "verify_system_requirements")
                        else True
                    )
        except Exception as e:
            logger.warning(
                f"[LIBRARIAN] Authorization lookup error for '{action}' -> '{canonical_agent}': {e}"
            )

        return False

    def get_action_details(self, action_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves full action specification record directly via SkillRepository."""
        try:
            return self.repo.get_skill_by_action(action_name)
        except Exception as e:
            logger.error(
                f"[LIBRARIAN] Error fetching details for action '{action_name}': {e}"
            )
        return None

    def find_matching_action(
        self, query: str, agent_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Performs keyword matching against active, verified DB-indexed actions fetched from DAL."""
        query_lower = query.lower().strip()
        best_match: Optional[Dict[str, Any]] = None
        highest_score = 0.0

        try:
            if agent_name:
                canonical_agent = (
                    self.resolve_agent_id_for_role(agent_name)
                    if hasattr(self, "resolve_agent_id_for_role")
                    else agent_name
                )
                actions = self.get_actions_for_agent(canonical_agent)
            else:
                actions = self.repo.get_all_active_skills()

            for r_dict in actions:
                if r_dict.get("status", "ACTIVE").upper() != "ACTIVE":
                    continue

                if not self._is_physically_executable(r_dict):
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
        except Exception as e:
            logger.error(f"[LIBRARIAN] Error matching action for query '{query}': {e}")

        return best_match