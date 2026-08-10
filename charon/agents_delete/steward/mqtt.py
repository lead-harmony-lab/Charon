"""
charon/agents/steward/mqtt.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: MQTT messaging operations for The Steward.
"""

from typing import Any, Dict, Optional, Union
from charon.tools.iot import publish_mqtt_message


def publish_mqtt(
    host: str,
    port: int,
    user: Optional[str],
    password: Optional[str],
    topic: Optional[str],
    payload: Optional[Union[Dict[str, Any], str]] = None,
) -> Dict[str, Any]:
    """Publishes a raw payload to an MQTT topic."""
    return publish_mqtt_message(
        topic=topic or "",
        payload=payload,
        host=host,
        port=port,
        user=user,
        password=password,
    )