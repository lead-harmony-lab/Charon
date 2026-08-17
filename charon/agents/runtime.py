"""
charon/agents/runtime.py
System Version: v1.0.0 | File Revision: 3.1.0

Universal Data-Driven Agent Runtime.
Instantiated dynamically by the Router using metadata stored in SQLite agent_registry.
Acts as the hardware container that binds CBAC roles and executes an assigned Work Contract,
wrapped inside the BaseAgent Zero-Trust Ephemeral Envelope.
"""

import importlib
import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel

from charon.agents.base import BaseAgent
from charon.core.permissions.contract_policies import BaseContractPolicy
from charon.core.skills import SkillLibrarian
from charon.gateway.gatekeeper import GatekeeperManager

logger = logging.getLogger("Charon.Agents.Runtime")


class RuntimeAgent(BaseAgent):
    """
    Universal concrete implementation of BaseAgent.
    Hydrated with persona, CBAC role, default_action_contract, and database metadata.
    Delegates tool calls through BaseAgent.execute_sub_skill for CBAC validation.
    """

    def __init__(
        self,
        agent_id: str,
        default_action_contract: str,
        role_name: Optional[str] = None,
        display_name: str = "",
        description: str = "",
        priority_weight: float = 1.0,
        heavy_model: str = "",
        librarian: Optional[SkillLibrarian] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            librarian=librarian,
            agent_id=agent_id,
            role_name=role_name,
            ledger=kwargs.get("ledger"),
        )

        self.name = display_name or self.agent_id.capitalize()
        self.description = description
        self.priority_weight = priority_weight
        self.heavy_model = heavy_model

        # Extract GatekeeperManager from context kwargs
        self.gatekeeper: Optional[GatekeeperManager] = kwargs.get("gatekeeper")
        if not self.gatekeeper:
            logger.warning(
                f"[{self.agent_id}] Initialized without GatekeeperManager! Manual approval guardrails disabled."
            )

        # Hydrate the Execution Envelope (Work Contract)
        self.work_contract = self._instantiate_contract(default_action_contract)

        # Bind telemetry handlers
        if self.work_contract:
            self.work_contract.bind_telemetry(self.report_trace)

    def _instantiate_contract(self, contract_name: str) -> Optional[BaseContractPolicy]:
        """
        Dynamically loads the Work Contract class required by this agent.
        Queries database via SkillLibrarian for file location and instantiates contract handler.
        """
        logger.info(f"[{self.agent_id}] Binding Work Contract envelope '{contract_name}' (Role: {self.role_name})")

        if not self.librarian:
            logger.error(f"[{self.agent_id}] Librarian missing. Cannot resolve contract '{contract_name}'.")
            return None

        contract_manifest = self.librarian.get_action_manifest(contract_name)
        if not contract_manifest:
            logger.error(f"[{self.agent_id}] Contract '{contract_name}' not found in DB registry.")
            return None

        get_val = lambda k: contract_manifest.get(k) if isinstance(contract_manifest, dict) else getattr(contract_manifest, k, None)

        raw_path = get_val("entry_file_path")
        class_name = get_val("handler_name")

        if not raw_path or not class_name:
            logger.error(f"[{self.agent_id}] Invalid registry entry for '{contract_name}'. Missing file/handler.")
            return None

        module_path = raw_path
        if module_path.endswith('.py'):
            module_path = module_path[:-3]
        module_path = module_path.replace('/', '.').replace('\\', '.')

        try:
            logger.debug(f"[{self.agent_id}] Importing {class_name} from {module_path}")
            module = importlib.import_module(module_path)
            ContractClass = getattr(module, class_name)

            return ContractClass(
                agent_id=self.agent_id,
                gatekeeper=self.gatekeeper,
                tool_executor=self.execute_sub_skill,
                ledger=self.ledger
            )

        except (ImportError, AttributeError, Exception) as e:
            logger.error(f"[{self.agent_id}] Critical failure instantiating contract {contract_name}: {e}")
            return None

    def _execute_container(self, payload: Dict[str, Any]) -> BaseModel:
        """
        Internal execution dispatch (called by BaseAgent.execute_task after Zero-Trust envelope locks).
        1. Validates Work Contract existence.
        2. Fetches 'blinded' authorized tool schemas via BaseAgent.
        3. Invokes Work Contract execution loop guarded by BaseAgent CBAC checks.
        """
        self.report_progress("Initiating Work Contract for task assignment", phase="contract_start")

        if not self.work_contract:
            raise RuntimeError(
                f"[FAIL-FAST] Agent '{self.agent_id}' has no bound Work Contract. Execution aborted."
            )

        # BaseAgent restricts and provides this list via The Blinder
        authorized_tool_schemas = self.get_authorized_tool_schemas()

        logger.info(f"[{self.name}] Handing off payload to Work Contract: {self.work_contract.__class__.__name__}")

        # Ingest both task payload and constraints (if generated by constraints.py)
        constraints = payload.get("constraints") or payload.get("constraint_revision")

        result_artifact = self.work_contract.execute(
            task_payload=payload.get("task_payload", payload),
            authorized_tools=authorized_tool_schemas,
            coordinator_constraints=constraints
        )

        self.report_progress("Work Contract execution complete.", phase="contract_complete")
        return result_artifact