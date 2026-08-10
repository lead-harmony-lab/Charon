"""tests/agents/test_steward.py — Pytest suite for The Steward (Home Automation & IoT Agent)."""

import os
from unittest.mock import MagicMock, patch
import pytest

from charon.agents.steward import TheSteward, StewardAgent, execute_steward_task
from charon.intent.payloads.hardware import StewardPayload


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Sets mock environment variables for Home Assistant and MQTT testing."""
    monkeypatch.setenv("HOMEASSISTANT_URL", "http://ha.test:8123")
    monkeypatch.setenv("HOMEASSISTANT_TOKEN", "mock_jwt_token_123")
    monkeypatch.setenv("MQTT_BROKER_HOST", "mqtt.test.local")
    monkeypatch.setenv("MQTT_BROKER_PORT", "1883")
    monkeypatch.setenv("MQTT_USER", "test_user")
    monkeypatch.setenv("MQTT_PASSWORD", "test_pass")


@pytest.fixture
def steward(mock_env_vars):
    """Provides a fresh instance of TheSteward initialized with test environment variables."""
    return TheSteward()


class TestStewardInitialization:
    """Tests proper initialization and configuration parsing of TheSteward."""

    def test_init_defaults(self, mock_env_vars):
        agent = TheSteward()
        assert agent.ha_url == "http://ha.test:8123"
        assert agent.ha_token == "mock_jwt_token_123"
        assert agent.mqtt_host == "mqtt.test.local"
        assert agent.mqtt_port == 1883
        assert agent.mqtt_user == "test_user"
        assert agent.mqtt_pass == "test_pass"

    def test_backward_compatibility_alias(self):
        assert StewardAgent is TheSteward


class TestControlAppliance:
    """Tests the Home Assistant entity control action."""

    def test_invalid_target_device_format(self, steward):
        res = steward.control_appliance(
            target_device="invalid_entity_id", command="turn_on"
        )
        assert res["status"] == "error"
        assert "Invalid target_device format" in res["message"]

    @patch("charon.agents.steward.home_assistant.make_ha_request")
    def test_control_appliance_success(self, mock_make_request, steward):
        mock_make_request.return_value = {"status": "success", "code": 200, "data": []}

        res = steward.control_appliance(
            target_device="switch.workbench_power",
            command="turn_on",
            payload={"brightness": 100},
        )

        mock_make_request.assert_called_once_with(
            "http://ha.test:8123",
            "mock_jwt_token_123",
            "/api/services/switch/turn_on",
            method="POST",
            payload={"entity_id": "switch.workbench_power", "brightness": 100},
        )
        assert res["action"] == "control_appliance"
        assert res["target_device"] == "switch.workbench_power"
        assert res["command"] == "turn_on"
        assert res["response"]["status"] == "success"


class TestPublishMQTT:
    """Tests direct MQTT message publication."""

    @patch("charon.agents.steward.mqtt.publish_mqtt_message")
    def test_publish_mqtt_success(self, mock_publish, steward):
        mock_publish.return_value = {
            "action": "publish_mqtt",
            "topic": "lab/sensors/temp",
            "payload": {"deg_c": 22.5},
            "status": "success",
        }

        res = steward.publish_mqtt(
            topic="lab/sensors/temp", payload={"deg_c": 22.5}
        )

        mock_publish.assert_called_once_with(
            topic="lab/sensors/temp",
            payload={"deg_c": 22.5},
            host="mqtt.test.local",
            port=1883,
            user="test_user",
            password="test_pass",
        )
        assert res["status"] == "success"
        assert res["topic"] == "lab/sensors/temp"


class TestReadSensorNetAndDiscover:
    """Tests Home Assistant state inspection and device discovery."""

    @patch("charon.agents.steward.home_assistant.make_ha_request")
    def test_read_specific_sensor(self, mock_make_request, steward):
        mock_make_request.return_value = {
            "status": "success",
            "code": 200,
            "data": {"entity_id": "sensor.temp", "state": "21.4"},
        }

        res = steward.read_sensor_net(target_device="sensor.temp")

        mock_make_request.assert_called_once_with(
            "http://ha.test:8123",
            "mock_jwt_token_123",
            "/api/states/sensor.temp",
            method="GET",
        )
        assert res["action"] == "read_sensor_net"
        assert res["target_device"] == "sensor.temp"

    @patch("charon.agents.steward.home_assistant.make_ha_request")
    def test_discover_devices(self, mock_make_request, steward):
        mock_make_request.return_value = {
            "status": "success",
            "code": 200,
            "data": [
                {
                    "entity_id": "light.desk_lamp",
                    "state": "on",
                    "attributes": {"friendly_name": "Desk Lamp"},
                },
                {
                    "entity_id": "sensor.humidity",
                    "state": "45%",
                    "attributes": {"friendly_name": "Lab Humidity"},
                },
            ],
        }

        res = steward.discover_devices()

        mock_make_request.assert_called_once_with(
            "http://ha.test:8123",
            "mock_jwt_token_123",
            "/api/states",
            method="GET",
        )
        assert res["action"] == "discover_devices"
        assert res["count"] == 2
        assert res["devices"][0]["entity_id"] == "light.desk_lamp"


class TestExecuteRouterAndAliases:
    """Tests action resolution, aliases, and payload normalization in execute()."""

    @pytest.mark.parametrize(
        "action_alias", ["control_appliance", "control", "set_state", "toggle"]
    )
    @patch.object(TheSteward, "control_appliance")
    def test_control_appliance_action_aliases(
        self, mock_control, action_alias, steward
    ):
        mock_control.return_value = {"status": "mocked"}
        params = {"target_device": "switch.test", "command": "turn_on"}

        res = steward.execute(action=action_alias, params=params)

        mock_control.assert_called_once_with(
            target_device="switch.test", command="turn_on", payload=None
        )
        assert res == {"status": "mocked"}

    @patch.object(TheSteward, "read_sensor_net")
    def test_unknown_action_fallback_to_read_sensor_net(self, mock_read, steward):
        """Tests that unsupported actions fall back gracefully to read_sensor_net."""
        mock_read.return_value = {"action": "read_sensor_net", "status": "fallback"}

        res = steward.execute(action="unsupported_action")

        mock_read.assert_called_once_with(target_device=None)
        assert res == {"action": "read_sensor_net", "status": "fallback"}


class TestTaskDispatcher:
    """Tests the top-level execute_steward_task entry point."""

    @patch.object(TheSteward, "execute")
    def test_execute_task_with_dict(self, mock_execute):
        mock_execute.return_value = {"status": "ok"}
        payload = {"action": "discover_devices"}

        res = execute_steward_task(payload)

        mock_execute.assert_called_once_with(
            action="discover_devices", params=payload
        )
        assert res == {"status": "ok"}

    @patch.object(TheSteward, "execute")
    def test_execute_task_with_pydantic_payload(self, mock_execute):
        mock_execute.return_value = {"status": "ok"}
        payload = StewardPayload(
            action="control_appliance",
            target_device="light.ceiling",
            command="turn_off",
        )

        res = execute_steward_task(payload)

        mock_execute.assert_called_once_with(
            action="control_appliance",
            params={
                "target_device": "light.ceiling",
                "command": "turn_off",
                "topic": None,
                "payload": {},
            },
        )
        assert res == {"status": "ok"}

    def test_execute_task_invalid_payload(self):
        res = execute_steward_task(payload="invalid_str_payload")
        assert res["status"] == "error"
        assert "Invalid payload format" in res["message"]
