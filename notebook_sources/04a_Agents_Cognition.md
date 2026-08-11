# Subsystem Domain Context: 04a_Agents_Cognition
> **Generated:** 2026-08-11 06:46 UTC  
> **Charon Core Version:** v8.0  
> **Git Branch:** `Streamline-Dynamic-Routing` | **Commit:** `c416670`

---

## Target File: `charon/agents/base.py`

```python
"""
charon/agents/base.py
System Version: v0.3.3 | File Revision: 2.8.0

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
from typing import Any, Callable, Dict, List, Optional, Union
from pydantic import BaseModel

from charon.core.contracts import (
    CapabilityNegotiation,
    ContractResponse,
    DiagnosticGap,
    ExecutionStatus,
    GapType,
    ToolManifest,
)
from charon.core.coordinator.blackboard import TaskBlackboard, ThoughtType
from charon.core.skills import SkillLibrarian

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
    """Abstract Base Class for all Charon Specialist Agents.

    Provides standardized probing, action discovery, health inspection,
    dynamic skill checkout via SkillLibrarian SSOT, Chain-of-Thought (CoT)
    telemetry broadcasting, user response reporting, and diagnostic contract negotiation.
    """

    name: str = "BaseAgent"
    agent_id: str = "base_agent"
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
    ) -> None:
        """Initializes the agent and binds the dynamic capability librarian."""
        self.librarian = librarian or SkillLibrarian.get_instance()
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

    def report_action(self, action: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Emits a sub-action step specifically for execution drop-down logs."""
        if self._telemetry_callback:
            self._telemetry_callback({
                "type": "agent_action",
                "agent_name": getattr(self, "name", self.__class__.__name__),
                "data": {"action": action, **(details or {})},
            })

    def evaluate_capability(
        self, action: str, params: Optional[Dict[str, Any]] = None
    ) -> SkillContract:
        """Evaluates whether the agent can handle the requested action natively or dynamically via DB SSOT."""
        is_native = False
        if isinstance(self.supported_actions, dict):
            is_native = action in self.supported_actions or action in getattr(self, "ACTION_MAP", {})
        elif isinstance(self.supported_actions, list):
            is_native = action in self.supported_actions

        if is_native:
            missing_reqs = [req for req in self.system_requirements if shutil.which(req) is None]
            if missing_reqs:
                return SkillContract(
                    status="CAPABILITY_GAP",
                    capability_type=CapabilityType.NATIVE,
                    missing_prerequisites=missing_reqs,
                )
            return SkillContract(status="READY", capability_type=CapabilityType.NATIVE)

        if self.librarian:
            manifest = None
            if hasattr(self.librarian, "get_action_manifest"):
                manifest = self.librarian.get_action_manifest(action, self.agent_id)
            if not manifest and hasattr(self.librarian, "get_action_details"):
                manifest = self.librarian.get_action_details(action)

            if manifest:
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
    def execute(
        self,
        action: str,
        parameters: Dict[str, Any],
        raw_prompt: str = "",
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """Primary routing switch for executing agent actions. Must fail fast if unsupported."""
        pass

    def execute_dynamic(
        self, action: str, parameters: Dict[str, Any], raw_prompt: str = ""
    ) -> Union[str, Dict[str, Any]]:
        """Isolated dispatcher for executing dynamically loaded skill plugins bound in DB SSOT."""
        if not self.librarian:
            raise RuntimeError(f"[{self.name}] SkillLibrarian is not initialized. Cannot execute dynamic skills.")

        handler = self.librarian.check_out_skill(action, self.agent_id)
        if not handler:
            raise ValueError(
                f"[FAIL-FAST] Dynamic skill '{action}' is not registered or unauthorized for agent_id '{self.agent_id}'."
            )

        logger.info(f"[{self.name}] Dispatching dynamic skill execution for action: '{action}'")
        result = handler(agent_name=self.name, parameters=parameters, raw_prompt=raw_prompt)

        # Broadcast output via agent_response event if text content is produced
        response_text = ""
        if isinstance(result, str):
            response_text = result
        elif isinstance(result, dict):
            response_text = str(
                result.get("result") or result.get("content") or result.get("output") or ""
            )

        if response_text:
            self.report_response(response_text)

        return result

    def health_check(self) -> Dict[str, Any]:
        """Performs runtime health, dependency checks, and dynamic skill capability aggregation from DB."""
        missing = [req for req in self.system_requirements if shutil.which(req) is None]
        dynamic_actions = self.librarian.list_available_actions(self.agent_id) if self.librarian else []

        return {
            "agent": self.name,
            "agent_id": self.agent_id,
            "domain": self.domain,
            "status": "degraded" if missing else "healthy",
            "missing_dependencies": missing,
            "dynamic_skills_available": dynamic_actions,
            "native_actions_supported": list(self.supported_actions.keys()) if isinstance(self.supported_actions, dict) else self.supported_actions,
        }

    def probe(self, probe_type: str = "full") -> Dict[str, Any]:
        """Coordinator Probing Interface: Exposes health status, capability matrix, and domain metadata."""
        probe_type = str(probe_type).lower().strip()
        health_info = self.health_check()

        capabilities_info = {
            "agent_name": self.name,
            "agent_id": self.agent_id,
            "domain": self.domain,
            "native_actions": self.supported_actions,
            "dynamic_skills": self.librarian.list_available_actions(self.agent_id) if self.librarian else [],
            "manifest": self.get_manifest().model_dump(),
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

    def get_manifest(self) -> ToolManifest:
        """Returns declarative capability contract/manifest including native and dynamic skills from DB SSOT."""
        actions_list: List[str] = []
        if isinstance(self.supported_actions, dict):
            for category, acts in self.supported_actions.items():
                if isinstance(acts, list):
                    actions_list.extend(acts)
                else:
                    actions_list.append(str(acts))
        elif isinstance(self.supported_actions, list):
            actions_list.extend(self.supported_actions)

        dynamic_actions = self.librarian.list_available_actions(self.agent_id) if self.librarian else []
        all_actions = sorted(list(set(actions_list + dynamic_actions)))

        return ToolManifest(
            agent_name=self.name,
            supported_actions=all_actions,
            system_requirements=self.system_requirements,
            consumed_artifacts=self.consumed_artifacts,
            produced_artifacts=self.produced_artifacts,
            description=f"{self.domain}: {self.description}",
        )
```

────────────────────────────────────────────────────────────────────────────────

