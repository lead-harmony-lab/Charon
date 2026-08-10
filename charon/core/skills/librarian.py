"""
charon/core/skills/librarian.py
System Version: v0.6.0 | File Revision: 9.1.0

Module: Central registry, hybrid DB/disk discovery hub, dynamic query bus, and authorization desk.
Combines RoleResolver, RouteManager, SkillIndexer, SkillQuery, and SkillExecutor mixins.
Integrates CBAC Schema V2 authorization, PermissionRepository, and Quarantine State controls.
"""

import logging
from pathlib import Path
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
from charon.core.skills.roles import RoleResolverMixin
from charon.core.skills.routes import RouteManagerMixin
from charon.db.repositories import (
    AgentRepository,
    PermissionRepository,
    RoleRepository,
    RouteRepository,
    SkillRepository,
)

logger = logging.getLogger("Charon.Core.Skills")


class SkillLibrarian(
    RoleResolverMixin,
    RouteManagerMixin,
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
        route_repo: Optional[RouteRepository] = None,
        permission_repo: Optional[PermissionRepository] = None,
    ) -> None:
        self._skills: Dict[str, BaseSkill] = {}
        self.db_path: Path = Path(db_path)

        # Instantiate Data Access Layer (DAL) Repositories
        self.repo: SkillRepository = skill_repo or SkillRepository(self.db_path)
        self.agent_repo: AgentRepository = agent_repo or AgentRepository(self.db_path)
        self.role_repo: RoleRepository = role_repo or RoleRepository(self.db_path)
        self.route_repo: RouteRepository = route_repo or RouteRepository(self.db_path)
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
        """Singleton accessor for global agent capability lookup and manifest resolution."""
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

    def get_action_manifest(
        self, action: str, agent_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves action details/manifest for a given skill trigger after validating
        authorization for the specified agent.
        """
        if not action:
            return None

        # Validate agent authorization if agent name/ID provided
        if agent_name:
            canonical_agent = self.resolve_agent_id_for_role(agent_name)
            if hasattr(self, "is_skill_available") and not self.is_skill_available(
                action, canonical_agent
            ):
                return None

        # Resolve skill action metadata from query mixin or repository
        if hasattr(self, "get_action_details"):
            details = self.get_action_details(action)
            if details:
                return details

        return self.repo.get_skill_by_action(action)

    # =========================================================================
    # Dynamic Router & Manifest Control API
    # =========================================================================

    def get_agent_default_action(self, agent_id: str) -> Optional[str]:
        """
        Retrieves the default interface action for an agent.
        Resolves canonical agent ID via RoleResolverMixin and queries cached manifests.
        """
        manifest = self.get_agent_manifest(agent_id)
        if manifest and "default_action" in manifest:
            return str(manifest["default_action"])
        return None

    def get_default_action_for_role(self, role_name: str) -> str:
        """
        Resolves and returns the default action_name for a given system role.
        Falls back to resolving the agent mapped to the role.
        """
        agent_id = self.resolve_agent_id_for_role(role_name)
        if not agent_id:
            return ""

        agent_manifest = self.get_agent_manifest(agent_id) or {}
        if isinstance(agent_manifest, dict):
            return agent_manifest.get("default_action") or ""

        return getattr(agent_manifest, "default_action", "")

    def reload_all_manifests(self) -> None:
        """Refreshes the in-memory manifest cache directly from AgentRepository."""
        try:
            self._manifest_cache = self.agent_repo.get_all_manifests()
            logger.info(
                f"[SkillLibrarian] Cached {len(self._manifest_cache)} agent manifest(s) in memory."
            )
        except Exception as e:
            logger.warning(
                f"[SkillLibrarian] Could not load agent manifests on startup: {e}"
            )

    def get_all_agent_manifests(self) -> Dict[str, Dict[str, Any]]:
        """Returns all cached agent manifests."""
        return self._manifest_cache

    def get_agent_manifest(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single manifest by resolving agent target via RoleResolverMixin.
        Checks canonical agent ID as well as raw inputs.
        """
        if not agent_id:
            return None
        canonical_id = self.resolve_agent_id_for_role(agent_id)
        return self._manifest_cache.get(canonical_id) or self._manifest_cache.get(agent_id)

    def update_agent_manifest(self, agent_id: str, update_data: Dict[str, Any]) -> bool:
        """Delegates manifest persistence to AgentRepository via resolved agent ID and refreshes cache."""
        canonical_id = self.resolve_agent_id_for_role(agent_id)
        success = self.agent_repo.update_manifest(canonical_id, update_data)
        if success:
            self.reload_agent_manifest(canonical_id)
        return success

    def reload_agent_manifest(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Hot-reloads a single agent manifest from AgentRepository into memory cache."""
        canonical_id = self.resolve_agent_id_for_role(agent_id)
        manifest = self.agent_repo.get_manifest(canonical_id)
        if manifest:
            self._manifest_cache[canonical_id] = manifest
        else:
            self._manifest_cache.pop(canonical_id, None)
        return manifest

    def set_tool_status(self, agent_id: str, tool_name: str, enabled: bool) -> bool:
        """
        Toggles agent capability in agent_skill_map by resolving action contract/skill_id
        and hot-reloading the manifest cache.
        """
        canonical_id = self.resolve_agent_id_for_role(agent_id)

        # Resolve corresponding skill_id if tool_name is passed as action contract trigger
        skill_row = self.repo.get_skill_by_action(tool_name)
        skill_id = (
            skill_row.get("skill_id")
            if isinstance(skill_row, dict)
            else (getattr(skill_row, "skill_id", tool_name) if skill_row else tool_name)
        )

        if enabled:
            success = self.repo.link_agent_to_skill(canonical_id, skill_id)
        else:
            success = self.repo.revoke_skill_by_id(canonical_id, skill_id)

        if success:
            self.reload_agent_manifest(canonical_id)
        return success