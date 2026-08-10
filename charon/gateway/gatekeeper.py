"""
charon/gateway/gatekeeper.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Gatekeeper State Manager & Tiered Risk Matrix
Intercepts Level 2/3 high-risk agent actions and handles human-in-the-loop authorization
using approval token IDs (appr_xxxxxx) and asyncio event signaling.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set, Tuple

from pydantic import BaseModel

logger = logging.getLogger("Charon.Gateway.Gatekeeper")

# ADR-003: Level 2/3 High-Risk Actions requiring mandatory human authorization
HIGH_RISK_ACTIONS: Set[str] = {
    # Hardware & Physical Operations (Level 2/3)
    "flash_hardware",
    "flash_firmware",
    "transmit_to_printer",
    # Code Execution & Terminal Commands (Level 2/3)
    "execute_sandbox_code",
    "run_existing_script",
    "execute_cli_command",
    "execute_shell_command",
    # OS & Service Mutations (Level 2/3)
    "manage_service",
    "package_manager",
    "modify_system_service",
    "update_kernel_config",
    # Workspace & Ledger Purging (Level 2/3)
    "delete_workspace",
    "purge_database",
    "expunge_record",
    "delete_rule",
    "purge_logs",
    "vacuum_database",
}


@dataclass
class PendingIntercept:
    """Represents an active authorization intercept held in memory."""

    approval_id: str
    agent: str
    extraction: Optional[BaseModel]
    user_raw_input: str
    event: asyncio.Event = field(default_factory=asyncio.Event)
    decision: Optional[str] = None  # "APPROVED", "REJECTED", "CANCEL", etc.


class GatekeeperManager:
    """Manages pre-flight authorization intercepts and pending execution state."""

    def __init__(self) -> None:
        self.pending_intercepts: Dict[str, PendingIntercept] = {}
        # Single-state pointers for backward compatibility
        self.pending_agent: Optional[str] = None
        self.pending_extraction: Optional[BaseModel] = None
        self.pending_raw_input: str = ""
        self.active_approval_id: Optional[str] = None

    @property
    def awaiting_approval(self) -> bool:
        """Dynamic check returning True if any active pending intercepts exist."""
        return len(self.pending_intercepts) > 0

    @awaiting_approval.setter
    def awaiting_approval(self, value: bool) -> None:
        """Compatibility setter allowing legacy direct assignment without state drift."""
        pass

    def requires_approval(self, extraction: Optional[BaseModel]) -> bool:
        """Check if extraction payload flags approval required or matches ADR-003 high-risk matrix."""
        if not extraction:
            return False

        # 1. Direct payload flag check
        if getattr(extraction, "requires_approval", False):
            return True

        # 2. Defense-in-depth check against Level 2/3 action matrix
        action = getattr(extraction, "action", "")
        if action and str(action).lower() in HIGH_RISK_ACTIONS:
            return True

        return False

    def requires_approval_raw(
        self,
        agent_name: str,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Helper to evaluate risk on raw agent/action strings during DAG step execution."""
        if str(action).lower() in HIGH_RISK_ACTIONS:
            return True
        if parameters and parameters.get("requires_approval"):
            return True
        return False

    def intercept_task(
        self,
        agent: str,
        extraction: Optional[BaseModel],
        user_raw_input: str,
    ) -> Tuple[str, str, str]:
        """
        Creates a pending approval token (appr_xxxxxx), sets state, and builds the manifest text.
        Returns: Tuple[manifest_message, action_name, approval_id]
        """
        approval_id = f"appr_{uuid.uuid4().hex[:8]}"
        intercept = PendingIntercept(
            approval_id=approval_id,
            agent=agent,
            extraction=extraction,
            user_raw_input=user_raw_input,
        )
        self.pending_intercepts[approval_id] = intercept

        # Update legacy single-state flags
        self.pending_agent = agent
        self.pending_extraction = extraction
        self.pending_raw_input = user_raw_input
        self.active_approval_id = approval_id

        action = getattr(extraction, "action", "unknown") if extraction else "unknown"
        param_details = []

        if extraction:
            if hasattr(extraction, "model_dump"):
                payload_dict = extraction.model_dump()
            elif hasattr(extraction, "dict"):
                payload_dict = extraction.dict()
            else:
                payload_dict = getattr(extraction, "__dict__", {})

            for key, val in payload_dict.items():
                if key not in ["requires_approval", "memory_candidate"] and val is not None:
                    formatted_val = (
                        f"\n    '''\n    {str(val).strip()}\n    '''"
                        if isinstance(val, str) and len(str(val)) > 80
                        else str(val)
                    )
                    param_details.append(f"  • {key}: {formatted_val}")

        manifest_params = (
            "\n".join(param_details) if param_details else "  • No parameters specified."
        )
        manifest_message = (
            f"\n🛡️ GATEKEEPER PRE-FLIGHT MANIFEST [{approval_id}]\n"
            f"─────────────────────────────────────────────────────────────\n"
            f" Target Agent : {agent}\n"
            f" Action        : {action}\n"
            f" Proposed Parameters:\n{manifest_params}\n"
            f"─────────────────────────────────────────────────────────────\n"
            f"Authorization required before proceeding.\n"
            f"Reply with 'proceed' or 'cancel' (Token: {approval_id})."
        )

        logger.warning(
            f"GATEKEEPER TRIGGERED [{approval_id}]: Action '{action}' by {agent} requires approval."
        )
        return manifest_message, str(action), approval_id

    def resolve_intercept(self, approval_id: str, decision: str) -> bool:
        """
        Resolves a pending intercept token, unblocking waiting execution threads.
        Called directly by gateway routes or WebSocket handlers.
        """
        norm_decision = decision.strip().upper()

        # 1. Resolve targeted approval_id if present
        if approval_id in self.pending_intercepts:
            intercept = self.pending_intercepts[approval_id]
            intercept.decision = norm_decision
            intercept.event.set()
            logger.info(f"Resolved Gatekeeper Intercept '{approval_id}' -> {norm_decision}")
            return True

        # 2. Fallback: Resolve active single-state intercept if active token matches
        if self.active_approval_id and self.active_approval_id in self.pending_intercepts:
            intercept = self.pending_intercepts[self.active_approval_id]
            intercept.decision = norm_decision
            intercept.event.set()
            logger.info(f"Resolved active Gatekeeper Intercept '{self.active_approval_id}' -> {norm_decision}")
            return True

        logger.warning(f"Attempted to resolve unknown or expired approval_id: {approval_id}")
        return False

    def submit_decision(self, approval_id: str, decision: str) -> bool:
        """Explicit alias for resolve_intercept to support direct core caller contracts."""
        return self.resolve_intercept(approval_id, decision)

    async def wait_for_decision(self, approval_id: str, timeout: float = 300.0) -> str:
        """
        Asynchronously waits for client authorization response targeting approval_id.
        Times out after `timeout` seconds (default 5 mins), returning "EXPIRED".
        """
        intercept = self.pending_intercepts.get(approval_id)
        if not intercept:
            logger.warning(f"wait_for_decision called on missing or expired approval_id: {approval_id}")
            return "EXPIRED"

        try:
            await asyncio.wait_for(intercept.event.wait(), timeout=timeout)
            return intercept.decision or "REJECTED"
        except asyncio.TimeoutError:
            logger.warning(f"Gatekeeper Intercept '{approval_id}' timed out after {timeout}s.")
            intercept.decision = "EXPIRED"
            return "EXPIRED"
        finally:
            # Safely release intercept memory AFTER waiting consumers process decision
            self.pending_intercepts.pop(approval_id, None)
            if self.active_approval_id == approval_id:
                self.reset()

    def handle_approval(self) -> Tuple[Optional[str], Optional[BaseModel], str]:
        """Legacy helper to approve and release the currently active payload."""
        agent = self.pending_agent
        extraction = self.pending_extraction
        raw_input = self.pending_raw_input

        if extraction and hasattr(extraction, "confirmed"):
            setattr(extraction, "confirmed", True)

        eff_input = (
            raw_input
            if "proceed" in raw_input.lower()
            else f"{raw_input} proceed"
        )
        self.reset()
        return agent, extraction, eff_input

    def reset(self) -> None:
        """Clear active gatekeeper pending pointers."""
        if self.active_approval_id and self.active_approval_id in self.pending_intercepts:
            self.pending_intercepts.pop(self.active_approval_id, None)

        self.pending_agent = None
        self.pending_extraction = None
        self.pending_raw_input = ""
        self.active_approval_id = None