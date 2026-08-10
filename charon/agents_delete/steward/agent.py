"""
charon/agents/steward/agent.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Primary agent router class for The Steward.
Inherits from BaseAgent for unified system probing and capability discovery.
Updated for dynamic intent schemas.
"""

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Union

from charon.agents.base import BaseAgent
from charon.agents.steward.home_assistant import (
    control_appliance,
    discover_devices,
    read_sensor_net,
)
from charon.agents.steward.mqtt import publish_mqtt
from charon.config.paths import ensure_ecosystem_directories
from charon.core.skills import SkillLibrarian
from charon.intent import DynamicActionPayload

logger = logging.getLogger("charon.agents.steward")

VALID_STEWARD_ACTIONS = (
    "control_appliance",
    "publish_mqtt",
    "read_sensor_net",
    "discover_devices",
)

ACTION_MAP = {
    "control_appliance": "control_appliance",
    "control": "control_appliance",
    "turn_on": "control_appliance",
    "turn_off": "control_appliance",
    "toggle": "control_appliance",
    "appliance": "control_appliance",
    "publish_mqtt": "publish_mqtt",
    "publish": "publish_mqtt",
    "mqtt": "publish_mqtt",
    "mqtt_publish": "publish_mqtt",
    "read_sensor_net": "read_sensor_net",
    "read_sensor": "read_sensor_net",
    "sensor": "read_sensor_net",
    "get_state": "read_sensor_net",
    "sensor_net": "read_sensor_net",
    "discover_devices": "discover_devices",
    "discover": "discover_devices",
    "list_devices": "discover_devices",
    "devices": "discover_devices",
}


class TheSteward(BaseAgent):
    """Specialist Agent: Home Automation and IoT Domain.

    Domain: Home Assistant REST API interactions, direct MQTT messaging, and network sensor reads.
    """

    name: str = "TheSteward"
    domain: str = (
        "Home Assistant REST API interactions, direct MQTT messaging, and network sensor reads."
    )
    description: str = (
        "Home automation and IoT agent responsible for Home Assistant REST API integrations, "
        "direct MQTT message publishing, network sensor reading, and device discovery."
    )

    system_requirements: List[str] = ["requests", "paho-mqtt"]
    consumed_artifacts: List[str] = [
        "target_device",
        "entity_id",
        "command",
        "topic",
        "payload",
    ]
    produced_artifacts: List[str] = [
        "device_state",
        "mqtt_status",
        "discovery_report",
    ]

    SUPPORTED_ACTIONS: Dict[str, List[str]] = {
        "control_appliance": [
            "control_appliance",
            "control",
            "turn_on",
            "turn_off",
            "toggle",
            "appliance",
        ],
        "publish_mqtt": [
            "publish_mqtt",
            "publish",
            "mqtt",
            "mqtt_publish",
        ],
        "read_sensor_net": [
            "read_sensor_net",
            "read_sensor",
            "sensor",
            "get_state",
            "sensor_net",
        ],
        "discover_devices": [
            "discover_devices",
            "discover",
            "list_devices",
            "devices",
        ],
    }

    supported_actions = SUPPORTED_ACTIONS

    def __init__(self, librarian: Optional[SkillLibrarian] = None) -> None:
        """Initializes TheSteward agent with Home Assistant and MQTT connection configuration."""
        super().__init__(librarian=librarian)
        ensure_ecosystem_directories()
        self.ha_url = os.getenv(
            "HOMEASSISTANT_URL", "http://homeassistant.local:8123"
        ).rstrip("/")
        self.ha_token = os.getenv("HOMEASSISTANT_TOKEN", "")
        self.mqtt_host = os.getenv("MQTT_BROKER_HOST", "localhost")
        self.mqtt_port = int(os.getenv("MQTT_BROKER_PORT", "1883"))
        self.mqtt_user = os.getenv("MQTT_USER", None)
        self.mqtt_pass = os.getenv("MQTT_PASSWORD", None)
        logger.info(
            f"[{self.name}] Initialized for IoT & Home Assistant automation."
        )

    def health_check(self) -> Dict[str, Any]:
        """Runtime health check verifying Home Assistant and MQTT configuration status."""
        base_health = super().health_check()
        try:
            ha_configured = bool(self.ha_token)
            mqtt_configured = bool(self.mqtt_host)
            healthy = (ha_configured or mqtt_configured) and base_health.get(
                "healthy", True
            )

            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": healthy,
                "status": (
                    "Operational"
                    if healthy
                    else "Degraded: Home Assistant token missing and MQTT host unconfigured"
                ),
                "missing_dependencies": base_health.get(
                    "missing_dependencies", []
                ),
                "details": {
                    "ha_url": self.ha_url,
                    "ha_configured": ha_configured,
                    "mqtt_host": self.mqtt_host,
                    "mqtt_port": self.mqtt_port,
                    "mqtt_authenticated": bool(self.mqtt_user),
                    **base_health.get("details", {}),
                },
                "dynamic_skills_available": base_health.get(
                    "dynamic_skills_available", []
                ),
                "native_actions_supported": base_health.get(
                    "native_actions_supported", []
                ),
            }
        except Exception as e:
            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": False,
                "status": f"Degraded: Exception during health check ({e})",
                "missing_dependencies": base_health.get(
                    "missing_dependencies", []
                ),
                "details": {},
            }

    async def execute(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """Primary routing switch for The Steward's capabilities using DynamicActionPayload schemas."""
        raw_params = parameters if parameters is not None else (params or {})
        payload_dict = dict(raw_params)
        action_clean = str(action or "").lower().strip()

        # Dynamic Probing Intercept
        if action_clean in ["probe", "ping", "health", "get_capabilities", "status"]:
            probe_type = payload_dict.get("probe_type", "full")
            return self.probe(probe_type=probe_type)

        normalized_action = ACTION_MAP.get(action_clean, action_clean)

        if normalized_action not in VALID_STEWARD_ACTIONS:
            logger.error(
                f"[{self.name}] Does not recognize action: {normalized_action}"
            )
            raise ValueError(
                f"Unknown action '{normalized_action}' for {self.name}"
            )

        self.report_progress(
            message=f"Executing steward action: '{normalized_action}'",
            phase="START",
            action=normalized_action,
            progress_pct=0.0,
        )
        self.report_trace(
            event_type="EXECUTION_START",
            action=normalized_action,
            details={"parameters": payload_dict, "raw_prompt": raw_prompt},
        )
        self.report_action(action=normalized_action, details=payload_dict)

        try:
            if "call_action" in payload_dict and "params" in payload_dict:
                payload = DynamicActionPayload.model_validate(payload_dict)
            else:
                extracted_params = {
                    k: v for k, v in payload_dict.items()
                    if k not in ["call_action", "action", "thought", "memory_candidate"]
                }
                payload = DynamicActionPayload(
                    call_action=normalized_action,
                    thought=payload_dict.get("thought", ""),
                    params=extracted_params,
                )
        except Exception as e:
            logger.warning(
                f"[{self.name}] Payload validation warning ({e}). Executing fallback construction..."
            )
            fallback_action = (
                normalized_action
                if normalized_action in VALID_STEWARD_ACTIONS
                else "read_sensor_net"
            )
            payload = DynamicActionPayload(
                call_action=fallback_action,
                thought=payload_dict.get("thought", ""),
                params=payload_dict,
            )

        target_action = payload.call_action or normalized_action
        action_params = payload.params if isinstance(payload.params, dict) else raw_params

        logger.info(
            f"[{self.name}] Executing action '{target_action}' with params: {action_params}"
        )

        try:
            if target_action == "control_appliance":
                target_device = (
                    action_params.get("target_device")
                    or action_params.get("entity_id")
                    or action_params.get("device")
                )
                command = (
                    action_params.get("command")
                    or action_params.get("service")
                )
                data_payload = (
                    action_params.get("payload")
                    or action_params.get("data")
                )
                result = self.control_appliance(
                    target_device=target_device,
                    command=command,
                    payload=data_payload,
                )

            elif target_action == "publish_mqtt":
                topic = (
                    action_params.get("topic")
                    or action_params.get("mqtt_topic")
                )
                data_payload = (
                    action_params.get("payload")
                    or action_params.get("data")
                    or action_params.get("message")
                )
                result = self.publish_mqtt(topic=topic, payload=data_payload)

            elif target_action == "read_sensor_net":
                target_device = (
                    action_params.get("target_device")
                    or action_params.get("entity_id")
                    or action_params.get("device")
                )
                result = self.read_sensor_net(target_device=target_device)

            elif target_action == "discover_devices":
                result = self.discover_devices()

            else:
                logger.error(
                    f"[{self.name}] Does not recognize action: {target_action}"
                )
                raise ValueError(
                    f"Unknown action '{target_action}' for {self.name}"
                )

            self.report_progress(
                message=f"Successfully completed action: '{normalized_action}'",
                phase="COMPLETE",
                action=normalized_action,
                progress_pct=100.0,
            )
            self.report_trace(
                event_type="EXECUTION_COMPLETE",
                action=normalized_action,
                details={"status": "success"},
            )
            return result

        except Exception as e:
            logger.exception(
                f"[{self.name}] Execution error during '{normalized_action}': {e}"
            )
            self.report_progress(
                message=f"Failed to execute action: '{normalized_action}'",
                phase="ERROR",
                action=normalized_action,
                progress_pct=100.0,
            )
            self.report_trace(
                event_type="EXECUTION_ERROR",
                action=normalized_action,
                details={"error": str(e)},
            )
            raise

    # =========================================================================
    # BACKWARD COMPATIBILITY HELPERS & DELEGATES
    # =========================================================================

    def control_appliance(
        self,
        target_device: Optional[str],
        command: Optional[str],
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Controls a Home Assistant entity."""
        return control_appliance(
            self.ha_url, self.ha_token, target_device, command, payload
        )

    def publish_mqtt(
        self,
        topic: Optional[str],
        payload: Optional[Union[Dict[str, Any], str]] = None,
    ) -> Dict[str, Any]:
        """Publishes a raw payload to an MQTT topic."""
        return publish_mqtt(
            self.mqtt_host,
            self.mqtt_port,
            self.mqtt_user,
            self.mqtt_pass,
            topic,
            payload,
        )

    def read_sensor_net(
        self, target_device: Optional[str] = None
    ) -> Dict[str, Any]:
        """Queries state and attributes for a target entity or lists all entities."""
        return read_sensor_net(self.ha_url, self.ha_token, target_device)

    def discover_devices(self) -> Dict[str, Any]:
        """Fetches all active states and entities registered in Home Assistant."""
        return discover_devices(self.ha_url, self.ha_token)