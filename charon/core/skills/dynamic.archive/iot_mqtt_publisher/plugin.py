"""Plugin entrypoint module for iot_mqtt_publisher."""

import logging
import os
from typing import Any, Dict

from charon.agents.steward.mqtt import publish_mqtt as steward_publish_mqtt

logger = logging.getLogger("CHAROND.Skills.IotMqttPublisher")


def handle_publish_mqtt(params: Dict[str, Any]) -> Dict[str, Any]:
    """Publishes a raw or structured payload to an MQTT topic."""
    topic = params.get("topic") or params.get("mqtt_topic")
    if not topic:
        return {"status": "error", "message": "Missing required 'topic' parameter."}

    payload = (
        params.get("payload")
        or params.get("data")
        or params.get("message")
        or ""
    )

    host = params.get("host") or os.getenv("MQTT_BROKER_HOST", "localhost")
    port = int(params.get("port") or os.getenv("MQTT_BROKER_PORT", "1883"))
    user = params.get("user") or os.getenv("MQTT_USER")
    password = params.get("password") or os.getenv("MQTT_PASSWORD")

    logger.info(f"Publishing MQTT message to topic '{topic}' via broker {host}:{port}")
    res = steward_publish_mqtt(
        host=host,
        port=port,
        user=user,
        password=password,
        topic=topic,
        payload=payload,
    )
    return {"status": "success", "result": res}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router for iot_mqtt_publisher."""
    if action_name == "publish_mqtt":
        return handle_publish_mqtt(params)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'iot_mqtt_publisher'."
    )