"""
charon/agents/steward/home_assistant.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Home Assistant state and appliance operations.
"""

import logging
from typing import Any, Dict, Optional
from charon.tools.iot import make_ha_request

logger = logging.getLogger("Charon.Steward.HomeAssistant")


def control_appliance(
    ha_url: str,
    ha_token: str,
    target_device: Optional[str],
    command: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Controls a Home Assistant entity (e.g., switch, light, relay)."""
    if not target_device or "." not in target_device:
        return {
            "status": "error",
            "message": f"Invalid target_device format '{target_device}'. Expected 'domain.entity_id'.",
        }

    domain, _ = target_device.split(".", 1)
    service = command or "turn_on"
    endpoint = f"/api/services/{domain}/{service}"

    req_body = {"entity_id": target_device}
    if payload:
        req_body.update(payload)

    logger.info(f"[STEWARD] Controlling appliance {target_device} -> {service}")
    res = make_ha_request(ha_url, ha_token, endpoint, method="POST", payload=req_body)
    return {
        "action": "control_appliance",
        "target_device": target_device,
        "command": service,
        "response": res,
    }


def read_sensor_net(
    ha_url: str, ha_token: str, target_device: Optional[str] = None
) -> Dict[str, Any]:
    """Queries state and attributes for a target entity or lists all entities."""
    if target_device:
        endpoint = f"/api/states/{target_device}"
        res = make_ha_request(ha_url, ha_token, endpoint, method="GET")
        return {
            "action": "read_sensor_net",
            "target_device": target_device,
            "response": res,
        }
    else:
        return discover_devices(ha_url, ha_token)


def discover_devices(ha_url: str, ha_token: str) -> Dict[str, Any]:
    """Fetches all active states and entities registered in Home Assistant."""
    endpoint = "/api/states"
    res = make_ha_request(ha_url, ha_token, endpoint, method="GET")
    if res.get("status") == "success":
        states = res.get("data", [])
        summary = [
            {
                "entity_id": item.get("entity_id"),
                "state": item.get("state"),
                "friendly_name": item.get("attributes", {}).get("friendly_name"),
            }
            for item in states
            if isinstance(item, dict)
        ]
        return {
            "action": "discover_devices",
            "count": len(summary),
            "devices": summary,
        }
    return res