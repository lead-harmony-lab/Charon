#!/usr/bin/env python3
"""tests/agents/spark/test_utils.py — Unit tests for spark/utils.py."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from charon.agents.spark.utils import find_pcb_file, resolve_project_dir


# --- Tests: resolve_project_dir ---

def test_resolve_project_dir_returns_none_when_empty():
    """Returns None when no payload, params, or prompt text are provided."""
    assert resolve_project_dir(params={}, raw_prompt="") is None
    assert resolve_project_dir(params={}, raw_prompt="   ") is None


def test_resolve_project_dir_payload_precedence():
    """Tests payload attribute precedence (directory -> name -> path)."""
    with patch("charon.agents.spark.utils.resolve_project_path") as mock_resolve:
        mock_resolve.side_effect = lambda x: Path(x)

        # 1. payload.project_directory takes priority
        payload = SimpleNamespace(
            project_directory="/path/dir",
            project_name="/path/name",
            project_path="/path/path",
        )
        assert resolve_project_dir(params={}, payload=payload) == Path("/path/dir")

        # 2. payload.project_name if project_directory is missing
        payload = SimpleNamespace(
            project_directory=None,
            project_name="/path/name",
            project_path="/path/path",
        )
        assert resolve_project_dir(params={}, payload=payload) == Path("/path/name")

        # 3. payload.project_path if directory and name are missing
        payload = SimpleNamespace(
            project_directory=None,
            project_name=None,
            project_path="/path/path",
        )
        assert resolve_project_dir(params={}, payload=payload) == Path("/path/path")


def test_resolve_project_dir_params_precedence():
    """Tests params dict key precedence (directory -> path -> name -> base_path)."""
    with patch("charon.agents.spark.utils.resolve_project_path") as mock_resolve:
        mock_resolve.side_effect = lambda x: Path(x)

        # project_directory
        assert resolve_project_dir(params={"project_directory": "p_dir"}) == Path("p_dir")

        # project_path
        assert resolve_project_dir(params={"project_path": "p_path"}) == Path("p_path")

        # project_name
        assert resolve_project_dir(params={"project_name": "p_name"}) == Path("p_name")

        # base_path
        assert resolve_project_dir(params={"base_path": "p_base"}) == Path("p_base")


def test_resolve_project_dir_token_splitting_from_raw_prompt():
    """Hits lines 31-32: Splitting raw_prompt to extract the last token when params is empty."""
    with patch("charon.agents.spark.utils.resolve_project_path") as mock_resolve:
        mock_resolve.side_effect = lambda x: Path(x)

        result = resolve_project_dir(params={}, raw_prompt="open project_alpha")
        assert result == Path("project_alpha")
        mock_resolve.assert_called_with("project_alpha")


# --- Tests: find_pcb_file ---

def test_find_pcb_file_explicit_file_exists(tmp_path):
    """Returns resolved path when explicit pcb_file exists."""
    pcb_file = tmp_path / "board.kicad_pcb"
    pcb_file.touch()

    # Via payload.pcb_file
    payload = SimpleNamespace(pcb_file=str(pcb_file))
    assert find_pcb_file(params={}, payload=payload) == pcb_file.resolve()

    # Via params['pcb_file']
    assert find_pcb_file(params={"pcb_file": str(pcb_file)}) == pcb_file.resolve()

    # Via params['file']
    assert find_pcb_file(params={"file": str(pcb_file)}) == pcb_file.resolve()


def test_find_pcb_file_explicit_file_missing_falls_through(tmp_path):
    """Hits branch 50->53: Explicit pcb_file does not exist on disk, falling through to search."""
    missing_pcb = tmp_path / "nonexistent.kicad_pcb"

    with patch("charon.agents.spark.utils.resolve_project_dir") as mock_resolve:
        mock_resolve.return_value = None
        assert find_pcb_file(params={"pcb_file": str(missing_pcb)}) is None
        mock_resolve.assert_called_once()


def test_find_pcb_file_search_directories(tmp_path):
    """Hits lines 55-64: Searches cad/, hardware/, and root project dirs for .kicad_pcb."""
    # 1. Subdirectory: target_path/cad
    cad_dir = tmp_path / "cad"
    cad_dir.mkdir()
    cad_pcb = cad_dir / "design.kicad_pcb"
    cad_pcb.touch()

    with patch("charon.agents.spark.utils.resolve_project_dir", return_value=tmp_path):
        assert find_pcb_file(params={}) == cad_pcb.resolve()

    cad_pcb.unlink()

    # 2. Subdirectory: target_path/hardware
    hw_dir = tmp_path / "hardware"
    hw_dir.mkdir()
    hw_pcb = hw_dir / "board.kicad_pcb"
    hw_pcb.touch()

    with patch("charon.agents.spark.utils.resolve_project_dir", return_value=tmp_path):
        assert find_pcb_file(params={}) == hw_pcb.resolve()

    hw_pcb.unlink()

    # 3. Root directory: target_path
    root_pcb = tmp_path / "main.kicad_pcb"
    root_pcb.touch()

    with patch("charon.agents.spark.utils.resolve_project_dir", return_value=tmp_path):
        assert find_pcb_file(params={}) == root_pcb.resolve()


def test_find_pcb_file_non_directory_or_no_matching_files(tmp_path):
    """Hits non-directory sdir checks and missing .kicad_pcb returns."""
    # Create 'cad' as a file rather than a directory to test is_dir() returning False
    cad_file = tmp_path / "cad"
    cad_file.touch()

    with patch("charon.agents.spark.utils.resolve_project_dir", return_value=tmp_path):
        assert find_pcb_file(params={}) is None


def test_find_pcb_file_target_path_none_or_missing(tmp_path):
    """Returns None when target directory is None or does not exist."""
    missing_dir = tmp_path / "nonexistent"

    with patch("charon.agents.spark.utils.resolve_project_dir", return_value=missing_dir):
        assert find_pcb_file(params={}) is None

    with patch("charon.agents.spark.utils.resolve_project_dir", return_value=None):
        assert find_pcb_file(params={}) is None
