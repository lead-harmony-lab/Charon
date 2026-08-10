import pytest
from pydantic import ValidationError

from charon.intent.payloads.knowledge import (
    ArchivistPayload,
    EngineerPayload,
    PlannerPayload,
    ScoutPayload,
)


class TestArchivistPayload:
    """Tests for ArchivistPayload defaults, model validators, and fallbacks."""

    def test_archivist_defaults(self) -> None:
        """Verify default values when instantiating empty."""
        payload = ArchivistPayload()
        assert payload.action == "store_record"
        assert payload.category == "system_rule"
        assert payload.requires_approval is False
        assert payload.query is None
        assert payload.fact is None

    def test_sanitize_non_dict_input(self) -> None:
        """Verify sanitize_llm_payload handles non-dict input cleanly."""
        result = ArchivistPayload.sanitize_llm_payload("string_input")
        assert result == "string_input"

    def test_sanitize_properties_wrapper_unwrapping(self) -> None:
        """Verify nested 'properties' dictionary is unwrapped."""
        raw_input = {
            "properties": {
                "action": "search_ledger",
                "query": "find user preferences",
            }
        }
        payload = ArchivistPayload.model_validate(raw_input)
        assert payload.action == "search_ledger"
        assert payload.query == "find user preferences"

    def test_fact_fallback_from_query(self) -> None:
        """Verify fact is populated from query when action is store_record and fact is missing."""
        payload = ArchivistPayload.model_validate(
            {"action": "store_record", "query": "User prefers dark mode"}
        )
        assert payload.fact == "User prefers dark mode"

    def test_fact_fallback_from_prompt(self) -> None:
        """Verify fact is populated from prompt when action is record_rule and fact is missing."""
        payload = ArchivistPayload.model_validate(
            {"action": "record_rule", "prompt": "Always format code with black"}
        )
        assert payload.fact == "Always format code with black"

    def test_fact_fallback_from_target_concept(self) -> None:
        """Verify fact is populated from target_concept when action is store_record and fact is missing."""
        payload = ArchivistPayload.model_validate(
            {"action": "store_record", "target_concept": "Key-Value Concept"}
        )
        assert payload.fact == "Key-Value Concept"

    def test_fact_fallback_when_action_is_omitted(self) -> None:
        """Verify fact fallback triggers when action is omitted from input dict."""
        payload = ArchivistPayload.model_validate({"query": "Implicit fact"})
        assert payload.action == "store_record"
        assert payload.fact == "Implicit fact"

    def test_fact_not_overwritten_if_already_present(self) -> None:
        """Verify existing fact is preserved even if fallback fields exist."""
        payload = ArchivistPayload.model_validate(
            {
                "action": "store_record",
                "fact": "Explicit Fact",
                "query": "Fallback Query",
            }
        )
        assert payload.fact == "Explicit Fact"

    def test_non_store_action_does_not_populate_fact(self) -> None:
        """Verify non-storing actions (e.g. search_ledger) do not set fact from query."""
        payload = ArchivistPayload.model_validate(
            {"action": "search_ledger", "query": "lookup data"}
        )
        assert payload.fact is None
        assert payload.query == "lookup data"

    def test_invalid_action_raises_validation_error(self) -> None:
        """Verify unsupported action raises ValidationError."""
        with pytest.raises(ValidationError):
            ArchivistPayload(action="invalid_archivist_action")  # type: ignore


class TestPlannerPayload:
    """Tests for PlannerPayload fields and constraints."""

    def test_planner_defaults(self) -> None:
        """Verify default field values."""
        payload = PlannerPayload()
        assert payload.action == "decompose_task"
        assert payload.requires_approval is False
        assert payload.objective is None

    def test_planner_custom_values(self) -> None:
        """Verify custom payload initialization."""
        payload = PlannerPayload(
            action="analyze_error_logs",
            objective="Debug build pipeline",
            prompt="Investigate traceback",
            log_content="Traceback (most recent call last): ...",
            target_directory="/workspace/project",
        )
        assert payload.action == "analyze_error_logs"
        assert payload.objective == "Debug build pipeline"
        assert payload.log_content is not None and payload.log_content.startswith("Traceback")
        assert payload.target_directory == "/workspace/project"

    def test_planner_requires_approval_must_be_false(self) -> None:
        """Verify requires_approval strictly rejects True."""
        with pytest.raises(ValidationError):
            PlannerPayload(requires_approval=True)  # type: ignore

    def test_planner_invalid_action(self) -> None:
        """Verify invalid action raises ValidationError."""
        with pytest.raises(ValidationError):
            PlannerPayload(action="unknown_plan_action")  # type: ignore


class TestEngineerPayload:
    """Tests for EngineerPayload fields and constraints."""

    def test_engineer_defaults(self) -> None:
        """Verify default field values."""
        payload = EngineerPayload()
        assert payload.action == "execute_sandbox_code"
        assert payload.language == "python"
        assert payload.requires_approval is False

    def test_engineer_custom_values(self) -> None:
        """Verify custom payload assignment."""
        payload = EngineerPayload(
            action="run_existing_script",
            problem="Fix NullPointer in parser",
            prompt="Run script and collect stdout",
            script_path="/scripts/run.py",
            language="python",
            target_dir="/tmp/run",
            requires_approval=True,
        )
        assert payload.action == "run_existing_script"
        assert payload.script_path == "/scripts/run.py"
        assert payload.requires_approval is True

    def test_engineer_invalid_action(self) -> None:
        """Verify invalid action raises ValidationError."""
        with pytest.raises(ValidationError):
            EngineerPayload(action="invalid_engineering_action")  # type: ignore


class TestScoutPayload:
    """Tests for ScoutPayload fields and constraints."""

    def test_scout_defaults(self) -> None:
        """Verify default field values."""
        payload = ScoutPayload()
        assert payload.action == "search_web"
        assert payload.max_results == 5
        assert payload.requires_approval is False

    def test_scout_custom_values(self) -> None:
        """Verify custom payload assignment."""
        payload = ScoutPayload(
            action="scrape_page_content",
            query="Python async patterns",
            url="https://docs.python.org/3/",
            max_results=10,
        )
        assert payload.action == "scrape_page_content"
        assert payload.url == "https://docs.python.org/3/"
        assert payload.max_results == 10

    def test_scout_requires_approval_must_be_false(self) -> None:
        """Verify requires_approval strictly rejects True."""
        with pytest.raises(ValidationError):
            ScoutPayload(requires_approval=True)  # type: ignore

    def test_scout_invalid_action(self) -> None:
        """Verify invalid action raises ValidationError."""
        with pytest.raises(ValidationError):
            ScoutPayload(action="execute_hack")  # type: ignore
