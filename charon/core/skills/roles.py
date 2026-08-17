"""
charon/core/skills/roles.py
System Version: v0.6.4 | File Revision: 9.1.1

Strict database-driven role resolution and entrypoint discovery mixin for SkillLibrarian.
No in-memory fallback dictionaries. The database is the single source of truth.
Unmapped roles raise RoleResolutionError immediately.
"""

import logging
from typing import Dict

from charon.db.repositories import RoleRepository

logger = logging.getLogger("Charon.Core.Skills.Roles")


class RoleResolutionError(KeyError):
    """Raised when a requested role cannot be resolved directly from the database registry."""
    pass


class RoleResolverMixin:
    """Strict DB-backed canonical ID resolution and entrypoint lookup mixin."""

    @property
    def _role_repo(self) -> RoleRepository:
        """Lazily provisions and caches the repository using the instance's db_path."""
        if not hasattr(self, "_cached_role_repo") or self._cached_role_repo is None:
            self._cached_role_repo = RoleRepository(getattr(self, "db_path", None))
        return self._cached_role_repo

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
            logger.error(
                "[LIBRARIAN] Core role validation failed: `system_roles` table returned no records."
            )
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
        Queries the database directly for the exact agent_id bound to the given role key.

        Strips the 'role:' namespace prefix if present to ensure clean DB lookups.
        HARD FAIL: Raises `RoleResolutionError` immediately if input is missing or unmapped in DB.
        """
        if not role_input or not isinstance(role_input, str):
            raise RoleResolutionError(
                "[LIBRARIAN] Role lookup rejected: Blank or invalid role input."
            )

        # Safely strip "role:" prefix for DB lookups
        sanitized_role = role_input.replace("role:", "") if role_input.startswith("role:") else role_input

        # Single Source of Truth: Direct raw key lookup in database
        resolved_id = self._role_repo.get_agent_id_for_role(sanitized_role)
        if resolved_id:
            return resolved_id

        # HARD FAIL: No in-memory guessing, no normalization, no fallbacks
        raise RoleResolutionError(
            f"[LIBRARIAN] Unresolvable Role: Exact key '{role_input}' (sanitized to '{sanitized_role}') has no active agent binding in the database."
        )

    def resolve_role(self, role_input: str) -> str:
        """Alias method for role resolution compatibility."""
        return self.resolve_agent_id_for_role(role_input)

    def get_agent_entrypoint(self, agent_id: str) -> Dict[str, str]:
        """
        Retrieves the Python module path and class name for a database-validated agent directly from DB.
        Raises RoleResolutionError if module or class_name is missing or incomplete in the DB.
        """
        canonical_id = self.resolve_agent_id_for_role(agent_id)

        entrypoint_data = self._role_repo.get_agent_entrypoint_data(canonical_id)

        if (
            entrypoint_data
            and isinstance(entrypoint_data, dict)
            and entrypoint_data.get("module")
            and entrypoint_data.get("class_name")
        ):
            return entrypoint_data

        raise RoleResolutionError(
            f"[LIBRARIAN] Entrypoint Resolution Failure: Incomplete or missing entrypoint record "
            f"(module/class_name) in database for agent '{canonical_id}'."
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