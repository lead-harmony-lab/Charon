"""
charon/agents/runtime.py
System Version: v0.5.3 | File Revision: 2.4.0

Universal Data-Driven Agent Runtime.
Instantiated dynamically by the Router using metadata stored in SQLite agent_registry.
Acts as the hardware container that executes an assigned Work Contract (Default Action).
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Union
from pydantic import BaseModel

from charon.agents.base import BaseAgent, BaseWorkContract
from charon.core.skills import SkillLibrarian
from charon.gateway.gatekeeper import GatekeeperManager
from charon.core.utils import normalize_role_name

logger = logging.getLogger("Charon.Agents.Runtime")


class RuntimeAgent(BaseAgent):
    """
    Universal concrete implementation of BaseAgent.
    Hydrated with persona, default_action_contract, and database metadata.
    Delegates all execution routing to its bound Work Contract.
    """

    def __init__(
        self,
        agent_id: str,
        default_action_contract: str,
        display_name: str = "",
        description: str = "",
        priority_weight: float = 1.0,
        heavy_model: str = "",
        librarian: Optional[SkillLibrarian] = None,
        **kwargs: Any,
    ) -> None:
        # BaseAgent applies utils.normalize_role_name during instantiation
        super().__init__(
            librarian=librarian,
            agent_id=agent_id,
            ledger=kwargs.get("ledger")
        )

        # Safely utilize the sanitized self.agent_id for fallbacks
        self.name = display_name or self.agent_id.capitalize()
        self.description = description
        self.priority_weight = priority_weight
        self.heavy_model = heavy_model

        # 1. Extract the Gatekeeper from kwargs (passed down by the Coordinator/Router)
        self.gatekeeper: Optional[GatekeeperManager] = kwargs.get("gatekeeper")
        if not self.gatekeeper:
            logger.warning(f"[{self.agent_id}] Initialized without GatekeeperManager! Guardrails disabled.")

        # 2. Hydrate the Execution Envelope (Work Contract)
        self.work_contract = self._instantiate_contract(default_action_contract)

        # We bind the agent's telemetry methods directly to the contract
        # so the contract can broadcast its internal LLM state to the Coordinator.
        if self.work_contract:
            self.work_contract.bind_telemetry(self.report_trace)
            # self.work_contract.bind_cot(self.log_cot)  # Enable when CoT integration is ready

    def _instantiate_contract(self, contract_name: str) -> Optional[BaseWorkContract]:
        """
        Dynamically loads the Work Contract class required by this agent.

        Injects the Gatekeeper and the `execute_sub_skill` bridge into the contract
        so it can securely route dynamic skill requests through CBAC and the Librarian SSOT.
        """
        logger.info(f"[{self.agent_id}] Binding Work Contract envelope: {contract_name}")

        # Note: Replace this block with your actual dynamic class registry loader.
        # ContractClass = get_contract_class_from_registry(contract_name)
        # if ContractClass:
        #     return ContractClass(
        #         agent_id=self.agent_id,
        #         gatekeeper=self.gatekeeper,
        #         tool_executor=self.execute_sub_skill
        #     )

        # Returning None here temporarily for architectural scaffolding;
        # normally this raises an error if the contract doesn't exist.
        return None

    def execute_task(
        self,
        task_payload: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
    ) -> BaseModel:
        """
        Primary execution dispatch:
        1. Validates Work Contract existence.
        2. Fetches all authorized peripheral tools (SkillManifests) from Librarian SSOT.
        3. Delegates execution loop to the assigned Work Contract.
        4. Returns a strictly validated Pydantic Artifact.
        """
        self.report_progress("Initiating Work Contract for task assignment", phase="contract_start")

        if not self.work_contract:
            raise RuntimeError(
                f"[FAIL-FAST] Agent '{self.agent_id}' has no bound Work Contract. "
                "Execution aborted."
            )

        if not self.librarian:
            raise RuntimeError(
                f"[FAIL-FAST] SkillLibrarian unavailable for runtime agent '{self.agent_id}'."
            )

        # 1. Fetch authorized peripheral capabilities (We do NOT execute them yet)
        authorized_tools_names = self.librarian.list_available_actions(self.agent_id)

        # Re-hydrate the full tool manifests so the Contract can natively translate them
        # into function-calling schemas (action_parameters) for the LLM.
        authorized_tools = []
        for tool_name in authorized_tools_names:
            manifest = self.librarian.get_action_manifest(tool_name, self.agent_id)
            if manifest:
                authorized_tools.append(manifest)

        # 2. Delegate to the Work Contract wrapper
        logger.info(f"[{self.name}] Handing off payload to Work Contract: {self.work_contract.__class__.__name__}")

        result_artifact = self.work_contract.execute(
            task_payload=task_payload,
            authorized_tools=authorized_tools,
            coordinator_constraints=constraints
        )

        self.report_progress("Work Contract execution complete.", phase="contract_complete")
        return result_artifact