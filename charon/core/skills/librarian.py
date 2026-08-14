"""
charon/core/skills/librarian.py
System Version: v2.0.0

Module: Central registry, hybrid DB/disk discovery hub, dynamic query bus, and authorization desk.
Combines RoleResolver, SkillIndexer, SkillQuery, and SkillExecutor mixins.
Integrates CBAC Schema V2 authorization, PermissionRepository, system_actions lookups, and Quarantine State controls.
Enforces strict fail-fast role and system action resolution against database registry with dynamic defaults.
"""

import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Union

from charon.config.paths import (
    DYNAMIC_SKILLS_DIR,
    PKG_DYNAMIC_SKILLS_DIR,
    PKG_STAGED_SKILLS_DIR,
    STATE_DB_PATH,
)
from charon.core.skills.base import BaseSkill
from charon.core.skills.executor import SkillExecutorMixin
from charon.core.skills.indexer import SkillIndexerMixin
from charon.core.skills.query import SkillQueryMixin
from charon.core.skills.roles import RoleResolutionError, RoleResolverMixin
from charon.db.repositories import (
    AgentRepository,
    PermissionRepository,
    RoleRepository,
    SkillRepository,
)

logger = logging.getLogger("Charon.Core.Skills")


class SkillLibrarian(
    RoleResolverMixin,
    SkillIndexerMixin,
    SkillQueryMixin,
    SkillExecutorMixin,
):
    """Central registry, dynamic query bus, role-resolver, and authorization manager for Charon."""

    _instance: Optional["SkillLibrarian"] = None

    def __init__(
        self,
        search_paths: Optional[List[Path]] = None,
        db_path: Union[Path, str] = STATE_DB_PATH,
        skill_repo: Optional[SkillRepository] = None,
        agent_repo: Optional[AgentRepository] = None,
        role_repo: Optional[RoleRepository] = None,
        permission_repo: Optional[PermissionRepository] = None,
    ) -> None:
        self._skills: Dict[str, BaseSkill] = {}
        self.db_path: Path = Path(db_path)

        # Instantiate Data Access Layer (DAL) Repositories
        self.repo: SkillRepository = skill_repo or SkillRepository(self.db_path)
        self.agent_repo: AgentRepository = agent_repo or AgentRepository(self.db_path)
        self.role_repo: RoleRepository = role_repo or RoleRepository(self.db_path)
        self.permission_repo: PermissionRepository = (
            permission_repo or PermissionRepository(self.db_path)
        )

        # In-memory manifest cache for zero-latency triage lookups
        self._manifest_cache: Dict[str, Dict[str, Any]] = {}
        self.reload_all_manifests()

        default_paths = [
            PKG_DYNAMIC_SKILLS_DIR,
            PKG_STAGED_SKILLS_DIR,
        ]
        if DYNAMIC_SKILLS_DIR.exists():
            default_paths.append(DYNAMIC_SKILLS_DIR)

        self.search_paths: List[Path] = search_paths or default_paths

    @classmethod
    def get_instance(cls, db_path: Optional[Union[Path, str]] = None) -> "SkillLibrarian":
        """Singleton accessor for global role capability lookup and manifest resolution."""
        target_path = Path(db_path) if db_path else STATE_DB_PATH
        if cls._instance is None:
            cls._instance = SkillLibrarian(db_path=target_path)
        elif db_path is not None and cls._instance.db_path != target_path:
            cls._instance = SkillLibrarian(db_path=target_path)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Flushes the singleton instance (primarily used for test teardowns or DB switches)."""
        cls._instance = None

    # =========================================================================
    # Skill Action Lookup & Authorization API
    # =========================================================================

    def resolve_system_action(self, reserved_key: str) -> str:
        """Resolves an abstract system action key (e.g., 'sys_synthesis') to its active database action_name SSOT.

        Fails fast if the key is missing, unbound, or unmapped in the database.
        """
        if not reserved_key:
            raise ValueError("[FAIL-FAST] System action key cannot be empty.")

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT action_name FROM system_actions WHERE reserved_key = ?;",
                    (reserved_key,),
                )
                row = cursor.fetchone()

            if not row or not row[0]:
                raise RuntimeError(
                    f"[FAIL-FAST] Mandatory system action key '{reserved_key}' is not mapped to an active skill in system_actions."
                )

            return str(row[0])

        except Exception as err:
            logger.error(f"[SkillLibrarian] Error resolving system action '{reserved_key}': {err}")
            raise

    def get_action_manifest(
        self, action: str, role_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieves action details/manifest for a given skill trigger after validating authorization.

        Gracefully returns None if role resolution fails or skill is unauthorized.
        """
        if not action:
            return None

        # Validate role authorization if role name/ID provided
        if role_name:
            try:
                canonical_role = self.resolve_agent_id_for_role(role_name)
                if not self.is_skill_available(action, canonical_role):
                    return None
            except RoleResolutionError:
                logger.debug(f"[SkillLibrarian] Unmapped role '{role_name}' for action '{action}'.")
                return None

        # Resolve skill action metadata from query mixin or repository
        details = self.get_action_details(action)
        if details:
            return details

        return self.repo.get_skill_by_action(action)

    def get_roles_for_action(self, action_name: str) -> List[str]:
        """Resolves candidate role IDs authorized to perform an ACTIVE action capability contract.

        Delegates directly to SkillRepository SSOT query.
        """
        if not action_name:
            return []
        try:
            return self.repo.get_agents_for_action(action_name.strip())
        except Exception as err:
            logger.error(
                f"[SkillLibrarian] Error resolving candidate roles for action '{action_name}': {err}"
            )
            return []

    def list_available_actions(self, role_name: str) -> List[str]:
        """Retrieves all active action capability names granted to a role alias.

        Resolves role aliases to canonical IDs before querying SSOT state.
        """
        if not role_name:
            return []
        try:
            canonical_id = self.resolve_agent_id_for_role(role_name)
            return self.repo.get_actions_for_agent(canonical_id)
        except RoleResolutionError as rre:
            logger.warning(
                f"[SkillLibrarian] Could not resolve role '{role_name}' for available actions: {rre}"
            )
            return []
        except Exception as err:
            logger.error(
                f"[SkillLibrarian] Error listing actions for target '{role_name}': {err}"
            )
            return []

    # =========================================================================
    # Manifest Control API
    # =========================================================================

    def get_role_default_action(self, role_id: str) -> Optional[str]:
        """Retrieves the default interface action (Work Contract) for a role.

        Resolves canonical role ID via RoleResolverMixin and queries cached manifests.
        """
        manifest = self.get_agent_manifest(role_id)
        if manifest and "default_action" in manifest:
            return str(manifest["default_action"])
        return None

    def get_default_action_for_role(self, role_name: str) -> str:
        """Resolves and returns the default action_name (Work Contract) for a given system role.

        Fails fast if role_name cannot be resolved to an active role in SQLite.
        """
        role_id = self.resolve_agent_id_for_role(role_name)

        agent_manifest = self.get_agent_manifest(role_id) or {}
        if isinstance(agent_manifest, dict):
            return agent_manifest.get("default_action") or ""

        return getattr(agent_manifest, "default_action", "")

    def reload_all_manifests(self) -> None:
        """Refreshes the in-memory manifest cache directly from AgentRepository."""
        try:
            self._manifest_cache = self.agent_repo.get_all_manifests()
            logger.info(
                f"[SkillLibrarian] Cached {len(self._manifest_cache)} role manifest(s) in memory."
            )
        except Exception as e:
            logger.warning(
                f"[SkillLibrarian] Could not load role manifests on startup: {e}"
            )

    def get_all_agent_manifests(self) -> Dict[str, Dict[str, Any]]:
        """Returns all cached role manifests."""
        return self._manifest_cache

    def get_agent_manifest(self, role_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single manifest by resolving target via RoleResolverMixin.

        Fails fast if role_id is an unmapped role.
        """
        if not role_id:
            return None
        try:
            canonical_id = self.resolve_agent_id_for_role(role_id)
            return self._manifest_cache.get(canonical_id) or self._manifest_cache.get(role_id)
        except RoleResolutionError:
            return None

    def update_agent_manifest(self, role_id: str, update_data: Dict[str, Any]) -> bool:
        """Delegates manifest persistence to AgentRepository via resolved ID and refreshes cache."""
        canonical_id = self.resolve_agent_id_for_role(role_id)
        success = self.agent_repo.update_manifest(canonical_id, update_data)
        if success:
            self.reload_agent_manifest(canonical_id)
        return success

    def reload_agent_manifest(self, role_id: str) -> Optional[Dict[str, Any]]:
        """Hot-reloads a single role manifest from AgentRepository into memory cache."""
        canonical_id = self.resolve_agent_id_for_role(role_id)
        manifest = self.agent_repo.get_manifest(canonical_id)
        if manifest:
            self._manifest_cache[canonical_id] = manifest
        else:
            self._manifest_cache.pop(canonical_id, None)
        return manifest

    def set_tool_status(self, role_id: str, tool_name: str, enabled: bool) -> bool:
        """Toggles role capability via AgentRepository and hot-reloads the manifest cache."""
        canonical_id = self.resolve_agent_id_for_role(role_id)
        success = self.agent_repo.set_tool_status(canonical_id, tool_name, enabled)

        if success:
            self.reload_agent_manifest(canonical_id)
        return success