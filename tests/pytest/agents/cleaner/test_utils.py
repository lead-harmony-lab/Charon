"""Tests for Cleaner utility functions."""

from pathlib import Path

import pytest

from charon.agents.cleaner.utils import get_param, resolve_target_workspace
from charon.intent import CleanerPayload


class TestCleanerUtils:
    """Test suite for cleaner module utilities."""

    def test_get_param_from_payload_attribute(self):
        """Tests retrieving a parameter directly from a payload object attribute."""
        payload = CleanerPayload(action="initialize_project_workspace", project_name="my_project")
        value = get_param(payload, {}, "project_name")
        assert value == "my_project"

    def test_get_param_payload_none_fallback_to_params(self):
        """Tests falling back to params dictionary when payload attribute is None or missing."""
        payload = CleanerPayload(action="initialize_project_workspace", project_name=None)
        params = {"project_name": "fallback_project"}
        value = get_param(payload, params, "project_name")
        assert value == "fallback_project"

    def test_get_param_default_value(self):
        """Tests returning the default value when parameter is not present in payload or params."""
        payload = CleanerPayload(action="initialize_project_workspace")
        value = get_param(payload, {}, "nonexistent_key", default="default_val")
        assert value == "default_val"

    def test_resolve_target_workspace_base_path_with_project_subfolder(self, tmp_path: Path):
        """Tests resolving workspace when base_path contains project_name as a subdirectory."""
        base_dir = tmp_path / "workspaces"
        proj_dir = base_dir / "my_robot"
        proj_dir.mkdir(parents=True)

        target, error = resolve_target_workspace(
            base_path_str=str(base_dir), project_name="my_robot"
        )
        assert error is None
        assert target == proj_dir.resolve()

    def test_resolve_target_workspace_base_path_without_project_subfolder(self, tmp_path: Path):
        """Tests resolving workspace when base_path directly points to the workspace."""
        base_dir = tmp_path / "my_robot"
        base_dir.mkdir(parents=True)

        target, error = resolve_target_workspace(
            base_path_str=str(base_dir), project_name="my_robot"
        )
        assert error is None
        assert target == base_dir.resolve()

    def test_resolve_target_workspace_project_name_only(self, tmp_path: Path):
        """Tests resolving workspace using project_name relative to projects_dir."""
        proj_dir = tmp_path / "drone"
        proj_dir.mkdir(parents=True)

        target, error = resolve_target_workspace(
            project_name="drone", default_dir=tmp_path
        )
        assert error is None
        assert target == proj_dir.resolve()

    def test_resolve_target_workspace_no_inputs_defaults_to_cwd(self):
        """Tests falling back to current working directory when no path parameters are provided."""
        target, error = resolve_target_workspace()
        assert error is None
        assert target == Path.cwd().resolve()
