"""
Shared pytest fixtures for Charon agent unit and integration tests.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from charon.agents.archivist import TheArchivist
from charon.agents.cleaner import TheCleaner


# =============================================================================
# FILESYSTEM & ENVIRONMENT ISOLATION
# =============================================================================

@pytest.fixture
def mock_env_paths(tmp_path):
    """Provides isolated temporary directories for all Charon system paths.

    Yields a dictionary containing pre-created Path objects for:
    - workspace root
    - projects directory
    - logs directory
    - chroma database directory
    """
    base_dir = tmp_path / "charon_workspace"
    projects_dir = base_dir / "projects"
    logs_dir = base_dir / "logs"
    chroma_dir = base_dir / "chroma_db"

    for d in (base_dir, projects_dir, logs_dir, chroma_dir):
        d.mkdir(parents=True, exist_ok=True)

    yield {
        "root": base_dir,
        "projects": projects_dir,
        "logs": logs_dir,
        "chroma": chroma_dir,
    }


@pytest.fixture
def mock_projects_dir(mock_env_paths, monkeypatch):
    """Provides and monkeypatches the projects directory across cleaner submodules."""
    projects_dir = mock_env_paths["projects"]
    monkeypatch.setattr("charon.config.paths.PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("charon.agents.cleaner.agent.PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("charon.agents.cleaner.workspaces.PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("charon.agents.cleaner.cad.PROJECTS_DIR", projects_dir)
    return projects_dir


@pytest.fixture
def mock_logs_dir(mock_env_paths, monkeypatch):
    """Provides and monkeypatches the logs directory across cleaner submodules."""
    logs_dir = mock_env_paths["logs"]
    monkeypatch.setattr("charon.config.paths.LOGS_DIR", logs_dir)
    monkeypatch.setattr("charon.agents.cleaner.logs.LOGS_DIR", logs_dir)
    return logs_dir


@pytest.fixture(autouse=True)
def patch_ecosystem_directories():
    """Globally mocks `ensure_ecosystem_directories` across all agent modules

    to prevent tests from creating or touching actual system folders (~/.charon).
    Automatically runs for every test in this directory.
    """
    with patch("charon.config.paths.ensure_ecosystem_directories"), patch(
        "charon.agents.cleaner.ensure_ecosystem_directories"
    ), patch("charon.agents.archivist.ensure_ecosystem_directories"):
        yield


# =============================================================================
# AGENT INSTANCE FIXTURES
# =============================================================================

@pytest.fixture
def cleaner_agent(mock_projects_dir):
    """Provides a fresh instance of TheCleaner tied to the mock projects path."""
    return TheCleaner(default_projects_dir=mock_projects_dir)


@pytest.fixture
def archivist_agent(mock_env_paths):
    """Provides a fresh instance of TheArchivist tied to the mock ChromaDB path."""
    return TheArchivist(db_path=mock_env_paths["chroma"])


# =============================================================================
# HELPER & MOCK FIXTURES
# =============================================================================

@pytest.fixture
def mock_git_repo(mock_projects_dir):
    """Creates a mock git project folder inside the mock projects directory."""
    project_dir = mock_projects_dir / "sample_git_project"
    project_dir.mkdir(parents=True, exist_ok=True)
    git_dir = project_dir / ".git"
    git_dir.mkdir(exist_ok=True)

    # Create dummy files
    (project_dir / "main.py").write_text("# sample main script")
    (project_dir / "README.md").write_text("# Sample Project")

    return project_dir


@pytest.fixture
def mock_subprocess_git():
    """Patches subprocess.run to simulate successful Git commands by default."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        yield mock_run
