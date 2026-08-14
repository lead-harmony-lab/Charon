"""
charon/agents/base.py
System Version: v0.4.1 | File Revision: 3.2.0

Module: Core BaseAgent interface defining unified probing, health checks,
declarative manifest capabilities, dynamic skill lookup via SkillLibrarian SSOT,
Chain-of-Thought (CoT) telemetry broadcasting, response reporting, and rich diagnostic
contract negotiation routines for all Charon specialist agents.
"""

from abc import ABC, abstractmethod
import json
import logging
import shutil
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union, Type
from pydantic import BaseModel

# Native Core Imports (Aligned with actual codebase)
from charon.core.coordinator.blackboard import TaskBlackboard, ThoughtType
from charon.core.skills import SkillLibrarian
from charon.gateway.gatekeeper import GatekeeperManager
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


class BaseWorkContract(ABC):
    """
    Abstract interface for Work Contracts (Default Actions).
    Encapsulates the LLM loop, localized tool routing, payload sanitization,
    and strict output schema enforcement.
    """
    artifact_schema: Type[BaseModel]

    def __init__(
        self,
        agent_id: str,
        gatekeeper: Optional[GatekeeperManager],
        tool_executor: Callable[[str, Dict[str, Any], str], Any],
        ledger: Optional[ExecutionLedger] = None
    ):
        """Constructor injection enforces strict dependencies."""
        self.agent_id = agent_id
        self.gatekeeper = gatekeeper
        self._execute_tool = tool_executor  # Bound to RuntimeAgent.execute_sub_skill
        self.ledger = ledger or ExecutionLedger()

    async def _invoke_tool_with_guard(
        self,
        action: str,
        parameters: Dict[str, Any],
        raw_user_input: str,
        task_id: str = "SYSTEM_TASK"
    ) -> Any:
        """
        The global chokepoint. All tool invocations must pass through this.
        Delegates CBAC (Capability-Based Access Control) to the Gatekeeper
        and records state transitions to the ExecutionLedger.
        """
        # 1. Evaluate against the Gatekeeper risk matrix
        if self.gatekeeper and self.gatekeeper.requires_approval_raw(self.agent_id, action, parameters):
            manifest, action_name, approval_id = self.gatekeeper.intercept_task(
                agent=self.agent_id,
                extraction=None,
                user_raw_input=raw_user_input
            )

            logger.info(f"[{self.agent_id}] Execution paused. Awaiting CBAC authorization: {approval_id}")
            decision = await self.gatekeeper.wait_for_decision(approval_id)

            if decision != "APPROVED":
                await self.ledger.log_event(
                    task_id=task_id,
                    event_type="TOOL_EXECUTION_BLOCKED",
                    role_name=self.agent_id,
                    tool_name=action,
                    data={"parameters": parameters, "decision": decision}
                )
                return (
                    f"EXECUTION BLOCKED by User/Gatekeeper. Decision: {decision}. "
                    "You do not have permission to execute this action."
                )

        # 2. If safe/approved, log the initiation and delegate back to execution bridge
        await self.ledger.log_event(
            task_id=task_id,
            event_type="TOOL_EXECUTION_STARTED",
            role_name=self.agent_id,
            tool_name=action,
            data={"parameters": parameters}
        )

        try:
            result = self._execute_tool(action, parameters, raw_user_input)

            await self.ledger.log_event(
                task_id=task_id,
                event_type="TOOL_EXECUTION_COMPLETED",
                role_name=self.agent_id,
                tool_name=action,
                data={"status": "success"}
            )
            return result
        except Exception as e:
            await self.ledger.log_event(
                task_id=task_id,
                event_type="TOOL_EXECUTION_FAILED",
                role_name=self.agent_id,
                tool_name=action,
                data={"error": str(e)}
            )
            logger.error(f"[{self.agent_id}] Tool {action} crashed: {e}")
            raise e

    @abstractmethod
    def execute(
        self,
        task_payload: Dict[str, Any],
        authorized_tools: List[Dict[str, Any]],  # Hydrated from SkillManifests
        coordinator_constraints: Optional[Dict[str, Any]] = None
    ) -> BaseModel:
        """Executes the contract and returns a strict Artifact or Diagnostic."""
        pass

    @abstractmethod
    def bind_telemetry(self, callback: Callable) -> None:
        """Binds standard agent telemetry trace reporting."""
        pass

    @abstractmethod
    def bind_cot(self, callback: Callable) -> None:
        """Binds Chain of Thought (CoT) internal reasoning reporting."""
        pass


class BaseAgent(ABC):
    """Abstract Base Class for all Charon Specialist Agents.

    Provides standardized probing, action discovery, health inspection,
    dynamic skill checkout via SkillLibrarian SSOT, Chain-of-Thought (CoT)
    telemetry broadcasting, user response reporting, and diagnostic contract negotiation.
    Delegates main execution flow to a bound BaseWorkContract.
    """

    name: str = "BaseAgent"
    agent_id: str = "base_agent"
    domain: str = "Generic Domain"

    supported_actions: Union[Dict[str, Any], List[str]] = {}
    system_requirements: List[str] = []
    consumed_artifacts: List[str] = []
    produced_artifacts: List[str] = []
    description: str = "Standard agent interface."

    work_contract: Optional[BaseWorkContract] = None

    def __init__(
        self,
        librarian: Optional[SkillLibrarian] = None,
        agent_id: Optional[str] = None,
        ledger: Optional[ExecutionLedger] = None,
    ) -> None:
        """Initializes the agent and binds the dynamic capability librarian."""
        self.librarian = librarian or SkillLibrarian.get_instance()
        self.ledger = ledger or ExecutionLedger()

        if agent_id:
            self.agent_id = agent_id
        elif not hasattr(self, "agent_id") or self.agent_id == "base_agent":
            self.agent_id = self.name.lower()

        self._telemetry_callback: Optional[Callable[[Dict[str, Any]], None]] = None

    def bind_telemetry(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Binds a thread-safe telemetry callback from the Dispatcher."""
        self._telemetry_callback = callback

    def set_telemetry_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Alias for bind_telemetry for external TUI/bus streaming compatibility."""
        self.bind_telemetry(callback)

    def log_cot(
        self,
        blackboard: TaskBlackboard,
        message: str,
        thought_type: ThoughtType = ThoughtType.ANALYSIS,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Broadcasts live internal reasoning (Chain-of-Thought) to the blackboard and telemetry bus."""
        blackboard.emit_thought(
            source_agent=self.agent_id,
            message=message,
            thought_type=thought_type,
            context_data=context,
            bus_callback=self._telemetry_callback,
        )
        logger.info(f"[{self.name} CoT - {thought_type.value}] {message}")

    def report_response(self, content: str, **kwargs: Any) -> None:
        """Emits an explicit final agent response message to the client CLI and streaming buses."""
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
        """Emits execution state changes for the UI Router HUD."""
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

    def evaluate_capability(
        self, action: str, params: Optional[Dict[str, Any]] = None
    ) -> SkillContract:
        """Evaluates whether the agent can handle the requested sub-action dynamically via DB SSOT."""
        if self.librarian:
            manifest = None
            if hasattr(self.librarian, "get_action_manifest"):
                manifest = self.librarian.get_action_manifest(action, self.agent_id)
            if not manifest and hasattr(self.librarian, "get_action_details"):
                manifest = self.librarian.get_action_details(action)

            if manifest:
                # manifest could be a Pydantic SkillManifest model or a dict
                if isinstance(manifest, dict):
                    sys_reqs = manifest.get("system_requirements", [])
                else:
                    sys_reqs = getattr(manifest, "system_requirements", [])

                if isinstance(sys_reqs, str):
                    try:
                        sys_reqs = json.loads(sys_reqs)
                    except Exception:
                        sys_reqs = []

                if not isinstance(sys_reqs, list):
                    sys_reqs = []

                missing_reqs = [
                    req for req in sys_reqs
                    if isinstance(req, str) and shutil.which(req) is None
                ]

                if missing_reqs:
                    return SkillContract(
                        status="CAPABILITY_GAP",
                        capability_type=CapabilityType.DYNAMIC_SKILL,
                        missing_prerequisites=missing_reqs,
                    )
                return SkillContract(status="READY", capability_type=CapabilityType.DYNAMIC_SKILL)

        return SkillContract(
            status="UNSUPPORTED_ACTION",
            capability_type=CapabilityType.UNSUPPORTED,
        )

    @abstractmethod
    def execute_task(
        self,
        task_payload: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
    ) -> BaseModel:
        """
        Primary execution dispatch inverted for the Work Contract paradigm.
        Takes a declarative task payload and delegates strictly to the work_contract.
        """
        pass

    def execute_sub_skill(
        self, action: str, parameters: Dict[str, Any], raw_prompt: str = ""
    ) -> Union[str, Dict[str, Any]]:
        """Isolated peripheral dispatcher used by Work Contracts to execute dynamically loaded skill plugins."""
        if not self.librarian:
            raise RuntimeError(f"[{self.name}] SkillLibrarian is not initialized. Cannot execute dynamic skills.")

        handler = self.librarian.check_out_skill(action, self.agent_id)
        if not handler:
            raise ValueError(
                f"[FAIL-FAST] Dynamic skill '{action}' is not registered or unauthorized for agent_id '{self.agent_id}'."
            )

        logger.info(f"[{self.name}] Executing peripheral dynamic skill: '{action}'")
        result = handler(agent_name=self.name, parameters=parameters, raw_prompt=raw_prompt)
        return result

    def health_check(self) -> Dict[str, Any]:
        """Performs runtime health, dependency checks, and dynamic skill capability aggregation from DB."""
        missing = [req for req in self.system_requirements if shutil.which(req) is None]
        dynamic_actions = self.librarian.list_available_actions(self.agent_id) if self.librarian else []

        return {
            "agent": self.name,
            "agent_id": self.agent_id,
            "domain": self.domain,
            "status": "degraded" if missing or not self.work_contract else "healthy",
            "missing_dependencies": missing,
            "has_work_contract": self.work_contract is not None,
            "dynamic_skills_available": dynamic_actions,
        }

    def probe(self, probe_type: str = "full") -> Dict[str, Any]:
        """
        Coordinator Probing Interface: Exposes Work Contract boundaries,
        produced schemas, and peripheral capabilities.
        """
        probe_type = str(probe_type).lower().strip()
        health_info = self.health_check()

        # Schema output serialization safely handles None contracts
        schema_json = {}
        contract_name = "None"
        if self.work_contract and hasattr(self.work_contract, "artifact_schema"):
            schema_json = self.work_contract.artifact_schema.model_json_schema()
            contract_name = self.work_contract.__class__.__name__

        capabilities_info = {
            "agent_name": self.name,
            "agent_id": self.agent_id,
            "domain": self.domain,
            "work_contract_role": contract_name,
            "produced_artifact_schema": schema_json,
            "authorized_sub_skills": self.librarian.list_available_actions(self.agent_id) if self.librarian else [],
        }

        if probe_type == "health":
            return health_info
        elif probe_type == "capabilities":
            return capabilities_info

        return {
            "agent": self.name,
            "agent_id": self.agent_id,
            "health": health_info,
            "capabilities": capabilities_info,
        }