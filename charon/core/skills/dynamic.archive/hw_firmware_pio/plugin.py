"""Plugin entrypoint module for hw_firmware_pio."""

import logging
from typing import Any, Dict

from charon.agents.spark.firmware import (
    handle_compile_firmware,
    handle_flash_hardware,
)

logger = logging.getLogger("CHAROND.Skills.HwFirmwarePio")


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router for PlatformIO firmware actions."""
    pio_cmd = params.get("pio_cmd", "pio")
    raw_prompt = params.get("raw_prompt", "")

    if action_name == "compile_firmware":
        result = handle_compile_firmware(
            pio_cmd=pio_cmd, payload=None, params=params, raw_prompt=raw_prompt
        )
        return {"status": "success", "result": result}

    elif action_name == "flash_hardware":
        result = handle_flash_hardware(
            pio_cmd=pio_cmd, payload=None, params=params, raw_prompt=raw_prompt
        )
        return {"status": "success", "result": result}

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'hw_firmware_pio'."
    )