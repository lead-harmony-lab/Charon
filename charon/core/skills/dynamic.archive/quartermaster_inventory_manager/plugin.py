"""Plugin entrypoint module for quartermaster_inventory_manager."""

import logging
from pathlib import Path
from typing import Any, Dict, Union
from charon.agents.quartermaster.inventory import check_inventory, log_inventory
from charon.agents.quartermaster.utils import _extract_param_dict

logger = logging.getLogger("CHAROND.Skills.QuartermasterInventoryManager")


def handle_check_inventory(
    params: Dict[str, Any], db_path: Path, raw_prompt: str = ""
) -> Dict[str, Any]:
    """Queries stock levels and bin locations in PartVault."""
    result = check_inventory(db_path=db_path, payload=params, raw_prompt=raw_prompt)
    return {"status": "success", "result": result}


def handle_log_inventory(
    params: Dict[str, Any], db_path: Path, raw_prompt: str = ""
) -> Dict[str, Any]:
    """Logs stock and metadata updates to PartVault."""
    result = log_inventory(db_path=db_path, payload=params, raw_prompt=raw_prompt)
    return {"status": "success", "result": result}


def execute_action(
    action_name: str,
    params: Dict[str, Any],
    db_path: Union[str, Path] = None,
    raw_prompt: str = "",
) -> Dict[str, Any]:
    """Main dispatch router for PartVault inventory operations."""
    if not db_path:
        return {"status": "error", "message": "Database path (db_path) is required."}

    path_obj = Path(db_path)

    if action_name == "check_inventory":
        return handle_check_inventory(params, path_obj, raw_prompt)
    elif action_name == "log_inventory":
        return handle_log_inventory(params, path_obj, raw_prompt)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'quartermaster_inventory_manager'."
    )