"""Plugin entrypoint module for hw_eda_kicad."""

import logging
from typing import Any, Dict

from charon.agents.spark.eda import (
    handle_export_bom,
    handle_export_gerbers,
)

logger = logging.getLogger("CHAROND.Skills.HwEdaKicad")


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router for KiCad EDA actions."""
    kicad_cli = params.get("kicad_cli", "kicad-cli")
    raw_prompt = params.get("raw_prompt", "")

    if action_name == "export_gerbers":
        result = handle_export_gerbers(
            kicad_cli=kicad_cli, payload=None, params=params, raw_prompt=raw_prompt
        )
        return {"status": "success", "result": result}

    elif action_name == "export_bom":
        result = handle_export_bom(
            kicad_cli=kicad_cli, payload=None, params=params, raw_prompt=raw_prompt
        )
        return {"status": "success", "result": result}

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'hw_eda_kicad'."
    )