"""
charon/core/skills/librarian.py
System Version: v2.1.2

Module: Central registry, hybrid DB/disk discovery hub, dynamic query bus, and authorization desk.
Combines RoleResolver, SkillIndexer, SkillQuery, and SkillExecutor mixins.
Integrates CBAC Schema V2 authorization, PermissionRepository, and Quarantine State controls.
Enforces strict fail-fast role resolution against database registry with dynamic defaults.
Updated: Implements Scenario A Planner Delegation Catalog resolution & DB cross-referenced role resolution.
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

    def get_agent_for_skill(
        self, skill_id: str, conn: Optional[sqlite3.Connection] = None
    ) -> Optional[str]:
        """Resolves the primary default agent assigned or authorized to execute a given skill."""
        if not skill_id:
            return None
        candidates = self.get_roles_for_action(skill_id, conn=conn)
        return candidates[0] if candidates else None

    def get_action_manifest(
        self, action: str, role_name: Optional[str] = None, conn: Optional[sqlite3.Connection] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieves action details/manifest for a given skill trigger after validating authorization."""
        if not action:
            return None

        if role_name:
            try:
                canonical_role = self.resolve_agent_id_for_role(role_name, conn=conn)
                planner_agent_id = self.role_repo.get_agent_for_role("system_planner", conn=conn)

                # 1. System Planner bypass: Planner must be able to read schemas for all tools
                if planner_agent_id and canonical_role == planner_agent_id:
                    pass
                else:
                    # 2. Check authorization using get_roles_for_action (handles both skill_id and action_name)
                    authorized_roles = self.get_roles_for_action(action, conn=conn)
                    if canonical_role not in authorized_roles:
                        # Fallback for quarantine/custom overrides inside is_skill_available
                        if hasattr(self, "is_skill_available") and not self.is_skill_available(action, canonical_role):
                            return None
            except RoleResolutionError:
                logger.debug(f"[SkillLibrarian] Unmapped role '{role_name}' for action '{action}'.")
                return None

        details = self.get_action_details(action)
        if details:
            return details

        skill_data = self.repo.get_skill_by_action(action, conn=conn)
        if skill_data:
            return skill_data

        # 3. Fallback: Caller passed a skill_id instead of an action_name. Resolve via catalog index.
        catalog = self.get_execution_tool_catalog(active_only=False, as_dict=True, conn=conn)
        return catalog.get(action)

    def get_roles_for_action(
        self, action_name: str, conn: Optional[sqlite3.Connection] = None
    ) -> List[str]:
        """Resolves candidate role IDs authorized to perform an ACTIVE capability contract by skill_id or action_name."""
        if not action_name:
            return []

        target = action_name.strip()
        query = """
            SELECT DISTINCT asm.agent_id
            FROM agent_skill_map asm
            INNER JOIN skill_registry sr ON asm.skill_id = sr.skill_id
            WHERE (asm.skill_id = ? OR sr.action_name = ?)
              AND sr.status = 'ACTIVE'
        """
        try:
            if conn:
                cursor = conn.cursor()
                cursor.execute(query, (target, target))
                rows = cursor.fetchall()
            else:
                with sqlite3.connect(self.db_path) as db_conn:
                    cursor = db_conn.cursor()
                    cursor.execute(query, (target, target))
                    rows = cursor.fetchall()
            return [row[0] for row in rows if row[0]]
        except Exception as err:
            logger.error(
                f"[SkillLibrarian] Error resolving candidate roles for target '{action_name}': {err}"
            )
            return []

    def list_available_actions(
        self, role_name: str, conn: Optional[sqlite3.Connection] = None
    ) -> List[str]:
        """Retrieves all active action capability names granted to a role alias."""
        if not role_name:
            return []
        try:
            canonical_id = self.resolve_agent_id_for_role(role_name, conn=conn)
            return self.repo.get_actions_for_agent(canonical_id, conn=conn)
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
    # Execution Tool Catalog API
    # =========================================================================

    def get_execution_tool_catalog(
            self,
            role_name: Optional[str] = None,
            skill_type: Optional[str] = None,
            active_only: bool = True,
            as_dict: bool = True,
            conn: Optional[sqlite3.Connection] = None,
    ) -> Union[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
        """Fetches execution tool catalog with detailed diagnostic trace logging."""
        raw_skills: List[Dict[str, Any]] = []

        if role_name:
            try:
                caller_agent_id = self.resolve_agent_id_for_role(role_name, conn=conn)
                planner_agent_id = self.role_repo.get_agent_for_role("system_planner", conn=conn)

                logger.debug(
                    f"[SkillLibrarian.Trace] Role lookup '{role_name}' -> "
                    f"caller_agent_id='{caller_agent_id}', planner_agent_id='{planner_agent_id}'"
                )

                if planner_agent_id and caller_agent_id == planner_agent_id:
                    logger.info(f"[SkillLibrarian.Trace] Agent '{caller_agent_id}' matched system_planner. Fetching global catalog.")
                    raw_skills = self.repo.get_all_active_skills(conn=conn) if active_only else self.repo.get_all_skills(conn=conn)
                else:
                    logger.debug(f"[SkillLibrarian.Trace] Querying agent_skill_map for caller_agent_id='{caller_agent_id}'")
                    raw_skills = self.repo.get_skills_for_agent(caller_agent_id, conn=conn)

                logger.info(
                    f"[SkillLibrarian.Trace] Retrieved {len(raw_skills)} raw skill record(s) for caller_agent_id='{caller_agent_id}': "
                    f"{[(s.get('skill_id'), s.get('action_name')) for s in raw_skills]}"
                )

            except RoleResolutionError as rre:
                logger.warning(
                    f"[SkillLibrarian] Role resolution failed for tool catalog lookup '{role_name}': {rre}"
                )
                return {} if as_dict else []
            except Exception as err:
                logger.error(
                    f"[SkillLibrarian] Failed to fetch tools for role '{role_name}': {err}"
                )
                return {} if as_dict else []
        else:
            try:
                if skill_type and skill_type.upper() not in ("*", "ALL", "ANY"):
                    raw_skills = self.repo.get_skills_by_type(
                        skill_type, active_only=active_only, conn=conn
                    )
                elif active_only:
                    raw_skills = self.repo.get_all_active_skills(conn=conn)
                else:
                    raw_skills = self.repo.get_all_skills(conn=conn)
            except Exception as err:
                logger.error(
                    f"[SkillLibrarian] Failed to fetch execution tool catalog: {err}"
                )
                return {} if as_dict else []

        # Filter skills by active status and skill_type classification
        filtered_skills: List[Dict[str, Any]] = []
        target_type = (
            skill_type.upper()
            if skill_type and skill_type.upper() not in ("*", "ALL", "ANY")
            else None
        )

        for skill in raw_skills:
            if active_only and not skill.get("is_active") and skill.get("status") != "ACTIVE":
                logger.debug(f"[SkillLibrarian.Trace] Filtering out inactive skill: {skill.get('skill_id')}")
                continue
            if target_type:
                stype = str(skill.get("skill_type", "")).upper()
                if target_type == "EXECUTION" and stype in ("EXECUTION", "NATIVE", "DYNAMIC", "PYTHON", "SYSTEM", ""):
                    pass
                elif stype != target_type:
                    logger.debug(f"[SkillLibrarian.Trace] Filtering out skill type mismatch ({stype} != {target_type}): {skill.get('skill_id')}")
                    continue
            filtered_skills.append(skill)

        # Single index by skill_id to prevent downstream schema duplication
        if as_dict:
            catalog: Dict[str, Dict[str, Any]] = {}
            for skill in filtered_skills:
                skill_id_key = skill.get("skill_id")

                if skill_id_key:
                    catalog[skill_id_key] = skill

                logger.debug(
                    f"[SkillLibrarian.Trace] Indexed skill: skill_id='{skill_id_key}' into catalog keys."
                )

            logger.info(f"[SkillLibrarian.Trace] Final catalog key count: {len(catalog)}. Keys: {list(catalog.keys())}")
            return catalog

        return filtered_skills

    get_tool_catalog = get_execution_tool_catalog
    get_execution_tools = get_execution_tool_catalog

    # ======================================
    # Manifest Control & System Topology API
    # ======================================

    def get_system_topology(self, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
        """Builds a comprehensive manifest of all active agents and their bound capabilities."""
        topology = []

        for agent_id, manifest in self._manifest_cache.items():
            if str(manifest.get("status", "ACTIVE")).upper() != "ACTIVE":
                continue

            bound_capabilities = self.list_available_actions(agent_id, conn=conn)

            topology.append({
                "agent_id": agent_id,
                "skill_id": manifest.get("default_action"),
                "role": manifest.get("role", "system_agent"),
                "description": manifest.get("description", f"Execute tasks requiring {agent_id} capabilities."),
                "bound_capabilities": bound_capabilities
            })

        return topology

    def get_role_default_action(self, role_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[str]:
        """Retrieves the default interface action (Work Contract) for a role."""
        manifest = self.get_agent_manifest(role_id, conn=conn)
        if manifest and "default_action" in manifest:
            return str(manifest["default_action"])
        return None

    def get_default_action_for_role(self, role_name: str, conn: Optional[sqlite3.Connection] = None) -> str:
        """Resolves and returns the default action_name for a given system role."""
        role_id = self.resolve_agent_id_for_role(role_name, conn=conn)

        agent_manifest = self.get_agent_manifest(role_id, conn=conn) or {}
        if isinstance(agent_manifest, dict):
            return agent_manifest.get("default_action") or ""

        return getattr(agent_manifest, "default_action", "")

    def reload_all_manifests(self, conn: Optional[sqlite3.Connection] = None) -> None:
        """Refreshes the in-memory manifest cache directly from AgentRepository."""
        try:
            self._manifest_cache = self.agent_repo.get_all_manifests(conn=conn)
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

    def get_agent_manifest(self, role_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
        """Retrieves a single manifest by resolving target via RoleResolverMixin."""
        if not role_id:
            return None
        try:
            canonical_id = self.resolve_agent_id_for_role(role_id, conn=conn)
            return self._manifest_cache.get(canonical_id) or self._manifest_cache.get(role_id)
        except RoleResolutionError:
            return None

    def update_agent_manifest(self, role_id: str, update_data: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> bool:
        """Delegates manifest persistence to AgentRepository via resolved ID and refreshes cache."""
        canonical_id = self.resolve_agent_id_for_role(role_id, conn=conn)
        success = self.agent_repo.update_manifest(canonical_id, update_data, conn=conn)
        if success:
            self.reload_agent_manifest(canonical_id, conn=conn)
        return success

    def reload_agent_manifest(self, role_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
        """Hot-reloads a single role manifest from AgentRepository into memory cache."""
        canonical_id = self.resolve_agent_id_for_role(role_id, conn=conn)
        manifest = self.agent_repo.get_manifest(canonical_id, conn=conn)
        if manifest:
            self._manifest_cache[canonical_id] = manifest
        else:
            self._manifest_cache.pop(canonical_id, None)
        return manifest

    def set_tool_status(self, role_id: str, tool_name: str, enabled: bool, conn: Optional[sqlite3.Connection] = None) -> bool:
        """Toggles role capability via AgentRepository and hot-reloads the manifest cache."""
        canonical_id = self.resolve_agent_id_for_role(role_id, conn=conn)
        success = self.agent_repo.set_tool_status(canonical_id, tool_name, enabled, conn=conn)

        if success:
            self.reload_agent_manifest(canonical_id, conn=conn)
        return success