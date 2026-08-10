"""Plugin entrypoint module for archivist_vector_ledger."""

import logging
from typing import Any, Dict
from charon.agents.archivist.ledger import LedgerManager
from charon.agents.archivist.utils import _get_payload_val

logger = logging.getLogger("CHAROND.Skills.ArchivistVectorLedger")


def handle_store_record(params: Dict[str, Any], ledger_mgr: LedgerManager) -> Dict[str, Any]:
    """Handles operational rule/fact storage."""
    result = ledger_mgr.store_record(params)
    return {"status": "success", "result": result}


def handle_search_ledger(
    params: Dict[str, Any], ledger_mgr: LedgerManager, fallback_fn=None
) -> Dict[str, Any]:
    """Handles vector memory query execution."""
    raw_prompt = _get_payload_val(params, "raw_prompt", default="")
    result = ledger_mgr.search_ledger(
        params=params,
        datasheet_search_fallback=fallback_fn or (lambda p, raw_prompt="": "No fallback available."),
        raw_prompt=raw_prompt,
    )
    return {"status": "success", "result": result}


def handle_expunge_record(params: Dict[str, Any], ledger_mgr: LedgerManager) -> Dict[str, Any]:
    """Handles record deletion via substring or distance match."""
    raw_prompt = _get_payload_val(params, "raw_prompt", default="")
    result = ledger_mgr.expunge_record(params=params, raw_prompt=raw_prompt)
    return {"status": "success", "result": result}


def handle_summarize_ledger(params: Dict[str, Any], ledger_mgr: LedgerManager) -> Dict[str, Any]:
    """Generates categorized summary of active vector memory."""
    result = ledger_mgr.summarize_ledger(params=params)
    return {"status": "success", "result": result}


def execute_action(
    action_name: str,
    params: Dict[str, Any],
    ledger_mgr: LedgerManager = None,
    fallback_fn=None,
) -> Dict[str, Any]:
    """Main dispatch router for vector ledger operations."""
    if not ledger_mgr:
        return {"status": "error", "message": "LedgerManager instance required to execute skill."}

    if action_name == "store_record":
        return handle_store_record(params, ledger_mgr)
    elif action_name == "search_ledger":
        return handle_search_ledger(params, ledger_mgr, fallback_fn)
    elif action_name == "expunge_record":
        return handle_expunge_record(params, ledger_mgr)
    elif action_name == "summarize_ledger":
        return handle_summarize_ledger(params, ledger_mgr)

    raise ValueError(f"Action '{action_name}' is not supported by skill 'archivist_vector_ledger'.")