"""
charon/agents/runtime.py
System Version: v1.0.0 | File Revision: 3.3.0

Universal Data-Driven Agent Runtime.
Instantiated dynamically by the Router using metadata stored in SQLite agent_registry.
Acts as the hardware container that binds CBAC roles and executes an assigned Work Contract,
wrapped inside the BaseAgent Zero-Trust Ephemeral Envelope.
"""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
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

        # Resolve relative to current working directory if absolute path is provided
        path_obj = Path(raw_path)
        if path_obj.is_absolute():
            try:
                path_obj = path_obj.relative_to(Path.cwd())
            except ValueError:
                pass

        try:
            logger.debug(f"[{self.agent_id}] Importing {class_name} directly from {path_obj}")

            # Load the module directly from the file path, ignoring folder dots
            spec = importlib.util.spec_from_file_location(class_name, str(path_obj))
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load spec for {class_name} at {path_obj}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[class_name] = module # Register in sys.modules
            spec.loader.exec_module(module)

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

    def _ensure_work_contract(self, payload: Dict[str, Any]) -> bool:
        """Lazily hydrates work_contract if uninitialized during agent startup."""
        if self.work_contract is not None:
            return True

        # 1. Check if the payload explicitly defines the main contract
        contract_name = payload.get("skill_id")

        # 2. Fallback to Librarian SSOT lookup by bound role or agent ID
        if not contract_name and self.librarian:
            lookup_target = self.role_name or self.agent_id
            contract_name = self.librarian.get_default_action_for_role(lookup_target)

        if contract_name:
            self.work_contract = self._instantiate_contract(contract_name)
            if self.work_contract:
                self.work_contract.bind_telemetry(self.report_trace)
                return True

        return False

    def _execute_container(self, payload: Dict[str, Any]) -> BaseModel:
        """Internal execution dispatch guarded by BaseAgent CBAC checks."""
        self.report_progress("Initiating Work Contract for task assignment", phase="contract_start")

        # Lazily hydrate contract if missing at runtime
        if not self.work_contract and not self._ensure_work_contract(payload):
            raise RuntimeError(
                f"[FAIL-FAST] Agent '{self.agent_id}' has no bound Work Contract. Execution aborted."
            )

        authorized_tool_schemas = self.get_authorized_tool_schemas()
        logger.info(f"[{self.name}] Handing off payload to Work Contract: {self.work_contract.__class__.__name__}")

        constraints = payload.get("constraints") or payload.get("constraint_revision")

        result_artifact = self.work_contract.execute(
            task_payload=payload.get("task_payload", payload),
            authorized_tools=authorized_tool_schemas,
            coordinator_constraints=constraints
        )

        self.report_progress("Work Contract execution complete.", phase="contract_complete")
        return result_artifact