"""
tests/conftest.py — Pytest hooks, CLI options, and global fixtures.
"""

from pathlib import Path
import pytest

from charon.core.version import get_git_revision, get_version_string
from tests.artifact_manager import ArtifactVersionManager


def pytest_addoption(parser: pytest.Parser) -> None:
    """Registers custom Charon flags with pytest CLI."""
    parser.addoption(
        "--fail-on-dirty",
        action="store_true",
        default=False,
        help="Abort test session if Git working tree contains uncommitted changes.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Evaluates session guards prior to test execution."""
    if config.getoption("--fail-on-dirty"):
        git_info = get_git_revision()
        if git_info["is_dirty"]:
            pytest.exit(
                "\n❌ ERROR: Aborting test run because Git workspace has uncommitted changes "
                "and --fail-on-dirty flag is enabled.\n"
                "Commit or stash your changes before re-running tests.",
                returncode=1,
            )


def pytest_report_header(config: pytest.Config) -> str:
    """Displays Charon target version and Git commit status in pytest header."""
    return f"Charon System Target: {get_version_string()}"


@pytest.fixture(scope="session")
def artifact_manager() -> ArtifactVersionManager:
    """Session-scoped artifact manager ensuring clean isolated directories per test suite run."""
    manager = ArtifactVersionManager()
    yield manager


@pytest.fixture
def test_workspace(request: pytest.FixtureRequest, artifact_manager: ArtifactVersionManager) -> Path:
    """Provides a versioned, isolated directory for an individual test function."""
    test_name = request.node.name
    return artifact_manager.get_test_run_path(test_name)
