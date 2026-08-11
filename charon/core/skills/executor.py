"""
charon/core/skills/executor.py
System Version: v0.6.3 | File Revision: 7.0.0

Module: Dynamic module import and skill checkout execution mixin for SkillLibrarian.
Resolves skill_id and handler_name to safely load disk plugins into runtime callables.
Integrates CBAC Schema V2 permission gatechecking and Quarantine State verification.
Enforces strict fail-fast role resolution against database registry.
"""

import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from charon.core.skills.base import BaseSkill
from charon.core.skills.roles import RoleResolutionError

logger = logging.getLogger("Charon.Core.Skills.Executor")


class SkillExecutorMixin:
    """Skill checkout and runtime handler resolution for SkillLibrarian."""

    def check_out_skill(
        self, action: str, agent_name: str
    ) -> Optional[Callable[..., Union[str, Dict[str, Any]]]]:
        """
        Validates authorization constraints, quarantine states, and CBAC permissions,
        then signs out the plugin handler callable.
        Resolves action_name -> skill_id -> entry_file_path + handler_name.
        Fails fast if agent_name cannot be resolved to an active agent in SQLite.
        """
        # Ground Truth DB Lookup: Fails hard if unresolvable
        canonical_agent = self.resolve_agent_id_for_role(agent_name)

        # 1. Look up skill metadata row to identify skill_id and status
        row = self.repo.get_skill_by_action(action)
        if not row:
            row = self.get_action_details(action)
            if not row:
                logger.error(f"[LIBRARIAN] Action contract '{action}' not found in registry.")
                return None

        skill_id = (
            row.get("skill_id", "unknown")
            if isinstance(row, dict)
            else getattr(row, "skill_id", "unknown")
        )
        status = (
            row.get("status", "QUARANTINED")
            if isinstance(row, dict)
            else getattr(row, "status", "QUARANTINED")
        )

        # 2. Check quarantine state
        if status == "QUARANTINED":
            quarantine_reason = (
                row.get("quarantine_reason", "Skill is in dynamic quarantine.")
                if isinstance(row, dict)
                else getattr(row, "quarantine_reason", "Skill is in dynamic quarantine.")
            )
            logger.warning(
                f"[LIBRARIAN] Checkout blocked: Skill '{skill_id}' ({action}) is QUARANTINED. Reason: {quarantine_reason}"
            )
            return None
        elif status == "DISABLED":
            logger.warning(
                f"[LIBRARIAN] Checkout blocked: Skill '{skill_id}' ({action}) is DISABLED."
            )
            return None

        # 3. CBAC Authorization Gatecheck
        perm_repo = getattr(self, "permission_repo", None)
        if perm_repo is not None:
            authorized = perm_repo.authorize_execution(canonical_agent, skill_id)
            if not authorized:
                logger.warning(
                    f"[LIBRARIAN] CBAC Access Denied: Agent '{canonical_agent}' unauthorized for skill '{skill_id}' ({action})."
                )
                return None
        else:
            # Fallback capability check via agent_skill_map
            if not self.is_skill_available(action, canonical_agent):
                logger.warning(
                    f"[LIBRARIAN] Access denied or skill unavailable for action '{action}' -> agent '{canonical_agent}' (raw: '{agent_name}')."
                )
                return None

        # 4. Check in-memory registered skills cache
        skills_map = getattr(self, "_skills", {})
        if action in skills_map:
            in_mem_skill = skills_map[action]
            logger.info(f"[LIBRARIAN] In-memory skill contract '{action}' checked out.")
            if isinstance(in_mem_skill, BaseSkill):
                if inspect.iscoroutinefunction(in_mem_skill.execute):
                    async def async_in_mem_wrapper(
                        agent="", params=None, raw_prompt="", agent_name=None, parameters=None, **kwargs
                    ):
                        return await in_mem_skill.execute(
                            agent_name or agent,
                            parameters if parameters is not None else (params or {}),
                            raw_prompt,
                        )
                    return async_in_mem_wrapper

                return lambda agent="", params=None, raw_prompt="", agent_name=None, parameters=None, **kwargs: in_mem_skill.execute(
                    agent_name or agent,
                    parameters if parameters is not None else (params or {}),
                    raw_prompt,
                )
            elif callable(in_mem_skill):
                return self._wrap_callable(in_mem_skill, default_action=action)

        try:
            # Defensive property extraction
            raw_path = (
                row.get("entry_file_path")
                if isinstance(row, dict)
                else getattr(row, "entry_file_path", None)
            )
            handler_name = (
                row.get("handler_name")
                if isinstance(row, dict)
                else getattr(row, "handler_name", "execute")
            )

            # Pre-flight Guardrail 1: DB entry missing disk path definition
            if not raw_path:
                logger.critical(
                    f"[PHANTOM SKILL DETECTED] Action '{action}' is registered in database (skill_id: '{skill_id}'), "
                    f"but lacks a valid 'entry_file_path' property."
                )
                return None

            entry_file_path = Path(raw_path)

            # Pre-flight Guardrail 2: DB/Disk Desync
            if not entry_file_path.exists() or not entry_file_path.is_file():
                logger.critical(
                    f"[PHANTOM SKILL DETECTED] Action '{action}' is registered in database (skill_id: '{skill_id}'), "
                    f"but plugin implementation file is missing on disk at '{entry_file_path}'. "
                    f"Database/Disk desync detected."
                )
                return None

            module_name = f"charon.skills_registry.dynamic.{skill_id}"
            spec = importlib.util.spec_from_file_location(module_name, entry_file_path)
            if spec is None or spec.loader is None:
                logger.error(f"[LIBRARIAN] Failed to load spec for {module_name} at '{entry_file_path}'.")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Resolution Priority 1: BaseSkill sub-class instantiation within module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    inspect.isclass(attr)
                    and issubclass(attr, BaseSkill)
                    and attr is not BaseSkill
                ):
                    instance = attr()
                    logger.info(
                        f"[LIBRARIAN] Checked out BaseSkill class '{attr_name}' for action '{action}' ({skill_id})."
                    )
                    if inspect.iscoroutinefunction(instance.execute):
                        async def async_base_skill_wrapper(
                            agent="", params=None, raw_prompt="", agent_name=None, parameters=None, **kwargs
                        ):
                            return await instance.execute(
                                agent_name or agent,
                                parameters if parameters is not None else (params or {}),
                                raw_prompt,
                            )
                        return async_base_skill_wrapper

                    return lambda agent="", params=None, raw_prompt="", agent_name=None, parameters=None, **kwargs: instance.execute(
                        agent_name or agent,
                        parameters if parameters is not None else (params or {}),
                        raw_prompt,
                    )

            # Resolution Priority 2: Explicit function corresponding to handler_name
            if handler_name and hasattr(module, handler_name):
                target_func = getattr(module, handler_name)
                logger.info(
                    f"[LIBRARIAN] Checked out handler function '{handler_name}' for action '{action}' ({skill_id})."
                )
                return self._wrap_callable(target_func, default_action=action)

            # Resolution Priority 3: Fallback module action entrypoint
            if hasattr(module, "execute_action"):
                target_func = getattr(module, "execute_action")
                logger.info(
                    f"[LIBRARIAN] Checked out 'execute_action' fallback for action '{action}' ({skill_id})."
                )

                if inspect.iscoroutinefunction(target_func):
                    async def async_fallback(
                        agent="", params=None, raw_prompt="", agent_name=None, parameters=None, **kwargs
                    ):
                        eff_params = parameters if parameters is not None else (params or {})
                        return await target_func(action, eff_params)
                    return async_fallback

                return lambda agent="", params=None, raw_prompt="", agent_name=None, parameters=None, **kwargs: target_func(
                    action,
                    parameters if parameters is not None else (params or {}),
                )

            logger.error(f"[LIBRARIAN] Execution handler '{handler_name}' missing in '{entry_file_path}'.")
            return None

        except Exception as e:
            logger.error(f"[LIBRARIAN] Exception during checkout for skill '{action}': {e}", exc_info=True)
            return None

    def _wrap_callable(
        self, target_func: Callable[..., Any], default_action: str = ""
    ) -> Callable[..., Any]:
        """Wraps target functions with signature inspection to normalize runtime parameter passing."""
        sig = inspect.signature(target_func)
        params_count = len(sig.parameters)
        is_async = inspect.iscoroutinefunction(target_func)

        if is_async:
            async def async_runtime_wrapper(
                agent_name: str = "",
                parameters: Optional[Dict[str, Any]] = None,
                raw_prompt: str = "",
                agent: str = "",
                params: Optional[Dict[str, Any]] = None,
                **kwargs: Any,
            ) -> Any:
                eff_agent = agent_name or agent
                eff_params = parameters if parameters is not None else (params if params is not None else {})

                if params_count >= 3:
                    return await target_func(eff_agent, eff_params, raw_prompt)
                elif params_count == 2:
                    return await target_func(eff_agent, eff_params)
                elif params_count == 1:
                    return await target_func(eff_params)
                else:
                    return await target_func()

            return async_runtime_wrapper

        def sync_runtime_wrapper(
            agent_name: str = "",
            parameters: Optional[Dict[str, Any]] = None,
            raw_prompt: str = "",
            agent: str = "",
            params: Optional[Dict[str, Any]] = None,
            **kwargs: Any,
        ) -> Any:
            eff_agent = agent_name or agent
            eff_params = parameters if parameters is not None else (params if params is not None else {})

            if params_count >= 3:
                return target_func(eff_agent, eff_params, raw_prompt)
            elif params_count == 2:
                return target_func(eff_agent, eff_params)
            elif params_count == 1:
                return target_func(eff_params)
            else:
                return target_func()

        return sync_runtime_wrapper

    checkout_skill = check_out_skill