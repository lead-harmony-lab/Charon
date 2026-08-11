"""Plugin entrypoint module for archivist_datasheet_rag."""

import logging
from typing import Any, Dict
from charon.agents.archivist.datasheets import DatasheetManager
from charon.agents.archivist.utils import _get_payload_val

logger = logging.getLogger("CHAROND.Skills.ArchivistDatasheetRAG")


def handle_index_datasheet(params: Dict[str, Any], ds_mgr: DatasheetManager) -> Dict[str, Any]:
    """Handles PDF parsing, SHA-256 hashing, chunking, and ChromaDB + SQLite sync."""
    result = ds_mgr.index_datasheet_action(params)
    return {"status": "success", "result": result}


def handle_search_datasheets(params: Dict[str, Any], ds_mgr: DatasheetManager) -> Dict[str, Any]:
    """Handles semantic RAG retrieval across indexed datasheet chunks."""
    raw_prompt = _get_payload_val(params, "raw_prompt", default="")
    result = ds_mgr.search_datasheets(params=params, raw_prompt=raw_prompt)
    return {"status": "success", "result": result}


def execute_action(
    action_name: str,
    params: Dict[str, Any],
    ds_mgr: DatasheetManager = None,
) -> Dict[str, Any]:
    """Main dispatch router for datasheet RAG operations."""
    if not ds_mgr:
        return {"status": "error", "message": "DatasheetManager instance required to execute skill."}

    if action_name == "index_datasheet":
        return handle_index_datasheet(params, ds_mgr)
    elif action_name == "search_datasheets":
        return handle_search_datasheets(params, ds_mgr)

    raise ValueError(f"Action '{action_name}' is not supported by skill 'archivist_datasheet_rag'.")