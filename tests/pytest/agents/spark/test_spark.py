"""test_spark.py — Unit test suite for TheSpark agent and related tools."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from charon.agents.spark import ACTION_MAP, VALID_SPARK_ACTIONS, TheSpark


@pytest.fixture
def spark_agent():
    """Provides a default instance of TheSpark agent."""
    return TheSpark(pio_cmd="pio", kicad_cli="kicad-cli")


@pytest.fixture
def mock_project_env(tmp_path):
    """Creates a temporary project workspace with PlatformIO and KiCad files."""
    project_dir = tmp_path / "sample_hardware_project"
    project_dir.mkdir(parents=True, exist_ok=True)

    # Create root firmware config
    (project_dir / "platformio.ini").touch()

    # Create CAD subfolder and PCB/Schematic files
    cad_dir = project_dir / "cad"
    cad_dir.mkdir(parents=True, exist_ok=True)
    pcb_file = cad_dir / "mainboard.kicad_pcb"
    sch_file = cad_dir / "mainboard.kicad_sch"
    pcb_file.touch()
    sch_file.touch()

    return {
        "project_dir": project_dir,
        "pcb_file": pcb_file,
        "sch_file": sch_file,
    }


# =============================================================================
# INITIALIZATION & ACTION ROUTING TESTS
# =============================================================================


def test_spark_initialization():
    """Verifies agent initialization and custom CLI executable settings."""
    spark = TheSpark(pio_cmd="/usr/local/bin/pio", kicad_cli="/usr/local/bin/kicad-cli")
    assert spark.pio_cmd == "/usr/local/bin/pio"
    assert spark.kicad_cli == "/usr/local/bin/kicad-cli"


@pytest.mark.parametrize(
    "alias, canonical",
    [
        ("compile", "compile_firmware"),
        ("build", "compile_firmware"),
        ("build_firmware", "compile_firmware"),
        ("flash", "flash_hardware"),
        ("upload", "flash_hardware"),
        ("upload_firmware", "flash_hardware"),
        ("gerbers", "export_gerbers"),
        ("export_pcb", "export_gerbers"),
        ("plot_gerbers", "export_gerbers"),
        ("generate_bom", "export_bom"),
        ("bom", "export_bom"),
    ],
)
def test_action_map_aliases(alias, canonical):
    """Ensures action aliases map to valid canonical actions."""
    assert ACTION_MAP[alias] == canonical
    assert canonical in VALID_SPARK_ACTIONS


def test_invalid_action_raises_value_error(spark_agent):
    """Verifies that an unknown action raises a ValueError."""
    with pytest.raises(ValueError, match="Unknown action 'invalid_spark_action'"):
        spark_agent.execute(action="invalid_spark_action", params={})


# =============================================================================
# FIRMWARE COMPILATION TESTS
# =============================================================================


def test_compile_firmware_missing_directory(spark_agent):
    """Returns an error message when no project directory is supplied or found."""
    result = spark_agent.execute(action="compile_firmware", params={})
    assert "Error: A 'project_directory' or 'project_name' parameter is required" in result


def test_compile_firmware_dry_run(spark_agent, mock_project_env):
    """Tests firmware compilation in dry-run mode."""
    project_dir = mock_project_env["project_dir"]

    with patch(
        "charon.agents.spark.utils.resolve_project_path", return_value=project_dir
    ):
        result = spark_agent.execute(
            action="compile_firmware",
            parameters={
                "project_directory": str(project_dir),
                "environment": "esp32dev",
                "dry_run": True,
            },
        )
        assert "Firmware compilation simulated successfully" in result
        assert "esp32dev" in result


@patch("shutil.which", return_value="/usr/bin/pio")
@patch("subprocess.run")
def test_compile_firmware_execution_success(
    mock_subproc, mock_which, spark_agent, mock_project_env
):
    """Verifies successful subprocess execution of PlatformIO build."""
    project_dir = mock_project_env["project_dir"]
    mock_subproc.return_value = MagicMock(
        returncode=0, stdout="[SUCCESS] Took 3.12 seconds"
    )

    with patch(
        "charon.agents.spark.utils.resolve_project_path", return_value=project_dir
    ):
        result = spark_agent.execute(
            action="build",
            parameters={
                "project_directory": str(project_dir),
                "environment": "uno",
            },
        )
        assert "Firmware compiled successfully" in result
        assert "[SUCCESS] Took 3.12 seconds" in result

        mock_subproc.assert_called_once()
        cmd_args = mock_subproc.call_args[0][0]
        assert cmd_args == ["pio", "run", "-e", "uno"]


def test_compile_firmware_nested_firmware_dir(spark_agent, tmp_path):
    """Tests auto-detection of a nested 'firmware' directory containing platformio.ini."""
    root_dir = tmp_path / "nested_project"
    firmware_dir = root_dir / "firmware"
    firmware_dir.mkdir(parents=True, exist_ok=True)
    (firmware_dir / "platformio.ini").touch()

    with patch("charon.agents.spark.utils.resolve_project_path", return_value=root_dir):
        result = spark_agent.execute(
            action="compile_firmware",
            parameters={"project_directory": str(root_dir), "dry_run": True},
        )
        assert "Firmware compilation simulated successfully" in result
        assert str(firmware_dir) in result


# =============================================================================
# HARDWARE FLASHING TESTS
# =============================================================================


def test_flash_hardware_dry_run(spark_agent, mock_project_env):
    """Tests hardware flashing simulation in dry-run mode."""
    project_dir = mock_project_env["project_dir"]

    with patch(
        "charon.agents.spark.utils.resolve_project_path", return_value=project_dir
    ):
        result = spark_agent.execute(
            action="flash",
            parameters={
                "project_directory": str(project_dir),
                "port": "/dev/ttyUSB0",
                "dry_run": True,
            },
        )
        assert "Firmware upload sequence simulated successfully" in result
        assert "/dev/ttyUSB0" in result


@patch("shutil.which", return_value="/usr/bin/pio")
@patch("subprocess.run")
def test_flash_hardware_execution_success(
    mock_subproc, mock_which, spark_agent, mock_project_env
):
    """Verifies successful subprocess execution of PlatformIO upload."""
    project_dir = mock_project_env["project_dir"]
    mock_subproc.return_value = MagicMock(
        returncode=0, stdout="[SUCCESS] Flashed target MCU"
    )

    with patch(
        "charon.agents.spark.utils.resolve_project_path", return_value=project_dir
    ):
        result = spark_agent.execute(
            action="upload_firmware",
            parameters={
                "project_directory": str(project_dir),
                "port": "/dev/ttyACM0",
                "environment": "stm32",
            },
        )
        assert "Firmware successfully flashed to target hardware" in result

        cmd_args = mock_subproc.call_args[0][0]
        assert cmd_args == [
            "pio",
            "run",
            "--target",
            "upload",
            "-e",
            "stm32",
            "--upload-port",
            "/dev/ttyACM0",
        ]


# =============================================================================
# GERBER & EDA EXPORT TESTS
# =============================================================================


def test_export_gerbers_missing_pcb(spark_agent):
    """Returns an error when no PCB file can be located."""
    result = spark_agent.execute(action="export_gerbers", params={})
    assert "Error: A valid 'pcb_file' or project containing a .kicad_pcb file" in result


def test_export_gerbers_dry_run(spark_agent, mock_project_env):
    """Simulates KiCad Gerber export using dry_run=True."""
    pcb_file = mock_project_env["pcb_file"]

    result = spark_agent.execute(
        action="export_gerbers",
        parameters={"pcb_file": str(pcb_file), "dry_run": True},
    )
    assert "Gerber fabrication files successfully plotted to" in result


@patch("shutil.which", return_value="/usr/bin/kicad-cli")
@patch("subprocess.run")
def test_export_gerbers_execution_success(mock_subproc, mock_which, spark_agent, mock_project_env):
    """Verifies invocation of KiCad CLI for Gerber and drill file generation."""
    pcb_file = mock_project_env["pcb_file"]
    mock_subproc.return_value = MagicMock(returncode=0, stdout="")

    result = spark_agent.execute(
        action="export_gerbers",
        parameters={"pcb_file": str(pcb_file)},
    )
    assert "Gerber fabrication & drill files successfully generated" in result
    assert mock_subproc.call_count == 2  # Gerber plot + Drill plot


# =============================================================================
# BOM EXPORT TESTS
# =============================================================================


def test_export_bom_dry_run(spark_agent, mock_project_env):
    """Simulates KiCad BOM export using dry_run=True."""
    pcb_file = mock_project_env["pcb_file"]

    result = spark_agent.execute(
        action="export_bom",
        parameters={"pcb_file": str(pcb_file), "dry_run": True},
    )
    assert "Bill of Materials (BOM) exported successfully to" in result


@patch("shutil.which", return_value="/usr/bin/kicad-cli")
@patch("subprocess.run")
def test_export_bom_execution_success(mock_subproc, mock_which, spark_agent, mock_project_env):
    """Verifies invocation of KiCad CLI for schematic BOM CSV generation."""
    pcb_file = mock_project_env["pcb_file"]
    mock_subproc.return_value = MagicMock(returncode=0, stdout="")

    result = spark_agent.execute(
        action="bom",
        parameters={"pcb_file": str(pcb_file)},
    )
    assert "Bill of Materials (BOM) exported successfully" in result
    mock_subproc.assert_called_once()
