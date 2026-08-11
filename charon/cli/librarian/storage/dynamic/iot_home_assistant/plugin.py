"""Plugin entrypoint module for iot_home_assistant."""

import logging
import os
from typing import Any, Dict, Optional

from charon.agents.steward.home_assistant import (
    control_appliance as ha_control_appliance,
    discover_devices as ha_discover_devices,
    read_sensor_net as ha_read_sensor_net,
)

logger = logging.getLogger("CHAROND.Skills.IotHomeAssistant")


def _resolve_credentials(params: Dict[str, Any]) -> tuple[str, str]:
    """Helper to resolve Home Assistant URL and token from params or env vars."""
    ha_url = (
        params.get("ha_url")
        or os.getenv("HOMEASSISTANT_URL", "http://homeassistant.local:8123")
    ).rstrip("/")
    ha_token = params.get("ha_token") or os.getenv("HOMEASSISTANT_TOKEN", "")
    return ha_url, ha_token


def handle_control_appliance(params: Dict[str, Any]) -> Dict[str, Any]:
    """Controls a Home Assistant entity."""
    ha_url, ha_token = _resolve_credentials(params)
    target_device = (
        params.get("target_device")
        or params.get("entity_id")
        or params.get("device")
    )
    command = params.get("command") or params.get("service")
    payload = params.get("payload") or params.get("data")

    if not target_device:
        return {
            "status": "error",
            "message": "Missing required 'target_device' or 'entity_id' parameter.",
        }

    logger.info(f"Controlling Home Assistant entity: {target_device} -> {command}")
    res = ha_control_appliance(
        ha_url=ha_url,
        ha_token=ha_token,
        target_device=target_device,
        command=command,
        payload=payload,
    )
    return {"status": "success", "result": res}


def handle_read_sensor_net(params: Dict[str, Any]) -> Dict[str, Any]:
    """Queries entity state or reads overall sensor net."""
    ha_url, ha_token = _resolve_credentials(params)
    target_device = (
        params.get("target_device")
        or params.get("entity_id")
        or params.get("device")
    )

    logger.info(f"Querying sensor net state for device: {target_device or 'ALL'}")
    res = ha_read_sensor_net(
        ha_url=ha_url, ha_token=ha_token, target_device=target_device
    )
    return {"status": "success", "result": res}


def handle_discover_devices(params: Dict[str, Any]) -> Dict[str, Any]:
    """Discovers registered devices and entities."""
    ha_url, ha_token = _resolve_credentials(params)

    logger.info("Executing Home Assistant entity discovery...")
    res = ha_discover_devices(ha_url=ha_url, ha_token=ha_token)
    return {"status": "success", "result": res}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router for iot_home_assistant."""
    if action_name == "control_appliance":
        return handle_control_appliance(params)
    elif action_name == "read_sensor_net":
        return handle_read_sensor_net(params)
    elif action_name == "discover_devices":
        return handle_discover_devices(params)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'iot_home_assistant'."
    )