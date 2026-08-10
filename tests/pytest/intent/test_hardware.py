import pytest
from pydantic import ValidationError

from charon.intent.payloads.hardware import (
    MachinistPayload,
    QuartermasterPayload,
    SparkPayload,
    StewardPayload,
)


class TestQuartermasterPayload:
    """Tests for QuartermasterPayload field defaults, model validators, and fallbacks."""

    def test_quartermaster_defaults(self) -> None:
        """Verify default values when instantiating with minimal required data."""
        payload = QuartermasterPayload()
        assert payload.action == "fetch_datasheet"
        assert payload.category == "General"
        assert payload.quantity == 0
        assert payload.storage_bin == "Unsorted/Inbox"
        assert payload.requires_approval is False
        assert payload.part_number is None
        assert payload.mpn is None

    def test_sanitize_non_dict_input(self) -> None:
        """Verify model_validator returns non-dict input untouched without crashing."""
        # Directly invoking class method validator with non-dict input
        result = QuartermasterPayload.sanitize_quartermaster_payload("raw_string_data")
        assert result == "raw_string_data"

    def test_sanitize_properties_wrapper_unwrapping(self) -> None:
        """Verify model_validator unwraps raw schema data wrapped in a 'properties' key."""
        raw_input = {
            "properties": {
                "action": "check_inventory",
                "part_number": "ESP32-S3-WROOM-1",
            }
        }
        payload = QuartermasterPayload.model_validate(raw_input)
        assert payload.action == "check_inventory"
        assert payload.part_number == "ESP32-S3-WROOM-1"
        assert payload.mpn == "ESP32-S3-WROOM-1"

    def test_mpn_fallback_from_query(self) -> None:
        """Verify query fills both part_number and mpn if missing."""
        payload = QuartermasterPayload.model_validate({"query": "ATMEGA328P"})
        assert payload.query == "ATMEGA328P"
        assert payload.part_number == "ATMEGA328P"
        assert payload.mpn == "ATMEGA328P"

    def test_mpn_fallback_from_part_number(self) -> None:
        """Verify part_number fills mpn if mpn is missing."""
        payload = QuartermasterPayload.model_validate({"part_number": "STM32F401"})
        assert payload.part_number == "STM32F401"
        assert payload.mpn == "STM32F401"

    def test_part_number_fallback_from_mpn(self) -> None:
        """Verify mpn fills part_number if part_number is missing."""
        payload = QuartermasterPayload.model_validate({"mpn": "NE555P"})
        assert payload.part_number == "NE555P"
        assert payload.mpn == "NE555P"

    def test_no_overwrite_when_both_part_number_and_mpn_provided(self) -> None:
        """Verify part_number and mpn are retained when both are explicitly provided."""
        payload = QuartermasterPayload.model_validate(
            {"part_number": "PART-123", "mpn": "MPN-456"}
        )
        assert payload.part_number == "PART-123"
        assert payload.mpn == "MPN-456"

    def test_invalid_action_raises_validation_error(self) -> None:
        """Verify error is raised when an unsupported action literal is supplied."""
        with pytest.raises(ValidationError):
            QuartermasterPayload(action="invalid_logistics_action")  # type: ignore


class TestMachinistPayload:
    """Tests for MachinistPayload fields and constraints."""

    def test_machinist_defaults(self) -> None:
        """Verify default field values."""
        payload = MachinistPayload()
        assert payload.action == "export_cad_to_stl"
        assert payload.requires_approval is False
        assert payload.source_file is None

    def test_machinist_custom_values(self) -> None:
        """Verify custom payload assignment."""
        payload = MachinistPayload(
            action="generate_gcode",
            source_file="enclosure.step",
            stl_file="enclosure.stl",
            profile="0.2mm_Standard",
            gcode_file="enclosure.gcode",
            requires_approval=True,
        )
        assert payload.action == "generate_gcode"
        assert payload.source_file == "enclosure.step"
        assert payload.profile == "0.2mm_Standard"
        assert payload.requires_approval is True

    def test_machinist_invalid_action(self) -> None:
        """Verify invalid action raises ValidationError."""
        with pytest.raises(ValidationError):
            MachinistPayload(action="laser_cut")  # type: ignore


class TestSparkPayload:
    """Tests for SparkPayload fields and constraints."""

    def test_spark_defaults(self) -> None:
        """Verify default field values."""
        payload = SparkPayload()
        assert payload.action == "compile_firmware"
        assert payload.requires_approval is False

    def test_spark_custom_values(self) -> None:
        """Verify custom payload assignment."""
        payload = SparkPayload(
            action="flash_hardware",
            project_directory="/workspace/firmware",
            environment="esp32s3_dev",
            port="/dev/ttyUSB0",
            pcb_file="mainboard.kicad_pcb",
            requires_approval=True,
        )
        assert payload.action == "flash_hardware"
        assert payload.environment == "esp32s3_dev"
        assert payload.port == "/dev/ttyUSB0"
        assert payload.requires_approval is True

    def test_spark_invalid_action(self) -> None:
        """Verify invalid action raises ValidationError."""
        with pytest.raises(ValidationError):
            SparkPayload(action="auto_route")  # type: ignore


class TestStewardPayload:
    """Tests for StewardPayload fields and constraints."""

    def test_steward_defaults(self) -> None:
        """Verify default field values."""
        payload = StewardPayload()
        assert payload.action == "control_appliance"
        assert payload.protocol == "http"
        assert payload.payload == {}
        assert payload.requires_approval is False

    def test_steward_custom_values(self) -> None:
        """Verify custom payload assignment."""
        payload = StewardPayload(
            action="publish_mqtt",
            target_device="relay_01",
            command="toggle",
            protocol="mqtt",
            topic="home/workshop/power",
            payload={"state": "ON"},
            requires_approval=True,
        )
        assert payload.action == "publish_mqtt"
        assert payload.protocol == "mqtt"
        assert payload.topic == "home/workshop/power"
        assert payload.payload == {"state": "ON"}

    def test_steward_invalid_protocol(self) -> None:
        """Verify invalid protocol literal raises ValidationError."""
        with pytest.raises(ValidationError):
            StewardPayload(protocol="grpc")  # type: ignore
