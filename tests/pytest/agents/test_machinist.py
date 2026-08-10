"""tests/agents/test_machinist.py — Unit tests for The Machinist agent and CAD/CAM tools."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from charon.agents.machinist import TheMachinist
from charon.agents.machinist.cad import inspect_cad_files
from charon.agents.machinist.utils import resolve_file_path
from charon.tools.cad import run_cad_export, run_slicer, transmit_gcode_http


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def agent():
    """Provides a default TheMachinist instance with deterministic defaults."""
    return TheMachinist(
        slicer_cmd="prusa-slicer",
        printer_url="http://192.168.1.50:5000",
    )


# ============================================================================
# 1. Agent Initialization & Routing Tests
# ============================================================================

def test_machinist_initialization(agent):
    """Verifies that agent attributes initialize correctly."""
    assert agent.slicer_cmd == "prusa-slicer"
    assert agent.printer_url == "http://192.168.1.50:5000"


def test_invalid_action_raises_value_error(agent):
    """Ensures an unrecognized action raises a validation or value error."""
    with pytest.raises(ValueError):
        agent.execute(action="invalid_action", parameters={})


# ============================================================================
# 2. CAD Export Domain Tests
# ============================================================================

def test_export_cad_to_stl_success(agent, tmp_path):
    """Tests CAD export execution when source CAD file exists."""
    cad_file = tmp_path / "model.scad"
    cad_file.write_text("// test scad code")

    params = {
        "source_file": str(cad_file),
        "dry_run": True,
    }

    with patch("charon.agents.machinist.cad.run_cad_export") as mock_export:
        mock_export.return_value = "Geometric export simulated successfully: model.stl."
        result = agent.execute("export_cad_to_stl", params)

        assert "Geometric export simulated successfully" in result
        mock_export.assert_called_once()


def test_export_cad_missing_file_returns_error(agent):
    """Verifies handling when the specified CAD file does not exist."""
    params = {"source_file": "/nonexistent/path/model.scad"}
    result = agent.execute("export_cad_to_stl", params)

    assert "Error: The source file" in result
    assert "cannot be located" in result


# ============================================================================
# 3. CAM Slicing Domain Tests
# ============================================================================

def test_generate_gcode_action_alias(agent, tmp_path):
    """Tests G-Code generation using action alias 'slice'."""
    stl_file = tmp_path / "part.stl"
    stl_file.write_text("solid part")

    params = {
        "stl_file": str(stl_file),
        "dry_run": True,
        "layer_height": 0.2,
        "infill": 20,
    }

    with patch("charon.agents.machinist.slicing.run_slicer") as mock_slicer:
        mock_slicer.return_value = "Toolpaths generated successfully. Output saved to part.gcode."
        result = agent.execute("slice", params)

        assert "Toolpaths generated successfully" in result
        mock_slicer.assert_called_once()


def test_generate_gcode_missing_stl(agent):
    """Ensures error message is returned when no STL parameters are provided."""
    result = agent.execute("generate_gcode", {})
    assert "Error: An 'stl_file' or 3D geometry file parameter is required" in result


# ============================================================================
# 4. Printer Transmission Domain Tests
# ============================================================================

def test_transmit_to_printer_action(agent, tmp_path):
    """Tests transmitting G-Code to printer endpoint."""
    gcode_file = tmp_path / "job.gcode"
    gcode_file.write_text("G28\nG1 Z10")

    params = {
        "gcode_file": str(gcode_file),
        "dry_run": True,
    }

    with patch("charon.agents.machinist.printer.transmit_gcode_http") as mock_transmit:
        mock_transmit.return_value = "Transmission simulated (Dry Run)."
        result = agent.execute("transmit", params)

        assert "Transmission simulated" in result
        mock_transmit.assert_called_once()


# ============================================================================
# 5. Workspace Inspection Tests
# ============================================================================

def test_inspect_cad_files(tmp_path):
    """Tests workspace directory scanning for CAD/CAM artifacts."""
    (tmp_path / "bracket.stl").touch()
    (tmp_path / "enclosure.step").touch()
    (tmp_path / "readme.txt").touch()

    with patch("charon.agents.machinist.cad.PROJECTS_DIR", tmp_path), \
         patch("charon.agents.machinist.cad.resolve_project_path", return_value=tmp_path):

        result = inspect_cad_files(raw_prompt="demo_project")

        assert "bracket.stl" in str(result)
        assert "enclosure.step" in str(result)
        assert "readme.txt" not in str(result)


# ============================================================================
# 6. Path Resolution Utilities Tests
# ============================================================================

def test_resolve_file_path_explicit_file(tmp_path):
    """Tests resolving explicit existing files."""
    test_file = tmp_path / "gear.stl"
    test_file.touch()

    params = {"source_file": str(test_file)}
    resolved = resolve_file_path(params, keys=["source_file"])

    assert resolved == test_file.resolve()


def test_resolve_file_path_fallback_search(tmp_path):
    """Tests searching project subdirectories when explicit file is missing."""
    cad_dir = tmp_path / "cad"
    cad_dir.mkdir()
    target_stl = cad_dir / "assembly.stl"
    target_stl.touch()

    params = {"project_name": "robotics"}

    with patch("charon.config.paths.resolve_project_path", return_value=tmp_path), \
         patch("charon.agents.machinist.utils.resolve_project_path", return_value=tmp_path, create=True):
        resolved = resolve_file_path(params, keys=["source_file"], expected_extensions=[".stl"])
        assert resolved == target_stl.resolve()


# ============================================================================
# 7. Low-Level Tools Integration Unit Tests
# ============================================================================

def test_tool_run_cad_export_dry_run(tmp_path):
    """Tests low-level CAD export tool under dry-run mode."""
    source = tmp_path / "box.scad"
    out = tmp_path / "box.stl"

    res = run_cad_export(source, out, dry_run=True)
    assert "Geometric export simulated successfully" in res
    assert out.exists()


def test_tool_run_slicer_dry_run(tmp_path):
    """Tests low-level slicer tool under dry-run mode."""
    stl = tmp_path / "box.stl"
    gcode = tmp_path / "box.gcode"

    res = run_slicer("prusa-slicer", stl, gcode, layer_height=0.15, dry_run=True)
    assert "Toolpaths generated successfully" in res
    assert gcode.exists()


def test_tool_transmit_gcode_http_dry_run(tmp_path):
    """Tests low-level HTTP G-Code transmitter under dry-run mode."""
    gcode = tmp_path / "box.gcode"
    gcode.touch()

    res = transmit_gcode_http("http://127.0.0.1:5000", gcode, dry_run=True)
    assert "Transmission simulated (Dry Run)" in res
