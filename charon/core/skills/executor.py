import importlib.util
import inspect
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from charon.core.skills.base import BaseSkill
from charon.core.skills.roles import RoleResolutionError
from charon.telemetry.trace import TraceEvent, TraceEventType, telemetry_bus

logger = logging.getLogger("Charon.Core.Skills.Executor")


class SkillExecutorMixin:
    """Skill checkout and runtime handler resolution for SkillLibrarian."""

    def check_out_skill(
        self, action: str, agent_name: str
    ) -> Optional[Callable[..., Union[str, Dict[str, Any]]]]:
        canonical_agent = self.resolve_agent_id_for_role(agent_name)

        # 1. Look up skill metadata row
        row = self.repo.get_skill_by_action(action)
        if not row:
            row = self.get_action_details(action)
            if not row:
                logger.error(f"[LIBRARIAN] Action contract '{action}' not found in registry.")
                telemetry_bus.emit(
                    TraceEvent(
                        event_type=TraceEventType.FAILED,
                        agent_name=agent_name,
                        action=action,
                        details={"error": "Action contract not found in registry"},
                    )
                )
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
        if status in ("QUARANTINED", "DISABLED"):
            reason = (
                row.get("quarantine_reason", f"Skill status is {status}.")
                if isinstance(row, dict)
                else getattr(row, "quarantine_reason", f"Skill status is {status}.")
            )
            logger.warning(f"[LIBRARIAN] Checkout blocked: Skill '{skill_id}' ({action}) is {status}.")
            telemetry_bus.emit(
                TraceEvent(
                    event_type=TraceEventType.FAILED,
                    agent_name=agent_name,
                    action=action,
                    details={"skill_id": skill_id, "status": status, "reason": reason},
                )
            )
            return None

        # 3. CBAC Authorization Gatecheck
        perm_repo = getattr(self, "permission_repo", None)
        authorized = True
        if perm_repo is not None:
            authorized = perm_repo.authorize_execution(canonical_agent, skill_id)
        else:
            authorized = self.is_skill_available(action, canonical_agent)

        if not authorized:
            logger.warning(
                f"[LIBRARIAN] CBAC Access Denied: Agent '{canonical_agent}' unauthorized for skill '{skill_id}' ({action})."
            )
            telemetry_bus.emit(
                TraceEvent(
                    event_type=TraceEventType.ESCALATION,
                    agent_name=agent_name,
                    action=action,
                    details={"skill_id": skill_id, "error": "CBAC Access Denied", "canonical_agent": canonical_agent},
                )
            )
            return None

        # Helper to emit successful checkout trace
        def _emit_checkout_event(handler_name: str):
            telemetry_bus.emit(
                TraceEvent(
                    event_type=TraceEventType.SKILL_CHECKOUT,
                    agent_name=agent_name,
                    action=action,
                    details={"skill_id": skill_id, "handler": handler_name, "canonical_agent": canonical_agent},
                )
            )

        # 4. Check in-memory registered skills cache
        skills_map = getattr(self, "_skills", {})
        if action in skills_map:
            in_mem_skill = skills_map[action]
            logger.info(f"[LIBRARIAN] In-memory skill contract '{action}' checked out.")
            _emit_checkout_event("in_memory")
            if isinstance(in_mem_skill, BaseSkill):
                return self._wrap_callable(in_mem_skill.execute, default_action=action, skill_id=skill_id)
            elif callable(in_mem_skill):
                return self._wrap_callable(in_mem_skill, default_action=action, skill_id=skill_id)

        try:
            raw_path = row.get("entry_file_path") if isinstance(row, dict) else getattr(row, "entry_file_path", None)
            handler_name = row.get("handler_name") if isinstance(row, dict) else getattr(row, "handler_name", "execute")

            if not raw_path:
                logger.critical(f"[PHANTOM SKILL DETECTED] Action '{action}' lacks 'entry_file_path'.")
                return None

            entry_file_path = Path(raw_path)
            if not entry_file_path.exists() or not entry_file_path.is_file():
                logger.critical(f"[PHANTOM SKILL DETECTED] Missing disk file: '{entry_file_path}'.")
                return None

            module_name = f"charon.skills_registry.dynamic.{skill_id}"
            spec = importlib.util.spec_from_file_location(module_name, entry_file_path)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Resolution Priority 1: BaseSkill sub-class
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if inspect.isclass(attr) and issubclass(attr, BaseSkill) and attr is not BaseSkill:
                    instance = attr()
                    logger.info(f"[LIBRARIAN] Checked out BaseSkill class '{attr_name}' for action '{action}'.")
                    _emit_checkout_event(attr_name)
                    return self._wrap_callable(instance.execute, default_action=action, skill_id=skill_id)

            # Resolution Priority 2: Explicit handler function
            if handler_name and hasattr(module, handler_name):
                target_func = getattr(module, handler_name)
                logger.info(f"[LIBRARIAN] Checked out handler function '{handler_name}' for action '{action}'.")
                _emit_checkout_event(handler_name)
                return self._wrap_callable(target_func, default_action=action, skill_id=skill_id)

            # Resolution Priority 3: Fallback execute_action
            if hasattr(module, "execute_action"):
                target_func = getattr(module, "execute_action")
                logger.info(f"[LIBRARIAN] Checked out 'execute_action' fallback for action '{action}'.")
                _emit_checkout_event("execute_action")
                return self._wrap_callable(target_func, default_action=action, skill_id=skill_id)

            return None

        except Exception as e:
            logger.error(f"[LIBRARIAN] Exception during checkout for skill '{action}': {e}", exc_info=True)
            return None

    def _wrap_callable(
        self, target_func: Callable[..., Any], default_action: str = "", skill_id: str = ""
    ) -> Callable[..., Any]:
        """Wraps target functions with signature inspection and runtime telemetry timing."""
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
                start_time = time.time()

                try:
                    if params_count >= 3:
                        res = await target_func(eff_agent, eff_params, raw_prompt)
                    elif params_count == 2:
                        res = await target_func(eff_agent, eff_params)
                    elif params_count == 1:
                        res = await target_func(eff_params)
                    else:
                        res = await target_func()

                    duration_ms = (time.time() - start_time) * 1000.0
                    telemetry_bus.emit(
                        TraceEvent(
                            event_type=TraceEventType.EXECUTION,
                            agent_name=eff_agent or "Librarian",
                            action=default_action,
                            duration_ms=duration_ms,
                            details={"skill_id": skill_id, "status": "success"},
                        )
                    )
                    return res
                except Exception as err:
                    duration_ms = (time.time() - start_time) * 1000.0
                    telemetry_bus.emit(
                        TraceEvent(
                            event_type=TraceEventType.FAILED,
                            agent_name=eff_agent or "Librarian",
                            action=default_action,
                            duration_ms=duration_ms,
                            details={"skill_id": skill_id, "error": str(err)},
                        )
                    )
                    raise err

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
            start_time = time.time()

            try:
                if params_count >= 3:
                    res = target_func(eff_agent, eff_params, raw_prompt)
                elif params_count == 2:
                    res = target_func(eff_agent, eff_params)
                elif params_count == 1:
                    res = target_func(eff_params)
                else:
                    res = target_func()

                duration_ms = (time.time() - start_time) * 1000.0
                telemetry_bus.emit(
                    TraceEvent(
                        event_type=TraceEventType.EXECUTION,
                        agent_name=eff_agent or "Librarian",
                        action=default_action,
                        duration_ms=duration_ms,
                        details={"skill_id": skill_id, "status": "success"},
                    )
                )
                return res
            except Exception as err:
                duration_ms = (time.time() - start_time) * 1000.0
                telemetry_bus.emit(
                    TraceEvent(
                        event_type=TraceEventType.FAILED,
                        agent_name=eff_agent or "Librarian",
                        action=default_action,
                        duration_ms=duration_ms,
                        details={"skill_id": skill_id, "error": str(err)},
                    )
                )
                raise err

        return sync_runtime_wrapper

    checkout_skill = check_out_skill