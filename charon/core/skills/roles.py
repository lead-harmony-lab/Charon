"""
charon/core/skills/roles.py
System Version: v0.6.0 | File Revision: 8.3.0

Pure database-driven role resolution, role key normalization, and agent entrypoint
discovery mixin for SkillLibrarian. Backed strictly by RoleRepository.
Zero hardcoded agent names in domain logic. CBAC Schema V2 compliant.
"""

import logging
from typing import Dict, Optional

from charon.db.repositories import RoleRepository

logger = logging.getLogger("Charon.Core.Skills.Roles")


class RoleResolverMixin:
    """Pure DB-backed role normalization, canonical ID resolution, and entrypoint lookup mixin."""

    @property
    def _role_repo(self) -> RoleRepository:
        """Lazily provisions and caches the repository using the instance's db_path."""
        if not hasattr(self, "_cached_role_repo") or self._cached_role_repo is None:
            self._cached_role_repo = RoleRepository(getattr(self, "db_path", None))
        return self._cached_role_repo

    def _normalize_role_key(self, raw_role: str) -> str:
        """Normalizes raw role inputs into clean lower snake_case keys."""
        if not raw_role:
            return ""
        return raw_role.strip().lower().replace(" ", "_").replace("-", "_")

    def get_default_agent_id(self) -> str:
        """
        Queries the database for the designated default system fallback agent ('system_fallback').
        Fails fast and hard if no fallback or active agent exists in the database.
        """
        try:
            agent_id = self._role_repo.get_default_agent_id()
            if agent_id:
                return agent_id
        except Exception as e:
            logger.error(f"[LIBRARIAN] Failed querying default agent from database: {e}")

        raise RuntimeError(
            "[LIBRARIAN] Critical Initialization Error: No default or active agent found in database registry."
        )

    def validate_core_roles(self) -> bool:
        """
        Validates that required system roles in `system_roles` have mapped, active agents in `agent_registry`.
        Returns True if all registered core system roles are validly mapped and active.
        """
        try:
            rows = self._role_repo.get_core_roles_status()
            if not rows:
                logger.warning("[LIBRARIAN] No system roles found in database `system_roles` table.")
                return False

            for role_name, agent_id, is_active in rows:
                if not agent_id or not is_active:
                    logger.warning(
                        f"[LIBRARIAN] Core system role '{role_name}' has unmapped or inactive agent ('{agent_id}')."
                    )
                    return False
            return True
        except Exception as e:
            logger.error(f"[LIBRARIAN] Core role validation check failed: {e}")
            return False

    def resolve_agent_id_for_role(self, role_input: str) -> str:
        """
        Resolves raw role input or alias to a canonical agent_id stored in the database.
        Falls back to the database-defined default agent if unresolvable.
        """
        if not role_input:
            return self.get_default_agent_id()

        norm = self._normalize_role_key(role_input)
        if not norm:
            return self.get_default_agent_id()

        system_role_variant = norm if norm.startswith("system_") else f"system_{norm}"
        agent_id_variant = norm[7:] if norm.startswith("system_") else norm

        try:
            resolved_id = self._role_repo.get_agent_id_for_role(
                norm=norm,
                agent_id_variant=agent_id_variant,
                system_role_variant=system_role_variant,
            )
            if resolved_id:
                return resolved_id
        except Exception as e:
            logger.warning(
                f"[LIBRARIAN] Database role resolution failed for '{role_input}': {e}"
            )

        return self.get_default_agent_id()

    def resolve_role(self, role_input: str) -> str:
        """Alias method for role resolution compatibility."""
        return self.resolve_agent_id_for_role(role_input)

    def get_agent_entrypoint(self, agent_id: str) -> Dict[str, str]:
        """
        Retrieves the Python module path and class name for an agent.
        Uses database dynamic overrides if available, otherwise resolves via
        canonical package convention (`charon.agents.<agent_id>`).
        """
        canonical_id = self.resolve_agent_id_for_role(agent_id)

        try:
            entrypoint_data = self._role_repo.get_agent_entrypoint_data(canonical_id)

            if entrypoint_data and entrypoint_data.get("module") and entrypoint_data.get("class_name"):
                return entrypoint_data

            if entrypoint_data is not None:
                class_name = "".join(part.capitalize() for part in canonical_id.split("_")) + "Agent"
                return {
                    "module": f"charon.agents.{canonical_id}",
                    "class_name": class_name,
                }
        except Exception as e:
            logger.warning(
                f"[LIBRARIAN] Failed fetching entrypoint for agent '{agent_id}' from DB: {e}"
            )

        default_agent_id = self.get_default_agent_id()
        class_name = "".join(part.capitalize() for part in default_agent_id.split("_")) + "Agent"
        return {
            "module": f"charon.agents.{default_agent_id}",
            "class_name": class_name,
        }

    def get_display_name_for_agent(self, agent_id: str) -> str:
        """Retrieves the human-readable display_name for an agent directly from DB."""
        canonical_id = self.resolve_agent_id_for_role(agent_id)

        try:
            display_name = self._role_repo.get_agent_display_name(canonical_id)
            if display_name:
                return display_name
        except Exception as e:
            logger.warning(
                f"[LIBRARIAN] Could not retrieve display name for agent '{agent_id}': {e}"
            )

        return canonical_id.replace("_", " ").title()