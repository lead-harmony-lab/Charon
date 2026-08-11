"""Plugin entrypoint module for quartermaster_bom_auditor."""

import logging
from pathlib import Path
from typing import Any, Dict, Union
from charon.agents.quartermaster.bom import generate_bom

logger = logging.getLogger("CHAROND.Skills.QuartermasterBOMAuditor")


def handle_generate_bom(
    params: Dict[str, Any], db_path: Path, raw_prompt: str = ""
) -> Dict[str, Any]:
    """Audits project assembly BOM against PartVault stock."""
    result = generate_bom(db_path=db_path, payload=params, raw_prompt=raw_prompt)
    return {"status": "success", "result": result}


def execute_action(
    action_name: str,
    params: Dict[str, Any],
    db_path: Union[str, Path] = None,
    raw_prompt: str = "",
) -> Dict[str, Any]:
    """Main dispatch router for BOM auditing operations."""
    if not db_path:
        return {"status": "error", "message": "Database path (db_path) is required."}

    path_obj = Path(db_path)

    if action_name == "generate_bom":
        return handle_generate_bom(params, path_obj, raw_prompt)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'quartermaster_bom_auditor'."
    )