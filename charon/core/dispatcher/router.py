"""
charon/core/dispatcher/router.py
System Version: v0.4.0 | File Revision: 8.3.0

Core Routing Engine & Dynamic Agent Resolver backed by SQLite route_registry.
Enforces strict dynamic routing with zero hardcoded agent strings.
Instantiates data-driven RuntimeAgent instances hydrated dynamically via SkillLibrarian.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from charon.config.paths import STATE_DB_PATH
from charon.core.skills.librarian import SkillLibrarian
from charon.db.repositories import RouteRepository

logger = logging.getLogger("Charon.Router")


class RouteConfigError(Exception):
    """Raised when an illegal operation is attempted on an immutable route."""

    pass


class AgentRouter:
    """Manages dynamic agent lookup, route resolution, and RuntimeAgent instantiation via SkillLibrarian."""

    def __init__(self, db_path: Optional[Union[Path, str]] = None):
        target_path = Path(db_path) if db_path else STATE_DB_PATH

        if target_path.is_dir():
            logger.warning(
                f"[ROUTER] Directory path provided '{target_path}'. "
                f"Auto-correcting to STATE_DB_PATH '{STATE_DB_PATH}'."
            )
            target_path = STATE_DB_PATH

        self.db_path: Path = target_path
        self._route_cache: Dict[str, Tuple[str, str]] = {}
        self._system_fallback_cache: Optional[str] = None

    def clear_cache(self) -> None:
        """Flushes the in-memory route cache."""
        self._route_cache.clear()
        self._system_fallback_cache = None

    def get_system_fallback(self) -> str:
        """Retrieves system fallback role directly from RouteRepository DB or SkillLibrarian."""
        if self._system_fallback_cache:
            return self._system_fallback_cache

        if not self.db_path.exists():
            librarian = SkillLibrarian.get_instance(self.db_path)
            return librarian.get_default_agent_id()

        try:
            repo = RouteRepository(str(self.db_path))
            fallback = repo.get_system_fallback()

            if fallback:
                self._system_fallback_cache = fallback
                return fallback
        except Exception as e:
            logger.warning(f"[ROUTER] Failed querying system fallback from RouteRepository: {e}")

        librarian = SkillLibrarian.get_instance(self.db_path)
        default_agent = librarian.get_default_agent_id()
        self._system_fallback_cache = default_agent
        return default_agent

    def resolve_route(
        self,
        action_trigger: str = "",
        default_role: Optional[str] = None,
        **kwargs: Any,
    ) -> Tuple[str, str]:
        """Resolves an action trigger to (target_role, fallback_role) via RouteRepository."""
        action_trigger = kwargs.get("action_name", action_trigger)
        default_role = kwargs.get("default_agent", default_role)

        if action_trigger and action_trigger in self._route_cache:
            return self._route_cache[action_trigger]

        ultimate_fallback = default_role or self.get_system_fallback()

        if not self.db_path.exists():
            return ultimate_fallback, ultimate_fallback

        try:
            repo = RouteRepository(str(self.db_path))
            route_data = repo.resolve_and_track_route(action_trigger)

            if route_data:
                if isinstance(route_data, (tuple, list)):
                    target_role, fallback_role = route_data[0], route_data[1]
                elif isinstance(route_data, dict):
                    target_role = route_data.get("target_role", ultimate_fallback)
                    fallback_role = route_data.get("fallback_role")
                else:
                    target_role = getattr(route_data, "target_role", ultimate_fallback)
                    fallback_role = getattr(route_data, "fallback_role", None)

                fallback_role = fallback_role or ultimate_fallback

                if action_trigger:
                    self._route_cache[action_trigger] = (target_role, fallback_role)

                return target_role, fallback_role
        except Exception as e:
            logger.error(f"[ROUTER] Route resolution database query failed for '{action_trigger}': {e}")

        return ultimate_fallback, ultimate_fallback

    def get_agent_instance(
        self,
        target_role: Optional[str] = None,
        heavy_model: str = "",
        archivist: Optional[Any] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Dynamically resolves a target role or agent_id to its canonical database entry
        and returns a RuntimeAgent instance hydrated with metadata from SkillLibrarian.
        Zero legacy file imports or hardcoded agent class paths.
        """
        # Safely extract and remove keys to prevent duplication in **kwargs
        target_role = kwargs.pop("agent_id", target_role)
        heavy_model = kwargs.pop("heavy_model", heavy_model)
        archivist = kwargs.pop("archivist", archivist)
        kwargs.pop("target_role", None)

        if not target_role:
            raise ValueError("Must supply either 'target_role' or 'agent_id' to get_agent_instance.")

        librarian = SkillLibrarian.get_instance(self.db_path)

        # 1. Resolve target input (role alias or system_role) to canonical agent_id
        resolved_agent_id = librarian.resolve_agent_id_for_role(target_role) or target_role

        # 2. Fetch agent manifest/persona configuration directly from Librarian cache
        manifest = librarian.get_agent_manifest(resolved_agent_id) or librarian.get_agent_manifest(target_role)

        if not manifest or not isinstance(manifest, dict):
            raise RuntimeError(
                f"[ROUTER FAULT] No database manifest registered for target '{target_role}' "
                f"(Resolved ID: '{resolved_agent_id}'). Check agent_registry in state database."
            )

        # 3. Check Agent Lifecycle / Status Compliance (Schema V2)
        status = str(manifest.get("status", manifest.get("agent_status", "ACTIVE"))).upper()
        if status in ("QUARANTINED", "DISABLED", "ARCHIVED"):
            raise PermissionError(
                f"[ROUTER BLOCKED] Agent '{resolved_agent_id}' cannot be instantiated. "
                f"Current status: {status}."
            )

        # 4. Import concrete universal agent class
        from charon.agents.runtime import RuntimeAgent

        # 5. If passed pre-instantiated archivist/agent matches target ID, reuse directly
        if archivist is not None and getattr(archivist, "agent_id", None) == resolved_agent_id:
            return archivist

        # 6. Extract configuration payload from DB manifest
        display_name = manifest.get("display_name") or librarian.get_display_name_for_agent(resolved_agent_id)
        description = manifest.get("description", "")
        system_prompt = manifest.get("system_prompt", "")
        active_tools = manifest.get("active_tools") or manifest.get("tools", [])
        priority_weight = float(manifest.get("priority_weight", 1.0))

        # 7. Instantiate and return concrete RuntimeAgent
        return RuntimeAgent(
            agent_id=resolved_agent_id,
            display_name=display_name,
            description=description,
            system_prompt=system_prompt,
            active_tools=active_tools,
            priority_weight=priority_weight,
            heavy_model=heavy_model,
            librarian=librarian,
            **kwargs,
        )

    def register_route(
        self,
        action_trigger: str,
        target_role: str,
        route_type: str = "DYNAMIC_AUTO",
        fallback_role: Optional[str] = None,
        description: str = "",
        created_by: str = "agent",
        force: bool = False,
    ) -> None:
        """Registers a dynamic or system route in the route_registry DB table."""
        librarian = SkillLibrarian.get_instance(self.db_path)

        # Canonicalize target_role and fallback_role before DB insertion
        canonical_target = librarian.resolve_agent_id_for_role(target_role) or target_role
        canonical_fallback = (
            librarian.resolve_agent_id_for_role(fallback_role) if fallback_role else None
        ) or fallback_role

        repo = RouteRepository(str(self.db_path))
        existing_type = repo.get_route_type(action_trigger)

        if existing_type == "SYSTEM" and not force and route_type != "USER_OVERRIDE":
            raise RouteConfigError(
                f"Cannot override IMMUTABLE system route '{action_trigger}'. "
                f"Route type '{route_type}' lacks sufficient permission."
            )

        repo.upsert_route(
            action_trigger,
            canonical_target,
            canonical_fallback,
            route_type,
            description,
            created_by,
        )
        self.clear_cache()

        display_name = librarian.get_display_name_for_agent(canonical_target) or canonical_target

        logger.info(
            f"[ROUTER] Registered route: '{action_trigger}' -> '{display_name}' ({canonical_target}) [{route_type}]"
        )