"""
charon/agents/base.py
System Version: v1.0.0 | File Revision: 4.3.1

Module: Core BaseAgent interface defining unified probing, health checks,
declarative manifest capabilities, dynamic skill lookup via SkillLibrarian SSOT,
and strict Zero-Trust Ephemeral Contract enforcement with JIT Expansion (The Interceptor).
"""

from abc import ABC, abstractmethod
import logging
import shutil
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from pydantic import BaseModel

from charon.core.coordinator.blackboard import TaskBlackboard, ThoughtType
from charon.core.skills import SkillLibrarian
from charon.core.permissions.middleware import CBACPermissionMiddleware
from charon.core.utils import normalize_role_name
from charon.telemetry.ledger import ExecutionLedger

logger = logging.getLogger("charon.agents.base")


class CapabilityType(str, Enum):
    """Defines the execution domain of an agent capability."""
    NATIVE = "native"
    DYNAMIC_SKILL = "dynamic_skill"
    UNSUPPORTED = "unsupported"


class SkillContract(BaseModel):
    """Pre-flight negotiation contract returned during capability probing."""
    status: str
    capability_type: CapabilityType
    missing_prerequisites: List[str] = []


class BaseAgent(ABC):
    """Abstract Base Class for all Charon Policy Execution Containers (PECs).

    Enforces strict Zero-Trust Ephemeral Contracts minted by the Coordinator.
    Actively intercepts, filters, hides, and dynamically expands tool access
    via JIT negotiation for authorized capabilities.
    """

    name: str = "BaseAgent"
    agent_id: str = "base_agent"
    role_name: str = "base_agent_role"
    domain: str = "Generic Domain"

    supported_actions: Union[Dict[str, Any], List[str]] = {}
    system_requirements: List[str] = []
    consumed_artifacts: List[str] = []
    produced_artifacts: List[str] = []
    description: str = "Standard agent interface."

    def __init__(
        self,
        librarian: Optional[SkillLibrarian] = None,
        agent_id: Optional[str] = None,
        role_name: Optional[str] = None,
        ledger: Optional[ExecutionLedger] = None,
        coordinator_repo: Optional[Any] = None,
    ) -> None:
        self.librarian = librarian or SkillLibrarian.get_instance()
        self.ledger = ledger or ExecutionLedger()
        self.coordinator_repo = coordinator_repo

        if agent_id:
            self.agent_id = agent_id
        elif not hasattr(self, "agent_id") or self.agent_id == "base_agent":
            self.agent_id = self.name.lower()

        self.role_name = role_name or normalize_role_name(self.agent_id)

        # Ephemeral Zero-Trust State (Injected per execution turn)
        self._active_contract_id: Optional[str] = None
        self._authorized_tools: List[str] = []

        # Mount CBAC Middleware
        repo = getattr(self.librarian, "repo", self.librarian) if self.librarian else None
        self.cbac_middleware = CBACPermissionMiddleware(repo=repo) if repo else None
        self._telemetry_callback: Optional[Callable[[Dict[str, Any]], None]] = None

    def _get_coordinator_repo(self) -> Optional[Any]:
        """Lazy resolver for CoordinatorStateRepository if not explicitly injected."""
        if self.coordinator_repo:
            return self.coordinator_repo

        if self.librarian:
            db_path = getattr(self.librarian, "db_path", None)
            if not db_path and hasattr(self.librarian, "repo"):
                db_path = getattr(self.librarian.repo, "db_path", None)

            if db_path:
                from charon.db.repositories.coordinator import CoordinatorStateRepository
                self.coordinator_repo = CoordinatorStateRepository(db_path=Path(db_path))
                return self.coordinator_repo

        return None

    # ==========================================
    # ZERO-TRUST EXECUTION ENVELOPE
    # ==========================================

    def execute_task(self, payload: Dict[str, Any]) -> BaseModel:
        """
        THE ENVELOPE: Concrete template method enforcing the ephemeral contract.
        Intercepts the Key Maker payload, locks authorized tools, and wraps execution.
        """
        self._active_contract_id = payload.get("active_contract_id")
        self._authorized_tools = list(payload.get("authorized_tools", []))

        if not self._active_contract_id:
            raise ValueError(
                f"ZERO-TRUST VIOLATION: Execution blocked for '{self.agent_id}'. "
                "No active_contract_id provided by the Coordinator."
            )

        logger.info(
            f"[{self.name}] Binding ephemeral contract {self._active_contract_id}. "
            f"Authorized tools: {self._authorized_tools}"
        )

        try:
            return self._execute_container(payload)
        finally:
            # THE LOCAL BURN: Instantly wipe ephemeral keys from memory
            self._active_contract_id = None
            self._authorized_tools = []

    @abstractmethod
    def _execute_container(self, payload: Dict[str, Any]) -> BaseModel:
        """Internal execution container implementation. Implemented by RuntimeAgent."""
        pass

    def get_authorized_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        THE BLINDER: Generates the strict tool manifest for the LLM.
        Hides any local skills not explicitly minted in the active contract.
        """
        schemas = []
        for tool_name in self._authorized_tools:
            manifest = self.librarian.get_action_manifest(tool_name, self.agent_id) if self.librarian else None
            if manifest:
                schemas.append(manifest)
            else:
                logger.warning(f"[{self.name}] Authorized tool '{tool_name}' missing from Librarian.")
        return schemas

    def execute_sub_skill(
        self,
        skill_id: str,
        parameters: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
        execution_context: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Union[str, Dict[str, Any]]:
        """
        THE INTERCEPTOR: Isolated dispatcher used by agents to execute tools.
        Enforces active contract bounds, performs JIT expansion on demand if CBAC allows,
        and proceeds to Librarian checkout.
        """
        # Safely handle if the caller passed `arguments=` instead of `parameters=`
        parameters = parameters or kwargs.get("arguments", {})

        if not self.librarian:
            raise RuntimeError(f"[{self.name}] SkillLibrarian not initialized.")

        # ZERO-TRUST INTERCEPTOR (Strict Ephemeral Check with JIT Fallback)
        if skill_id not in self._authorized_tools:
            coord_repo = self._get_coordinator_repo()
            jit_granted = False

            if self._active_contract_id and coord_repo:
                try:
                    logger.info(
                        f"[{self.name}] Tool '{skill_id}' outside active contract. Requesting JIT expansion..."
                    )
                    jit_granted = coord_repo.request_jit_extension(
                        contract_id=self._active_contract_id,
                        requested_skill=skill_id
                    )
                except Exception as e:
                    logger.warning(f"[{self.name}] Exception during JIT contract expansion: {e}")

            if jit_granted:
                self._authorized_tools.append(skill_id)
                self.report_trace(
                    event_type="JIT_CONTRACT_EXPANSION",
                    details={"contract_id": self._active_contract_id, "granted_skill": skill_id}
                )
                logger.info(
                    f"[{self.name}] JIT Contract Expansion GRANTED for '{skill_id}' "
                    f"under contract '{self._active_contract_id}'."
                )
            else:
                raise PermissionError(
                    f"ZERO-TRUST VIOLATION: '{self.agent_id}' attempted to execute unauthorized tool '{skill_id}'. "
                    f"Active contract '{self._active_contract_id}' strictly limits access to: {self._authorized_tools}"
                )

        # Base Legal Check (Level 0 Fallback)
        if self.cbac_middleware:
            ctx = execution_context or {}
            if "target_scope" not in ctx and "target_scope" in parameters:
                ctx["target_scope"] = parameters["target_scope"]

            self.cbac_middleware.validate_execution(
                role_name=self.role_name,
                skill_id=skill_id,
                execution_context=ctx,
            )

        # Checkout & Execute
        handler = self.librarian.check_out_skill(skill_id, self.agent_id)
        if not handler:
            raise ValueError(f"[FAIL-FAST] Dynamic skill '{skill_id}' is not registered.")

        logger.info(f"[{self.name}] Ephemeral & CBAC Passed. Executing '{skill_id}'.")
        return handler(agent_name=self.name, parameters=parameters, raw_prompt=raw_prompt)

    # ==========================================
    # TELEMETRY & REPORTING
    # ==========================================

    def bind_telemetry(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Binds a thread-safe telemetry callback from the Dispatcher."""
        self._telemetry_callback = callback

    def set_telemetry_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Alias for bind_telemetry for external TUI/bus streaming compatibility."""
        self.bind_telemetry(callback)

    def log_cot(
        self,
        blackboard: Optional[TaskBlackboard] = None,
        message: str = "",
        thought_type: ThoughtType = ThoughtType.ANALYSIS,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Broadcasts live internal reasoning (Chain-of-Thought) to blackboard and telemetry bus."""
        if blackboard and hasattr(blackboard, "emit_thought"):
            blackboard.emit_thought(
                source_role=self.agent_id,
                message=message,
                thought_type=thought_type
            )

        if self._telemetry_callback:
            self._telemetry_callback({
                "type": "agent_cot",
                "agent_name": self.name,
                "data": {
                    "thought_type": thought_type.value if hasattr(thought_type, "value") else str(thought_type),
                    "message": message,
                    "context": context or {}
                }
            })
        logger.info(f"[{self.name} CoT] {message}")

    def report_response(self, content: str, **kwargs: Any) -> None:
        """Emits an explicit final agent response message to streaming buses."""
        if not self._telemetry_callback:
            return

        payload_data: Dict[str, Any] = {"content": content}
        if kwargs:
            payload_data.update(kwargs)

        self._telemetry_callback({
            "type": "agent_response",
            "agent_name": getattr(self, "name", self.__class__.__name__),
            "data": payload_data,
        })

    def report_progress(
        self,
        message: str = "",
        phase: Optional[str] = None,
        action: Optional[str] = None,
        progress_pct: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        """Emits a standard progress update to the telemetry bus."""
        if not self._telemetry_callback:
            return

        payload_data: Dict[str, Any] = {
            "message": message,
            "phase": phase or action,
        }
        if progress_pct is not None:
            payload_data["progress_pct"] = progress_pct

        if kwargs:
            payload_data.update(kwargs)

        self._telemetry_callback({
            "type": "task_progress",
            "agent_name": getattr(self, "name", self.__class__.__name__),
            "data": payload_data,
        })

    def report_trace(
        self,
        event_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        action: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Emits execution state changes for telemetry HUD."""
        if not self._telemetry_callback:
            return

        merged_details = dict(details) if details else {}
        if kwargs:
            merged_details.update(kwargs)

        resolved_event = event_type or action or "EXECUTION_TRACE"

        self._telemetry_callback({
            "type": "telemetry_trace",
            "agent_name": getattr(self, "name", self.__class__.__name__),
            "data": {
                "event_type": resolved_event,
                "details": merged_details,
            },
        })

    # ==========================================
    # DISCOVERY & PROBING
    # ==========================================

    def health_check(self) -> Dict[str, Any]:
        """Performs runtime health and dependency checks."""
        missing = [req for req in self.system_requirements if shutil.which(req) is None]
        dynamic_actions = self.librarian.list_available_actions(self.agent_id) if self.librarian else []
        return {
            "agent_id": self.agent_id,
            "status": "degraded" if missing else "healthy",
            "missing_dependencies": missing,
            "dynamic_skills_available": dynamic_actions,
        }

    def probe(self, probe_type: str = "full") -> Dict[str, Any]:
        """Coordinator Probing Interface."""
        health_info = self.health_check()
        capabilities_info = {
            "agent_id": self.agent_id,
            "domain": self.domain,
            "authorized_sub_skills": self.librarian.list_available_actions(self.agent_id) if self.librarian else [],
        }
        if probe_type == "health":
            return health_info
        elif probe_type == "capabilities":
            return capabilities_info
        return {"health": health_info, "capabilities": capabilities_info}