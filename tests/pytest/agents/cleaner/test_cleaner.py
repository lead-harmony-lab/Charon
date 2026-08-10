"""tests/agents/test_cleaner.py — Unit tests for TheCleaner agent package."""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from charon.agents import TheCleaner, get_agent_class
from charon.agents.cleaner.agent import ACTION_MAP
from charon.agents.cleaner.cad import CADManager
from charon.agents.cleaner.logs import LogManager
from charon.agents.cleaner.workspaces import WorkspaceManager


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_projects_dir(tmp_path: Path) -> Path:
    """Provides a temporary directory acting as the PROJECTS_DIR."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    return projects_dir


@pytest.fixture
def mock_logs_dir(tmp_path: Path) -> Path:
    """Provides a temporary directory acting as the LOGS_DIR."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


@pytest.fixture
def cleaner_agent(mock_projects_dir: Path) -> TheCleaner:
    """Instantiates TheCleaner configured with the temporary projects directory."""
    return TheCleaner(default_projects_dir=mock_projects_dir)


# =============================================================================
# LAZY IMPORT & REGISTRY TESTS
# =============================================================================

def test_lazy_loading_registry():
    """Verifies that TheCleaner can be lazy-loaded from charon.agents."""
    cls = get_agent_class("cleaner")
    assert cls is TheCleaner

    cls_by_name = get_agent_class("TheCleaner")
    assert cls_by_name is TheCleaner


# =============================================================================
# WORKSPACE MANAGEMENT TESTS
# =============================================================================

def test_initialize_workspace(cleaner_agent: TheCleaner, mock_projects_dir: Path):
    """Tests project workspace scaffolding with default subdirectories."""
    project_name = "test_rover"

    with patch("charon.agents.cleaner.workspaces.git_init") as mock_git_init:
        mock_git_init.return_value = (True, "Initialized successfully")

        response = cleaner_agent.execute(
            action="init",
            parameters={"project_name": project_name},
        )

        assert "Workspace Initialization Completed" in response
        project_path = mock_projects_dir / project_name
        assert project_path.exists()

        # Check default subdirectories & .gitkeep files
        for sub in ["cad", "firmware", "docs", "src", "bom"]:
            subdir_path = project_path / sub
            assert subdir_path.exists()
            assert (subdir_path / ".gitkeep").exists()

        mock_git_init.assert_called_once_with(project_path)


def test_list_workspaces(cleaner_agent: TheCleaner, mock_projects_dir: Path):
    """Tests workspace listing and exclusion filters."""
    # Create valid projects
    (mock_projects_dir / "alpha_drone").mkdir()
    (mock_projects_dir / "beta_arm").mkdir()

    # Create excluded directories
    (mock_projects_dir / ".git").mkdir()
    (mock_projects_dir / "node_modules").mkdir()
    (mock_projects_dir / "archive").mkdir()

    response = cleaner_agent.execute(
        action="list_workspaces",
        parameters={},
    )

    assert "alpha_drone" in response
    assert "beta_arm" in response
    assert "node_modules" not in response
    assert "archive" not in response


def test_delete_workspace_authorization_flow(cleaner_agent: TheCleaner, mock_projects_dir: Path):
    """Tests two-step deletion authorization safety logic."""
    project_path = mock_projects_dir / "doomed_project"
    project_path.mkdir()
    (project_path / "dummy.txt").write_text("content")

    # Step 1: Unconfirmed request -> Authorization prompt returned
    unconfirmed_response = cleaner_agent.execute(
        action="delete",
        parameters={"project_name": "doomed_project"},
        raw_prompt="Delete doomed_project",
    )

    assert "[AUTHORIZATION REQUIRED]" in unconfirmed_response
    assert project_path.exists()  # Ensure folder was NOT deleted yet

    # Step 2: Confirmed request via prompt keyword "proceed"
    confirmed_response = cleaner_agent.execute(
        action="delete",
        parameters={"project_name": "doomed_project"},
        raw_prompt="proceed with deleting doomed_project",
    )

    assert "Workspace Purge" in confirmed_response
    assert "SUCCESS" in confirmed_response
    assert not project_path.exists()  # Ensure folder IS deleted now


def test_delete_workspace_safety_bounds(cleaner_agent: TheCleaner, mock_projects_dir: Path):
    """Verifies that safety protocols prevent out-of-bounds or root directory deletion."""
    # Attempt deleting root default_projects_dir
    response = cleaner_agent.execute(
        action="delete",
        parameters={"project_name": "..", "confirmed": True},
    )

    assert "Safety protocol prevents deletion" in response or "Missing" in response
    assert mock_projects_dir.exists()


# =============================================================================
# CAD SWEEPER TESTS
# =============================================================================

def test_sweep_cad_iterations(cleaner_agent: TheCleaner, mock_projects_dir: Path):
    """Tests finding and archiving older CAD iterations."""
    project_dir = mock_projects_dir / "arm_project"
    cad_dir = project_dir / "cad"
    cad_dir.mkdir(parents=True)

    # Create iterative files
    v1 = cad_dir / "bracket_v1.step"
    v2 = cad_dir / "bracket_v2.step"
    v3 = cad_dir / "bracket_v3.step"
    v1.write_text("v1")
    v2.write_text("v2")
    v3.write_text("v3")

    response = cleaner_agent.execute(
        action="sweep_cad",
        parameters={"project_name": "arm_project"},
    )

    assert "CAD Iteration Sweep" in response
    assert "bracket_v1.step -> archive/bracket_v1.step" in response
    assert "bracket_v2.step -> archive/bracket_v2.step" in response

    archive_dir = cad_dir / "archive"
    assert (archive_dir / "bracket_v1.step").exists()
    assert (archive_dir / "bracket_v2.step").exists()
    assert v3.exists()  # Latest version remains in main CAD directory


# =============================================================================
# LOG PRUNING TESTS
# =============================================================================

def test_prune_logs(cleaner_agent: TheCleaner, mock_logs_dir: Path):
    """Tests log pruning based on file age and protection of active log streams."""
    active_log = mock_logs_dir / "charond.log"
    old_rotated_log = mock_logs_dir / "charond_2025-01-01.log"
    recent_rotated_log = mock_logs_dir / "charond_2026-07-27.log"

    active_log.write_text("active")
    old_rotated_log.write_text("old")
    recent_rotated_log.write_text("recent")

    # Set file modification times (old log = 10 days old)
    now = time.time()
    ten_days_ago = now - (10 * 86400)
    import os
    os.utime(old_rotated_log, (ten_days_ago, ten_days_ago))

    response = cleaner_agent.execute(
        action="prune_logs",
        parameters={"logs_dir": str(mock_logs_dir), "max_age_days": 7, "keep_active": True},
    )

    assert "System Log Pruning" in response
    assert "charond_2025-01-01.log" in response

    assert not old_rotated_log.exists()  # Pruned
    assert active_log.exists()          # Retained (active stream)
    assert recent_rotated_log.exists()  # Retained (within window)


# =============================================================================
# ROUTING & ACTION MAP TESTS
# =============================================================================

def test_action_aliases(cleaner_agent: TheCleaner):
    """Verifies that action map aliases resolve correctly."""
    assert ACTION_MAP["init"] == "initialize_project_workspace"
    assert ACTION_MAP["scaffold"] == "initialize_project_workspace"
    assert ACTION_MAP["commit"] == "commit_workspace"
    assert ACTION_MAP["sweep"] == "sweep_cad_iterations"
    assert ACTION_MAP["prune"] == "prune_logs"
    assert ACTION_MAP["purge"] == "delete_project_workspace"


def test_invalid_action_raises_exception(cleaner_agent: TheCleaner):
    """Verifies ValueError when an unmapped/invalid action is executed."""
    with pytest.raises(ValueError, match="Unknown action 'non_existent_action'"):
        cleaner_agent.execute(action="non_existent_action", parameters={})
