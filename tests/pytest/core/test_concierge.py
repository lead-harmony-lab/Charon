import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from charon.core.concierge import (
    ConciergeService,
    SafeDict,
    _git_missing,
    _has_test_directory,
)


class TestSafeDict:
    def test_missing_key_retains_placeholder(self):
        d = SafeDict({"existing": "value"})
        assert d["existing"] == "value"
        assert d["missing"] == "{missing}"

    def test_format_map_with_safe_dict(self):
        template = "Hello {name}, your code is {status}!"
        result = template.format_map(SafeDict({"name": "Charon"}))
        assert result == "Hello Charon, your code is {status}!"


class TestConditionHelpers:
    def test_git_missing(self, tmp_path):
        assert _git_missing(None) is True
        assert _git_missing(tmp_path / "non_existent") is True

        # Existing directory without .git
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()
        assert _git_missing(project_dir) is True

        # Existing directory with .git
        (project_dir / ".git").mkdir()
        assert _git_missing(project_dir) is False

    def test_has_test_directory(self, tmp_path):
        assert _has_test_directory(None) is False
        assert _has_test_directory(tmp_path / "non_existent") is False

        project_dir = tmp_path / "my_project"
        project_dir.mkdir()
        assert _has_test_directory(project_dir) is False

        # Create 'tests' directory
        tests_dir = project_dir / "tests"
        tests_dir.mkdir()
        assert _has_test_directory(project_dir) is True


class TestConciergeService:
    @pytest.fixture
    def service(self):
        return ConciergeService()

    def test_extract_context_defaults(self, service):
        ctx = service._extract_context({})
        assert ctx["project_name"] == "active project"
        assert ctx["stl_file"] == "geometry.stl"
        assert ctx["gcode_file"] == "part.gcode"
        assert ctx["port"] == "auto"

    def test_extract_context_custom_params(self, service):
        params = {
            "project_name": "/home/user/Projects/Charon",
            "source_file": "/tmp/gear.stl",
            "gcode_file": "/tmp/gear.gcode",
            "upload_port": "/dev/ttyUSB0",
        }
        ctx = service._extract_context(params)
        assert ctx["project_name"] == "Charon"
        assert ctx["stl_file"] == "gear.stl"
        assert ctx["gcode_file"] == "gear.gcode"
        assert ctx["port"] == "/dev/ttyUSB0"

    def test_evaluate_next_step_returns_first_suggestion(self, service, tmp_path):
        project_dir = tmp_path / "test_repo"
        project_dir.mkdir()

        params = {"project_directory": str(project_dir), "project_name": "test_repo"}
        next_step = service.evaluate_next_step("create_project", params)

        assert next_step is not None
        assert next_step["id"] == "git_init"
        assert "Initialize Git repository for test_repo" in next_step["suggested_prompt"]

    def test_get_all_suggestions_filters_by_condition(self, service, tmp_path):
        project_dir = tmp_path / "git_repo"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()

        params = {"project_directory": str(project_dir), "project_name": "git_repo"}
        suggestions = service.get_all_suggestions("create_project", params)

        # 'git_init' condition (_git_missing) evaluates to False, leaving only 'github_remote'
        assert len(suggestions) == 1
        assert suggestions[0]["id"] == "github_remote"

    def test_unknown_action_returns_empty(self, service):
        assert service.get_all_suggestions("non_existent_action", {}) == []
        assert service.evaluate_next_step("non_existent_action", {}) is None

    def test_resolve_target_path_missing_directory_param(self, service):
        """Covers branch 156->161 when project_directory is missing from params."""
        result = service._resolve_target_path({})
        assert result is None

    def test_resolve_target_path_exception_handling(self, service, caplog):
        """Covers exception handling inside _resolve_target_path."""
        with patch(
            "charon.core.concierge.resolve_project_path",
            side_effect=ValueError("Invalid path"),
        ):
            with caplog.at_level("DEBUG"):
                result = service._resolve_target_path(
                    {"project_directory": "invalid/path/!!!"}
                )

                assert result is None
                assert "Could not resolve project path" in caplog.text

    def test_get_all_suggestions_without_condition_fn(self, service):
        """Covers branch 184->194 where a suggestion step has no condition callback."""
        mock_actions = {
            "test_action_no_cond": [
                {
                    "id": "always_valid_step",
                    # No condition key provided
                    "prompt_template": "Execute {project_name}",
                    "phrase": "Shall I execute {project_name}?",
                }
            ]
        }

        with patch.dict("charon.core.concierge.NEXT_BEST_ACTIONS", mock_actions):
            suggestions = service.get_all_suggestions(
                "test_action_no_cond", {"project_name": "TestProj"}
            )
            assert len(suggestions) == 1
            assert suggestions[0]["id"] == "always_valid_step"

    def test_condition_evaluation_exception_handling(self, service, caplog):
        """Covers error handling when candidate conditions raise runtime errors."""

        def faulty_condition(path, params):
            raise RuntimeError("Simulated condition failure")

        mock_actions = {
            "test_action": [
                {
                    "id": "faulty_step",
                    "condition": faulty_condition,
                    "prompt_template": "Do {project_name}",
                    "phrase": "Shall I do {project_name}?",
                },
                {
                    "id": "valid_step",
                    "condition": lambda p, params: True,
                    "prompt_template": "Run {project_name}",
                    "phrase": "Shall I run {project_name}?",
                },
            ]
        }

        with patch.dict("charon.core.concierge.NEXT_BEST_ACTIONS", mock_actions):
            with caplog.at_level("WARNING"):
                suggestions = service.get_all_suggestions(
                    "test_action", {"project_name": "TestProj"}
                )

                assert len(suggestions) == 1
                assert suggestions[0]["id"] == "valid_step"
                assert "Condition check failed for suggestion 'faulty_step'" in caplog.text


def test_import_fallback_coverage(monkeypatch):
    """Covers lines 8-16 by simulating an ImportError on charon.config.paths."""
    monkeypatch.delitem(sys.modules, "charon.core.concierge", raising=False)

    with patch.dict(sys.modules, {"charon.config.paths": None}):
        import charon.core.concierge as concierge_fallback

        rel_path = concierge_fallback.resolve_project_path("sample_project")
        assert rel_path.is_absolute()
        assert rel_path.name == "sample_project"

        abs_target = Path("/tmp/absolute_test_path").resolve()
        assert concierge_fallback.resolve_project_path(str(abs_target)) == abs_target
