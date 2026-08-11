"""Plugin entrypoint module for quartermaster_datasheet_fetcher."""

import logging
from pathlib import Path
from typing import Any, Dict, Union
from charon.agents.quartermaster.datasheets import fetch_datasheet

logger = logging.getLogger("CHAROND.Skills.QuartermasterDatasheetFetcher")


def handle_fetch_datasheet(
    params: Dict[str, Any],
    db_path: Path,
    datasheet_dir: Path,
    scout_agent: Any = None,
    raw_prompt: str = "",
) -> Dict[str, Any]:
    """Fetches, verifies, and stores PDF datasheets."""
    result = fetch_datasheet(
        db_path=db_path,
        datasheet_dir=datasheet_dir,
        scout_agent=scout_agent,
        payload=params,
        raw_prompt=raw_prompt,
    )
    return {"status": "success", "result": result}


def execute_action(
    action_name: str,
    params: Dict[str, Any],
    db_path: Union[str, Path] = None,
    datasheet_dir: Union[str, Path] = None,
    scout_agent: Any = None,
    raw_prompt: str = "",
) -> Dict[str, Any]:
    """Main dispatch router for datasheet retrieval operations."""
    if not db_path or not datasheet_dir:
        return {
            "status": "error",
            "message": "Both 'db_path' and 'datasheet_dir' parameters are required.",
        }

    db_obj = Path(db_path)
    ds_obj = Path(datasheet_dir)

    if action_name == "fetch_datasheet":
        return handle_fetch_datasheet(params, db_obj, ds_obj, scout_agent, raw_prompt)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'quartermaster_datasheet_fetcher'."
    )