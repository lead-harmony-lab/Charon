"""
tests/test_intent.py — Unit tests for charon.intent package schemas, validators, and base models.
"""

import pytest
from pydantic import ValidationError

from charon.intent import (
    AgentEnum,
    ArchitectPayload,
    ArchivistPayload,
    BaseAgentPayload,
    CleanerPayload,
    EngineerPayload,
    GeneralistPayload,
    IntentExtraction,
    MachinistPayload,
    MemoryCandidate,
    OverseerPayload,
    PlannerPayload,
    QuartermasterPayload,
    RoutingPayload,
    ScoutPayload,
    SparkPayload,
    StewardPayload,
    StrictBaseModel,
)


class TestBaseModelsAndRouting:
    """Tests for core base classes, enums, and routing payloads."""

    def test_strict_base_model_ignores_extra_fields(self):
        """Ensure local LLM outputs with unexpected extra fields don't raise validation errors."""

        class DummyModel(StrictBaseModel):
            name: str

        model = DummyModel.model_validate({"name": "charon", "unexpected_llm_hallucination": 123})
        assert model.name == "charon"
        assert not hasattr(model, "unexpected_llm_hallucination")

    def test_memory_candidate_defaults(self):
        candidate = MemoryCandidate(fact="Prefer dark mode in CAD UI")
        assert candidate.fact == "Prefer dark mode in CAD UI"
        assert candidate.is_persistent is True
        assert candidate.confidence == 1.0

    def test_base_agent_payload_schema_cleanup(self):
        """Verify get_clean_schema removes $defs for local LLM (Ollama) compatibility."""
        schema = BaseAgentPayload.get_clean_schema()
        assert "$defs" not in schema
        assert "properties" in schema

    def test_routing_payload_enum_validation(self):
        payload = RoutingPayload(agent=AgentEnum.SPARK)
        assert payload.agent == "The_Spark"
        assert payload.agent == AgentEnum.SPARK

        with pytest.raises(ValidationError):
            RoutingPayload(agent="NonExistentAgent")  # type: ignore

    def test_intent_extraction_defaults(self):
        extraction = IntentExtraction(
            agent=AgentEnum.GENERALIST,
            action="answer_query",
            parameters={"query": "Hello Charon"},
        )
        assert extraction.agent == AgentEnum.GENERALIST
        assert extraction.action == "answer_query"
        assert extraction.confidence == 1.0
        assert extraction.requires_approval is False


class TestHardwarePayloads:
    """Tests for hardware, fabrication, and logistics agent payloads."""

    def test_quartermaster_sanitizer_nested_properties(self):
        """Verify Quartermaster pre-validator unwraps nested 'properties' dict from LLMs."""
        raw_llm_output = {
            "properties": {
                "action": "fetch_datasheet",
                "query": "ESP32-S3-WROOM-1",
            }
        }
        payload = QuartermasterPayload.model_validate(raw_llm_output)
        assert payload.action == "fetch_datasheet"
        assert payload.part_number == "ESP32-S3-WROOM-1"
        assert payload.mpn == "ESP32-S3-WROOM-1"

    def test_quartermaster_mpn_alias_fallback(self):
        """Ensure mpn, part_number, and query alias correctly."""
        payload = QuartermasterPayload(mpn="STM32F401")
        assert payload.part_number == "STM32F401"
        assert payload.mpn == "STM32F401"

    def test_machinist_payload_defaults(self):
        payload = MachinistPayload(source_file="/workspace/bracket.step")
        assert payload.action == "export_cad_to_stl"
        assert payload.source_file == "/workspace/bracket.step"
        assert payload.requires_approval is False

    def test_spark_payload_defaults(self):
        payload = SparkPayload(action="compile_firmware", project_directory="/projects/drone")
        assert payload.action == "compile_firmware"
        assert payload.environment is None

    def test_steward_payload_defaults(self):
        payload = StewardPayload(target_device="lab_light", command="turn_on")
        assert payload.action == "control_appliance"
        assert payload.protocol == "http"


class TestKnowledgePayloads:
    """Tests for RAG, memory, planning, coding, and web agent payloads."""

    def test_archivist_sanitizer_fact_fallback(self):
        """Verify Archivist validator populates 'fact' from 'query' when storing records."""
        raw_llm_output = {
            "action": "store_record",
            "query": "Always set nozzle temp to 215C for PETG",
        }
        payload = ArchivistPayload.model_validate(raw_llm_output)
        assert payload.action == "store_record"
        assert payload.fact == "Always set nozzle temp to 215C for PETG"

    def test_archivist_sanitizer_nested_properties(self):
        raw_llm_output = {
            "properties": {
                "action": "record_rule",
                "prompt": "Never run CAD scripts directly on host",
            }
        }
        payload = ArchivistPayload.model_validate(raw_llm_output)
        assert payload.action == "record_rule"
        assert payload.fact == "Never run CAD scripts directly on host"

    def test_planner_payload(self):
        payload = PlannerPayload(objective="Design a 3-axis CNC router")
        assert payload.action == "decompose_task"
        assert payload.objective == "Design a 3-axis CNC router"
        assert payload.requires_approval is False

    def test_engineer_payload(self):
        payload = EngineerPayload(
            action="execute_sandbox_code",
            prompt="print('hello')",
            requires_approval=True,
        )
        assert payload.action == "execute_sandbox_code"
        assert payload.language == "python"
        assert payload.requires_approval is True

    def test_scout_payload(self):
        payload = ScoutPayload(query="Latest KiCad 8 release notes")
        assert payload.action == "search_web"
        assert payload.max_results == 5
        assert payload.requires_approval is False


class TestSystemPayloads:
    """Tests for system operations, cleanup, and orchestration payloads."""

    def test_generalist_payload(self):
        payload = GeneralistPayload(prompt="What is the speed of light?")
        assert payload.action == "answer_query"
        assert payload.prompt == "What is the speed of light?"

    def test_cleaner_payload(self):
        payload = CleanerPayload(
            action="initialize_project_workspace",
            project_name="AegisBot",
        )
        assert payload.action == "initialize_project_workspace"
        assert payload.project_name == "AegisBot"
        assert payload.initialize_git is True

    def test_architect_payload(self):
        payload = ArchitectPayload(action="rescind_order", target_task_id="task_12345")
        assert payload.action == "rescind_order"
        assert payload.target_task_id == "task_12345"

    def test_overseer_payload(self):
        payload = OverseerPayload(action="optimize_databases")
        assert payload.action == "optimize_databases"
        assert payload.prune_days == 7
        assert payload.requires_approval is False
