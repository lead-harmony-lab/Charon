"""Tests for The Cleaner workspace management domain module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from charon.agents.cleaner.workspaces import WorkspaceManager
from charon.intent import CleanerPayload


@pytest.fixture
def manager(tmp_path: Path) -> WorkspaceManager:
    """Fixture providing a WorkspaceManager instance with a temporary base directory."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    return WorkspaceManager(default_projects_dir=projects_dir)


class TestWorkspaceManagerInit:
    """Tests for WorkspaceManager initialization."""

    def test_init(self, tmp_path: Path):
        mgr = WorkspaceManager(default_projects_dir=tmp_path)
        assert mgr.default_projects_dir == tmp_path


class TestListWorkspaces:
    """Tests for listing active project workspaces."""

    def test_list_workspaces_success_filters_exclusions(self, manager: WorkspaceManager):
        base_dir = manager.default_projects_dir

        # Valid projects
        (base_dir / "alpha_bot").mkdir()
        (base_dir / "beta_drone").mkdir()

        # Exclusions and hidden directories
        (base_dir / "Tools").mkdir()
        (base_dir / "Downloads").mkdir()
        (base_dir / "Desktop").mkdir()
        (base_dir / "archive").mkdir()
        (base_dir / "node_modules").mkdir()
        (base_dir / ".git").mkdir()
        (base_dir / ".hidden_project").mkdir()

        # Non-directory file
        (base_dir / "readme.txt").write_text("info")

        result = manager.list_workspaces()

        assert "Current active projects located in" in result
        assert "• alpha_bot" in result
        assert "• beta_drone" in result
        assert "Tools" not in result
        assert "node_modules" not in result
        assert ".hidden_project" not in result

    def test_list_workspaces_custom_base_path(self, manager: WorkspaceManager, tmp_path: Path):
        custom_dir = tmp_path / "custom_workspaces"
        custom_dir.mkdir()
        (custom_dir / "rover").mkdir()

        payload = CleanerPayload(action="list_workspaces", base_path=str(custom_dir))
        result = manager.list_workspaces(payload=payload)

        assert f"Current active projects located in {custom_dir.resolve()}:" in result
        assert "• rover" in result

    def test_list_workspaces_nonexistent_directory(self, manager: WorkspaceManager, tmp_path: Path):
        missing_dir = tmp_path / "nonexistent"
        result = manager.list_workspaces(params={"base_path": str(missing_dir)})
        assert f"The workspace directory {missing_dir.resolve()} does not exist or is inaccessible." in result

    def test_list_workspaces_no_projects_found(self, manager: WorkspaceManager):
        result = manager.list_workspaces()
        assert f"No active projects found in {manager.default_projects_dir}." in result

    def test_list_workspaces_permission_error(self, manager: WorkspaceManager):
        with patch.object(Path, "iterdir", side_effect=PermissionError("Denied")):
            result = manager.list_workspaces()
            assert "Execution aborted: Permission denied reading" in result

    def test_list_workspaces_generic_exception(self, manager: WorkspaceManager):
        with patch.object(Path, "iterdir", side_effect=RuntimeError("Disk failure")):
            result = manager.list_workspaces()
            assert "An unexpected error occurred while scanning for projects: Disk failure" in result


class TestInitializeProjectWorkspace:
    """Tests for project directory scaffolding and Git initialization."""

    def test_initialize_missing_project_name(self, manager: WorkspaceManager):
        result = manager.initialize_project_workspace(params={})
        assert "Execution aborted: Missing 'project_name' parameter for initialization." in result

        result_empty_str = manager.initialize_project_workspace(params={"project_name": "   "})
        assert "Execution aborted: Missing 'project_name' parameter for initialization." in result_empty_str

    def test_initialize_success_default_subdirs_and_git(self, manager: WorkspaceManager):
        payload = CleanerPayload(action="initialize_project_workspace", project_name="drone_v2")

        with patch("charon.agents.cleaner.workspaces.git_init", return_value=(0, "Initialized empty Git repository")):
            result = manager.initialize_project_workspace(payload=payload)

        proj_path = manager.default_projects_dir / "drone_v2"
        assert proj_path.exists()
        for expected_sub in ["cad", "firmware", "docs", "src", "bom"]:
            sub_dir = proj_path / expected_sub
            assert sub_dir.is_dir()
            assert (sub_dir / ".gitkeep").exists()

        assert "[SYSTEM EXECUTION REPORT]" in result
        assert "Workspace Initialization Completed" in result
        assert "Git Repo" in result
        assert "Initialized empty Git repository" in result

    def test_initialize_subdirs_as_list(self, manager: WorkspaceManager):
        payload = CleanerPayload(action="initialize_project_workspace", project_name="arm")
        params = {"subdirectories": ["cad", "pcb"]}

        with patch("charon.agents.cleaner.workspaces.git_init", return_value=(0, "Initialized")):
            result = manager.initialize_project_workspace(payload=payload, params=params)

        proj_path = manager.default_projects_dir / "arm"
        assert (proj_path / "cad").is_dir()
        assert (proj_path / "pcb").is_dir()
        assert not (proj_path / "firmware").exists()
        assert "Subdirectories : cad, pcb" in result

    def test_initialize_subdirs_as_comma_string(self, manager: WorkspaceManager):
        params = {"project_name": "rover", "subdirectories": "cad, docs, telemetry"}

        with patch("charon.agents.cleaner.workspaces.git_init", return_value=(0, "Initialized")):
            result = manager.initialize_project_workspace(params=params)

        proj_path = manager.default_projects_dir / "rover"
        assert (proj_path / "telemetry").is_dir()
        assert "Subdirectories : cad, docs, telemetry" in result

    @pytest.mark.parametrize("git_param", ["true", "1", "yes", True])
    def test_initialize_git_truthy_values(self, manager: WorkspaceManager, git_param):
        params = {"project_name": "test_proj", "initialize_git": git_param}

        with patch("charon.agents.cleaner.workspaces.git_init", return_value=(0, "Git Init OK")) as mock_git:
            result = manager.initialize_project_workspace(params=params)

        assert mock_git.called
        assert "Git Repo" in result
        assert "Git Init OK" in result

    @pytest.mark.parametrize("git_param", ["false", "0", "no", False])
    def test_initialize_git_falsy_values(self, manager: WorkspaceManager, git_param):
        params = {"project_name": "test_proj", "initialize_git": git_param}

        with patch("charon.agents.cleaner.workspaces.git_init") as mock_git:
            result = manager.initialize_project_workspace(params=params)

        assert not mock_git.called
        assert "Git Repo" not in result

    def test_initialize_git_skips_if_git_dir_exists(self, manager: WorkspaceManager):
        proj_path = manager.default_projects_dir / "existing_repo"
        git_dir = proj_path / ".git"
        git_dir.mkdir(parents=True, exist_ok=True)

        params = {"project_name": "existing_repo", "initialize_git": True}

        with patch("charon.agents.cleaner.workspaces.git_init") as mock_git:
            result = manager.initialize_project_workspace(params=params)

        assert not mock_git.called
        assert "Git Repo" not in result

    def test_initialize_custom_base_path(self, manager: WorkspaceManager, tmp_path: Path):
        custom_base = tmp_path / "custom_base"
        params = {"base_path": str(custom_base), "project_name": "custom_proj"}

        with patch("charon.agents.cleaner.workspaces.git_init", return_value=(0, "Init")):
            result = manager.initialize_project_workspace(params=params)

        assert (custom_base / "custom_proj").exists()
        assert "Target Path" in result
        assert str((custom_base / "custom_proj").resolve()) in result

    def test_initialize_permission_error(self, manager: WorkspaceManager):
        with patch.object(Path, "mkdir", side_effect=PermissionError("Write denied")):
            result = manager.initialize_project_workspace(params={"project_name": "test_proj"})
            assert "Execution aborted: Permission denied writing to" in result

    def test_initialize_generic_exception(self, manager: WorkspaceManager):
        with patch.object(Path, "mkdir", side_effect=RuntimeError("Disk full")):
            result = manager.initialize_project_workspace(params={"project_name": "test_proj"})
            assert "An unexpected error occurred during initialization: Disk full" in result


class TestCommitWorkspace:
    """Tests for Workspace Git commit execution."""

    def test_commit_workspace_no_git_or_exe_status(self, manager: WorkspaceManager):
        with patch(
            "charon.agents.cleaner.workspaces.git_commit",
            return_value=(None, "no_git", "Directory is not a Git repository"),
        ):
            result = manager.commit_workspace(params={"project_name": "alpha"})
            assert result == "Directory is not a Git repository"

    def test_commit_workspace_clean_status(self, manager: WorkspaceManager):
        with patch(
            "charon.agents.cleaner.workspaces.git_commit",
            return_value=(None, "clean", "Working tree clean"),
        ):
            result = manager.commit_workspace(params={"project_name": "alpha"})
            assert "Status : Skipped (Workspace is already clean)" in result

    def test_commit_workspace_committed_status(self, manager: WorkspaceManager):
        payload = CleanerPayload(
            action="commit_workspace",
            project_name="alpha",
            commit_message="Initial checkpoint",
        )
        with patch(
            "charon.agents.cleaner.workspaces.git_commit",
            return_value=(None, "committed", "Committed 2 files"),
        ):
            result = manager.commit_workspace(payload=payload)
            assert "Git Commit Completed" in result
            assert "Message : 'Initial checkpoint'" in result

    def test_commit_workspace_failed_status(self, manager: WorkspaceManager):
        with patch(
            "charon.agents.cleaner.workspaces.git_commit",
            return_value=(None, "error", "Fatal error during commit"),
        ):
            result = manager.commit_workspace(params={"project_name": "alpha"})
            assert "Status : Failed" in result
            assert "Reason : Fatal error during commit" in result


class TestDeleteProjectWorkspace:
    """Tests for workspace purging, regex matching, safety checks, and authorization."""

    def test_delete_missing_project_name(self, manager: WorkspaceManager):
        result = manager.delete_project_workspace(params={}, raw_prompt="delete the files")
        assert "Execution aborted: Missing 'project_name' parameter for deletion." in result

    def test_delete_project_name_extracted_from_prompt_regex(self, manager: WorkspaceManager):
        prompt = "Please purge project sensor_node from disk"
        proj_dir = manager.default_projects_dir / "sensor_node"
        proj_dir.mkdir()

        result = manager.delete_project_workspace(raw_prompt=prompt)
        assert "[AUTHORIZATION REQUIRED]" in result
        assert "Project Name" in result
        assert "sensor_node" in result

    def test_delete_safety_base_path_or_outside_bounds(self, manager: WorkspaceManager, tmp_path: Path):
        # Attempt to delete the base directory itself
        params_base = {"project_name": "."}
        result_base = manager.delete_project_workspace(params=params_base)
        assert "Execution aborted: Safety protocol prevents deletion of" in result_base

        # Attempt path traversal out of base_path
        params_out = {"project_name": "../other_dir"}
        result_out = manager.delete_project_workspace(params=params_out)
        assert "Execution aborted: Safety protocol prevents deletion of" in result_out

    def test_delete_nonexistent_directory(self, manager: WorkspaceManager):
        params = {"project_name": "nonexistent_proj"}
        result = manager.delete_project_workspace(params=params)
        assert "Deletion skipped: Workspace directory" in result
        assert "does not exist." in result

    def test_delete_unconfirmed_shows_authorization_warning(self, manager: WorkspaceManager):
        proj_dir = manager.default_projects_dir / "drone"
        proj_dir.mkdir()
        (proj_dir / "file1.txt").write_text("data")
        (proj_dir / "subfolder").mkdir()
        (proj_dir / "subfolder" / "file2.txt").write_text("data2")

        result = manager.delete_project_workspace(params={"project_name": "drone"})

        assert "[AUTHORIZATION REQUIRED]" in result
        assert "Action Requested : Permanent Workspace Deletion" in result
        assert "Target Contents" in result
        assert "2 file(s), 1 folder(s)" in result
        assert "To proceed with execution, re-submit your instruction including the word 'proceed'." in result
        assert proj_dir.exists()

    @pytest.mark.parametrize(
        "payload_attr,param_key,prompt_word",
        [
            ("confirmed", None, None),
            ("authorized", None, None),
            ("gatekeeper_authorized", None, None),
            (None, "confirmed", None),
            (None, "authorized", None),
            (None, "gatekeeper_authorized", None),
            (None, None, "proceed"),
            (None, None, "confirm"),
        ],
    )
    def test_delete_confirmed_variations_success(
        self, manager: WorkspaceManager, payload_attr, param_key, prompt_word
    ):
        proj_dir = manager.default_projects_dir / "target_proj"
        proj_dir.mkdir()
        (proj_dir / "file.txt").write_text("content")

        payload = CleanerPayload(action="delete_project_workspace")
        if payload_attr:
            object.__setattr__(payload, payload_attr, True)

        params = {"project_name": "target_proj"}
        if param_key:
            params[param_key] = True

        raw_prompt = f"Please {prompt_word} deletion" if prompt_word else ""

        result = manager.delete_project_workspace(payload=payload, params=params, raw_prompt=raw_prompt)

        assert "[SYSTEM EXECUTION REPORT]" in result
        assert "Workspace Purge" in result
        assert "SUCCESS" in result
        assert not proj_dir.exists()

    def test_delete_permission_error(self, manager: WorkspaceManager):
        proj_dir = manager.default_projects_dir / "protected_proj"
        proj_dir.mkdir()

        params = {"project_name": "protected_proj", "confirmed": True}

        with patch("shutil.rmtree", side_effect=PermissionError("Access denied")):
            result = manager.delete_project_workspace(params=params)

        assert "[SYSTEM EXECUTION REPORT]" in result
        assert "Status: FAILED" in result
        assert "Reason: Permission denied deleting" in result

    def test_delete_generic_exception(self, manager: WorkspaceManager):
        proj_dir = manager.default_projects_dir / "locked_proj"
        proj_dir.mkdir()

        params = {"project_name": "locked_proj", "confirmed": True}

        with patch("shutil.rmtree", side_effect=RuntimeError("IO Error")):
            result = manager.delete_project_workspace(params=params)

        assert "[SYSTEM EXECUTION REPORT]" in result
        assert "Status: FAILED" in result
        assert "Reason: IO Error" in result
