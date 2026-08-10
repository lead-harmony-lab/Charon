# Agent Card: `The_Steward` (Home Automation & IoT Control)

**File Path:** `docs/architecture/agents/steward.md`

**Target Module:** `charon/agents/steward/agent.py`

**Agent Class:** `TheSteward` (Alias: `StewardAgent`)

**Agent Enum:** `AgentEnum.The_Steward`

**Safety Intercept Level:** 🟢 **Low Intercept** (Read-only sensor queries and device state discovery) / 🟡 **Medium Intercept** (Toggling home appliances, executing service calls, and publishing telemetry to MQTT brokers)

**System Specification:** Charon Agent Spec v2.2 / System Architecture v4.5

---

## 1. Operational Overview

**`The_Steward`** serves as Charon’s physical environment bridge, managing Home Automation networks, IoT sensor networks, and physical state controls. It provides direct REST API integration with Home Assistant and raw TCP/IP messaging capabilities over MQTT.

Through `The_Steward`, Charon can monitor physical laboratory/workspace environments (e.g., temperature, power consumption, relay status), trigger automated equipment power states, and publish raw telemetry payloads to remote microcontrollers or edge brokers.

---

## 2. Action Capabilities & Method Mapping

| Action Alias (`StewardPayload`) | Executing Method | Target Parameters | Description |
| --- | --- | --- | --- |
| `control_appliance`, `control`, `set_state`, `toggle` | `control_appliance` | `target_device`, `entity_id`, `device`, `command`, `service`, `payload`, `data` | Calls Home Assistant domain services (`turn_on`, `turn_off`, `toggle`) for a specific target entity (`domain.entity_id`). |
| `publish_mqtt`, `mqtt`, `publish` | `publish_mqtt` | `topic`, `mqtt_topic`, `payload`, `data`, `message` | Transmits raw text or serialized JSON payloads to an MQTT broker channel via `paho-mqtt`. |
| `read_sensor_net`, `read_sensor`, `get_state`, `read` | `read_sensor_net` | `target_device`, `entity_id`, `device` | Reads state telemetry and attributes for a specified entity. Calls `discover_devices()` if target is omitted. |
| `discover_devices`, `discover`, `list_devices` | `discover_devices` | None | Queries Home Assistant for all active entities and returns a summary list with states and friendly names. |

---

## 3. Subsystem Logic & Architectural Features

### Environment Configuration & Initialization

`The_Steward` automatically configures API endpoints and broker options via environment variables:

* **Home Assistant REST URL:** `HOMEASSISTANT_URL` (Defaults to `[http://homeassistant.local:8123](http://homeassistant.local:8123)`).
* **Long-Lived Access Token:** `HOMEASSISTANT_TOKEN` (Required for HTTP Authorization headers).
* **MQTT Connection Settings:** `MQTT_BROKER_HOST` (default: `localhost`), `MQTT_BROKER_PORT` (default: `1883`), `MQTT_USER`, and `MQTT_PASSWORD`.

### Home Assistant REST Interface (`_make_ha_request`)

All REST API interactions use standard library `urllib.request` with strict 10-second connection timeouts and Bearer Token authentication headers:

