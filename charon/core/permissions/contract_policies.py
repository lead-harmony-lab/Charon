"""
charon/core/permissions/contract_policies.py
System Version: v0.5.0 | File Revision: 3.1.0

Module: Core BaseContractPolicy handling standard telemetry, Gatekeeper intercepts,
ledger logging, and the batch tool execution loop via injected tool_executor.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import BaseModel

from charon.core.permissions.middleware import PermissionDeniedError
from charon.gateway.gatekeeper import GatekeeperManager
from charon.telemetry.ledger import ExecutionLedger

logger = logging.getLogger("charon.contracts.base")


class BaseContractPolicy(ABC):
    """
    Abstract Base Work Contract.
    Manages LLM reasoning loops, tool invocation batching via `tool_executor`,
    Gatekeeper intercepts, and output schema validation.
    """
    artifact_schema: Type[BaseModel]

    def __init__(
            self,
            agent_id: str,
            gatekeeper: Optional[GatekeeperManager],
            tool_executor: Callable[..., Any],
            ledger: Optional[ExecutionLedger] = None,
    ) -> None:
        self.agent_id = agent_id
        self.gatekeeper = gatekeeper
        self._execute_tool = tool_executor  # Injected callback -> BaseAgent.execute_sub_skill
        self.ledger = ledger or ExecutionLedger()

        self._telemetry_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._cot_callback: Optional[Callable[..., None]] = None

    def bind_telemetry(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Binds standard agent telemetry trace reporting."""
        self._telemetry_callback = callback

    def bind_cot(self, callback: Callable[..., None]) -> None:
        """Binds Chain-of-Thought reasoning callback."""
        self._cot_callback = callback

    async def _invoke_tool_with_guard(
            self,
            action: str,
            parameters: Dict[str, Any],
            raw_user_input: str,
            task_id: str = "SYSTEM_TASK",
            execution_context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Global execution chokepoint. Checks Gatekeeper policy, logs state
        transitions to ExecutionLedger, and delegates execution to `_execute_tool`.
        """
        # 1. Gatekeeper safety intercept check
        if self.gatekeeper and self.gatekeeper.requires_approval_raw(self.agent_id, action, parameters):
            manifest, action_name, approval_id = self.gatekeeper.intercept_task(
                agent=self.agent_id,
                extraction=None,
                user_raw_input=raw_user_input
            )

            logger.info(f"[{self.agent_id}] Execution paused. Awaiting authorization: {approval_id}")
            decision = await self.gatekeeper.wait_for_decision(approval_id)

            if decision != "APPROVED":
                await self.ledger.log_event(
                    task_id=task_id,
                    event_type="TOOL_EXECUTION_BLOCKED",
                    role_name=self.agent_id,
                    tool_name=action,
                    data={"parameters": parameters, "decision": decision}
                )
                return f"EXECUTION BLOCKED by User/Gatekeeper. Decision: {decision}."

        # 2. Telemetry log start
        await self.ledger.log_event(
            task_id=task_id,
            event_type="TOOL_EXECUTION_STARTED",
            role_name=self.agent_id,
            tool_name=action,
            data={"parameters": parameters}
        )

        # 3. Execute via injected runtime tool_executor
        try:
            result = self._execute_tool(
                action=action,
                parameters=parameters,
                raw_prompt=raw_user_input,
                execution_context=execution_context,
            )

            await self.ledger.log_event(
                task_id=task_id,
                event_type="TOOL_EXECUTION_COMPLETED",
                role_name=self.agent_id,
                tool_name=action,
                data={"status": "success"}
            )
            return result

        except PermissionDeniedError as e:
            await self.ledger.log_event(
                task_id=task_id,
                event_type="TOOL_EXECUTION_DENIED",
                role_name=self.agent_id,
                tool_name=action,
                data={"error": str(e)}
            )
            logger.warning(f"[{self.agent_id}] CBAC Block for tool '{action}': {e}")
            return f"PERMISSION DENIED by CBAC Policy: {e}"

        except Exception as e:
            await self.ledger.log_event(
                task_id=task_id,
                event_type="TOOL_EXECUTION_FAILED",
                role_name=self.agent_id,
                tool_name=action,
                data={"error": str(e)}
            )
            logger.error(f"[{self.agent_id}] Tool '{action}' execution error: {e}")
            raise e

    async def execute_tool_loop(
            self,
            tool_calls: List[Dict[str, Any]],
            raw_user_input: str,
            task_id: str = "SYSTEM_TASK",
            execution_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Iterates over requested tool call payloads from LLM generations,
        dispatching each through the guarded execution chokepoint.

        Args:
            tool_calls: List of requested tool invocations e.g. [{'tool_name': 'x', 'parameters': {...}}]
            raw_user_input: User prompt string used for Gatekeeper context and auditing.
            task_id: Active blackboard task identifier.
            execution_context: Scope metadata (e.g. workspace path bounds).

        Returns:
            List of execution results containing status and structured outputs.
        """
        tool_outputs = []

        for call in tool_calls:
            tool_name = call.get("tool_name") or call.get("action") or call.get("name")
            parameters = call.get("parameters", {})

            if not tool_name:
                tool_outputs.append({
                    "tool_name": "unknown",
                    "status": "ERROR",
                    "result": "Invalid tool call format: missing tool name."
                })
                continue

            try:
                result = await self._invoke_tool_with_guard(
                    action=tool_name,
                    parameters=parameters,
                    raw_user_input=raw_user_input,
                    task_id=task_id,
                    execution_context=execution_context,
                )

                status = "SUCCESS"
                if isinstance(result, str) and (
                        result.startswith("PERMISSION DENIED") or result.startswith("EXECUTION BLOCKED")
                ):
                    status = "BLOCKED"

                tool_outputs.append({
                    "tool_name": tool_name,
                    "status": status,
                    "result": result,
                })

            except Exception as e:
                tool_outputs.append({
                    "tool_name": tool_name,
                    "status": "ERROR",
                    "result": f"Execution failed: {str(e)}",
                })

        return tool_outputs

    @abstractmethod
    def execute(
            self,
            task_payload: Dict[str, Any],
            authorized_tools: List[Dict[str, Any]],
            coordinator_constraints: Optional[Dict[str, Any]] = None,
    ) -> BaseModel:
        """Executes the contract reasoning loop and returns a validated Pydantic Artifact."""
        pass