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