"""
charon/agents/steward/utils.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Internal helpers and constants for The Steward.
"""

import logging
from typing import Any, Dict, Optional, Union

from charon.intent import DynamicActionPayload

logger = logging.getLogger("Charon.Steward.Utils")

VALID_STEWARD_ACTIONS = (
    "control_appliance",
    "publish_mqtt",
    "read_sensor_net",
    "discover_devices",
)

ACTION_MAP = {
    "control_appliance": "control_appliance",
    "control": "control_appliance",
    "set_state": "control_appliance",
    "toggle": "control_appliance",
    "publish_mqtt": "publish_mqtt",
    "mqtt": "publish_mqtt",
    "publish": "publish_mqtt",
    "read_sensor_net": "read_sensor_net",
    "read_sensor": "read_sensor_net",
    "get_state": "read_sensor_net",
    "read": "read_sensor_net",
    "discover_devices": "discover_devices",
    "discover": "discover_devices",
    "list_devices": "discover_devices",
}


def extract_param_dict(
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]]
) -> Dict[str, Any]:
    """Helper utility to extract parameter dictionary from DynamicActionPayload or standard dict."""
    if isinstance(payload, DynamicActionPayload):
        return payload.params or {}
    elif isinstance(payload, dict):
        return payload
    return {}


def normalize_and_validate_payload(
    action: str, raw_params: Dict[str, Any]
) -> DynamicActionPayload:
    """Normalizes the requested action and parses into a validated DynamicActionPayload."""
    payload_dict = dict(raw_params)
    action_clean = str(action).lower().strip()
    normalized_action = ACTION_MAP.get(action_clean, action_clean)

    params_data = {k: v for k, v in payload_dict.items() if k != "action"}

    try:
        if "params" in payload_dict and isinstance(payload_dict["params"], dict):
            params_data = payload_dict["params"]

        return DynamicActionPayload(
            action=normalized_action,
            params=params_data,
        )
    except Exception as e:
        logger.warning(
            f"[STEWARD] Payload validation warning ({e}). Executing fallback construction..."
        )
        fallback_action = (
            normalized_action
            if normalized_action in VALID_STEWARD_ACTIONS
            else "read_sensor_net"
        )
        return DynamicActionPayload(
            action=fallback_action,
            params=params_data,
        )