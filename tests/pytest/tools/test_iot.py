import importlib
import json
import sys
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from charon.tools import iot


# ==========================================
# Module Load & Import Coverage Tests
# ==========================================

def test_iot_mqtt_import_error_fallback():
    """Simulate missing paho-mqtt during module load to hit lines 13-14."""
    with patch.dict(sys.modules, {"paho": None, "paho.mqtt": None, "paho.mqtt.publish": None}):
        importlib.reload(iot)
        assert iot.MQTT_AVAILABLE is False

    # Restore module state for subsequent tests
    importlib.reload(iot)
    assert iot.MQTT_AVAILABLE is True


# ==========================================
# Tests for make_ha_request
# ==========================================

def test_ha_request_missing_token():
    """Test that missing the HA token returns an immediate error."""
    result = iot.make_ha_request(
        ha_url="http://homeassistant.local:8123",
        ha_token="",
        endpoint="/api/states"
    )
    assert result["status"] == "error"
    assert "HOMEASSISTANT_TOKEN environment variable is not configured" in result["message"]


@patch("charon.tools.iot.urllib.request.urlopen")
def test_ha_request_success_with_payload(mock_urlopen):
    """Test a successful HA request that includes a JSON payload."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b'{"entity_id": "light.living_room", "state": "on"}'

    mock_urlopen.return_value.__enter__.return_value = mock_response

    payload = {"entity_id": "light.living_room"}
    result = iot.make_ha_request(
        ha_url="http://ha.local:8123",
        ha_token="secret_token",
        endpoint="/api/services/light/turn_on",
        method="POST",
        payload=payload
    )

    assert result["status"] == "success"
    assert result["code"] == 200
    assert result["data"]["state"] == "on"

    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]

    assert req.full_url == "http://ha.local:8123/api/services/light/turn_on"
    assert req.method == "POST"
    assert req.data == b'{"entity_id": "light.living_room"}'
    assert req.get_header("Authorization") == "Bearer secret_token"
    assert req.get_header("Content-type") == "application/json"


@patch("charon.tools.iot.urllib.request.urlopen")
def test_ha_request_success_empty_body(mock_urlopen):
    """Test successful HA request returning an empty response body."""
    mock_response = MagicMock()
    mock_response.status = 204
    mock_response.read.return_value = b""

    mock_urlopen.return_value.__enter__.return_value = mock_response

    result = iot.make_ha_request("http://ha.local:8123", "token", "/api/events")

    assert result["status"] == "success"
    assert result["code"] == 204
    assert result["data"] == {}


@patch("charon.tools.iot.urllib.request.urlopen")
def test_ha_request_http_error(mock_urlopen):
    """Test handling of HTTP errors with response body (e.g. 401 Unauthorized)."""
    mock_fp = MagicMock()
    mock_fp.read.return_value = b"401: Unauthorized"

    error = urllib.error.HTTPError(
        url="http://ha.local:8123/api/",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=mock_fp
    )
    mock_urlopen.side_effect = error

    result = iot.make_ha_request("http://ha.local:8123", "bad_token", "/api/")

    assert result["status"] == "error"
    assert result["code"] == 401
    assert "401: Unauthorized" in result["message"]


@patch("charon.tools.iot.urllib.request.urlopen")
def test_ha_request_http_error_no_fp(mock_urlopen):
    """Test handling of HTTP errors when e.fp is None."""
    error = urllib.error.HTTPError(
        url="http://ha.local:8123/api/",
        code=500,
        msg="Internal Error",
        hdrs={},
        fp=None
    )
    mock_urlopen.side_effect = error

    result = iot.make_ha_request("http://ha.local:8123", "token", "/api/")

    assert result["status"] == "error"
    assert result["code"] == 500


@patch("charon.tools.iot.urllib.request.urlopen")
def test_ha_request_generic_error(mock_urlopen):
    """Test handling of generic connection exceptions."""
    mock_urlopen.side_effect = Exception("Connection refused")

    result = iot.make_ha_request("http://ha.local:8123", "token", "/api/")

    assert result["status"] == "error"
    assert "Connection refused" in result["message"]
    assert "code" not in result


# ==========================================
# Tests for publish_mqtt_message
# ==========================================

def test_mqtt_missing_topic():
    """Test that passing an empty topic returns an error."""
    with patch("charon.tools.iot.MQTT_AVAILABLE", True):
        result = iot.publish_mqtt_message(topic="")

        assert result["status"] == "error"
        assert "MQTT topic is required" in result["message"]


def test_mqtt_not_installed():
    """Test behavior when paho-mqtt is missing."""
    with patch("charon.tools.iot.MQTT_AVAILABLE", False):
        result = iot.publish_mqtt_message(topic="home/test")

        assert result["status"] == "error"
        assert "paho-mqtt library is not installed" in result["message"]


@patch("charon.tools.iot.mqtt_publish.single")
def test_mqtt_publish_success_dict(mock_single):
    """Test successful publish with a dictionary payload (auto-converted to JSON)."""
    with patch("charon.tools.iot.MQTT_AVAILABLE", True):
        payload = {"brightness": 255, "color": "red"}
        result = iot.publish_mqtt_message(
            topic="home/lights/1/set",
            payload=payload
        )

        assert result["status"] == "success"
        assert result["action"] == "publish_mqtt"
        assert result["topic"] == "home/lights/1/set"

        mock_single.assert_called_once_with(
            topic="home/lights/1/set",
            payload='{"brightness": 255, "color": "red"}',
            hostname="localhost",
            port=1883,
            auth=None
        )


@patch("charon.tools.iot.mqtt_publish.single")
def test_mqtt_publish_success_string_auth(mock_single):
    """Test publishing a raw string with authentication and custom port."""
    with patch("charon.tools.iot.MQTT_AVAILABLE", True):
        result = iot.publish_mqtt_message(
            topic="home/sensor/temp",
            payload="23.5",
            host="mqtt.local",
            port=1884,
            user="admin",
            password="secretpassword"
        )

        assert result["status"] == "success"

        mock_single.assert_called_once_with(
            topic="home/sensor/temp",
            payload="23.5",
            hostname="mqtt.local",
            port=1884,
            auth={"username": "admin", "password": "secretpassword"}
        )


@patch("charon.tools.iot.mqtt_publish.single")
def test_mqtt_publish_exception(mock_single):
    """Test handling of paho-mqtt exceptions."""
    mock_single.side_effect = Exception("Connection to broker failed")

    with patch("charon.tools.iot.MQTT_AVAILABLE", True):
        result = iot.publish_mqtt_message(topic="test/topic")

        assert result["status"] == "error"
        assert "Connection to broker failed" in result["message"]
