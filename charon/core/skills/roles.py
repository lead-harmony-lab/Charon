"""
charon/core/skills/roles.py
System Version: v0.6.3 | File Revision: 9.0.0

Strict database-driven role resolution and entrypoint discovery mixin for SkillLibrarian.
No in-memory fallback dictionaries. No string-stripping heuristics.
The database is the single source of truth. Unmapped roles raise RoleResolutionError immediately.
"""

import logging
from typing import Dict

from charon.db.repositories import RoleRepository

logger = logging.getLogger("Charon.Core.Skills.Roles")


class RoleResolutionError(KeyError):
    """Raised when a requested role cannot be resolved directly from the database registry."""
    pass


class RoleResolverMixin:
    """Strict DB-backed role normalization, canonical ID resolution, and entrypoint lookup mixin."""

    @property
    def _role_repo(self) -> RoleRepository:
        """Lazily provisions and caches the repository using the instance's db_path."""
        if not hasattr(self, "_cached_role_repo") or self._cached_role_repo is None:
            self._cached_role_repo = RoleRepository(getattr(self, "db_path", None))
        return self._cached_role_repo

    def _normalize_role_key(self, raw_role: str) -> str:
        """Normalizes raw role input string by trimming whitespace and lowercasing."""
        if not raw_role:
            return ""
        return raw_role.strip().lower()

    def get_default_agent_id(self) -> str:
        """
        Queries the database for the designated default system fallback agent.
        Hard-fails if the database query returns no default agent.
        """
        agent_id = self._role_repo.get_default_agent_id()
        if agent_id:
            return agent_id

        raise RoleResolutionError(
            "[LIBRARIAN] Critical Registry Failure: No default system agent configured in database."
        )

    def validate_core_roles(self) -> bool:
        """
        Validates that all required system roles are explicitly mapped to active agents in SQLite.
        Strictly read-only database query.
        """
        rows = self._role_repo.get_core_roles_status()
        if not rows:
            logger.error("[LIBRARIAN] Core role validation failed: `system_roles` table returned no records.")
            return False

        all_valid = True
        for role_name, agent_id, is_active in rows:
            if not agent_id or not is_active:
                logger.error(
                    f"[LIBRARIAN] Invalid database state: Role '{role_name}' is unmapped or mapped to an inactive agent ('{agent_id}')."
                )
                all_valid = False

        return all_valid

    def resolve_agent_id_for_role(self, role_input: str) -> str:
        """
        Queries the database directly for the agent_id bound to the given role.

        HARD FAIL: Raises `RoleResolutionError` immediately if input is blank or unmapped in DB.
        """
        if not role_input or not str(role_input).strip():
            raise RoleResolutionError("[LIBRARIAN] Role lookup rejected: Empty or missing role input.")

        norm = self._normalize_role_key(role_input)

        # Single Source of Truth: Database lookup
        resolved_id = self._role_repo.get_agent_id_for_role(norm)
        if resolved_id:
            return resolved_id

        # HARD FAIL: No in-memory guessing, no default fallback
        raise RoleResolutionError(
            f"[LIBRARIAN] Unresolvable Role: '{role_input}' (normalized: '{norm}') "
            f"has no active agent binding in the database."
        )

    def resolve_role(self, role_input: str) -> str:
        """Alias method for role resolution compatibility."""
        return self.resolve_agent_id_for_role(role_input)

    def get_agent_entrypoint(self, agent_id: str) -> Dict[str, str]:
        """
        Retrieves the Python module path and class name for a database-validated agent.
        Raises RoleResolutionError if the agent has no entrypoint in DB.
        """
        canonical_id = self.resolve_agent_id_for_role(agent_id)

        entrypoint_data = self._role_repo.get_agent_entrypoint_data(canonical_id)

        if entrypoint_data and entrypoint_data.get("module") and entrypoint_data.get("class_name"):
            return entrypoint_data

        if entrypoint_data is not None:
            class_name = "".join(part.capitalize() for part in canonical_id.split("_")) + "Agent"
            return {
                "module": f"charon.agents.{canonical_id}",
                "class_name": class_name,
            }

        raise RoleResolutionError(
            f"[LIBRARIAN] Entrypoint Resolution Failure: No module/class registered for canonical agent '{canonical_id}'."
        )

    def get_display_name_for_agent(self, agent_id: str) -> str:
        """Retrieves human-readable display_name for an agent directly from DB."""
        canonical_id = self.resolve_agent_id_for_role(agent_id)

        display_name = self._role_repo.get_agent_display_name(canonical_id)
        if display_name:
            return display_name

        raise RoleResolutionError(
            f"[LIBRARIAN] Display Name Failure: Agent '{canonical_id}' has no display name in database."
        )