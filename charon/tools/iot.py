"""
charon/tools/iot.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Stateless tools for Home Assistant REST and MQTT messaging.
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Union

try:
    import paho.mqtt.publish as mqtt_publish

    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

logger = logging.getLogger("Charon.Tools.IoT")


def make_ha_request(
    ha_url: str,
    ha_token: str,
    endpoint: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    """Executes HTTP REST requests against a Home Assistant instance."""
    if not ha_token:
        return {
            "status": "error",
            "message": "HOMEASSISTANT_TOKEN environment variable is not configured.",
        }

    url = f"{ha_url.rstrip('/')}{endpoint}"
    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    }

    data_bytes = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(
        url, data=data_bytes, headers=headers, method=method
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_body = response.read().decode("utf-8")
            return {
                "status": "success",
                "code": response.status,
                "data": json.loads(res_body) if res_body else {},
            }
    except urllib.error.HTTPError as e:
        err_text = e.read().decode("utf-8") if e.fp else str(e)
        logger.error(f"[IOT TOOL] Home Assistant REST error [{e.code}]: {err_text}")
        return {"status": "error", "code": e.code, "message": err_text}
    except Exception as e:
        logger.error(f"[IOT TOOL] Failed to connect to Home Assistant at {url}: {e}")
        return {"status": "error", "message": str(e)}


def publish_mqtt_message(
    topic: str,
    payload: Optional[Union[Dict[str, Any], str]] = None,
    host: str = "localhost",
    port: int = 1883,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    """Publishes a raw payload to an MQTT topic."""
    if not MQTT_AVAILABLE:
        return {
            "status": "error",
            "message": "paho-mqtt library is not installed in the environment.",
        }

    if not topic:
        return {
            "status": "error",
            "message": "MQTT topic is required for publish_mqtt.",
        }

    msg_payload = (
        json.dumps(payload) if isinstance(payload, dict) else str(payload or "")
    )

    auth = None
    if user and password:
        auth = {"username": user, "password": password}

    try:
        logger.info(f"[IOT TOOL] Publishing MQTT message to topic: {topic}")
        mqtt_publish.single(
            topic=topic,
            payload=msg_payload,
            hostname=host,
            port=port,
            auth=auth,
        )
        return {
            "action": "publish_mqtt",
            "topic": topic,
            "payload": payload,
            "status": "success",
        }
    except Exception as e:
        logger.error(f"[IOT TOOL] MQTT publish failed: {e}")
        return {"status": "error", "topic": topic, "message": str(e)}
