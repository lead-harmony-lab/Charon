import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from charon.tools.eda import export_kicad_bom, export_kicad_gerbers


class TestExportKicadGerbers:
    def test_export_gerbers_dry_run(self, tmp_path):
        pcb_path = tmp_path / "test_board.kicad_pcb"
        pcb_path.touch()

        # Execute with dry_run=True
        result = export_kicad_gerbers(pcb_path, dry_run=True)

        expected_dir = tmp_path / "gerbers"
        assert expected_dir.exists()
        assert "successfully plotted" in result
        assert "(Dry Run)" in result

    @patch("charon.tools.eda.shutil.which")
    def test_export_gerbers_missing_cli(self, mock_which, tmp_path):
        mock_which.return_value = None
        pcb_path = tmp_path / "test_board.kicad_pcb"

        # Should simulate execution if KiCad CLI isn't installed
        result = export_kicad_gerbers(pcb_path)

        assert "successfully plotted" in result
        assert "(Simulated: KiCad CLI not found)" in result

    @patch("charon.tools.eda.shutil.which")
    @patch("charon.tools.eda.subprocess.run")
    def test_export_gerbers_success(self, mock_run, mock_which, tmp_path):
        mock_which.return_value = "/usr/bin/kicad-cli"
        pcb_path = tmp_path / "test_board.kicad_pcb"
        output_dir = tmp_path / "custom_gerbers"

        result = export_kicad_gerbers(pcb_path, output_dir=output_dir)

        assert "successfully generated" in result
        assert str(output_dir) in result
        assert output_dir.exists()

        # Verify both gerber and drill export commands were called
        assert mock_run.call_count == 2

        gerber_call = mock_run.call_args_list[0]
        assert "pcb" in gerber_call[0][0]
        assert "gerbers" in gerber_call[0][0]

        drill_call = mock_run.call_args_list[1]
        assert "drl" in drill_call[0][0]

    @patch("charon.tools.eda.shutil.which")
    @patch("charon.tools.eda.subprocess.run")
    def test_export_gerbers_subprocess_error(self, mock_run, mock_which, tmp_path):
        mock_which.return_value = "/usr/bin/kicad-cli"
        pcb_path = tmp_path / "test_board.kicad_pcb"

        # Simulate a crash during the Gerber export
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["kicad-cli"],
            stderr="Error loading PCB file",
            output=""
        )

        result = export_kicad_gerbers(pcb_path)

        assert "failure occurred" in result
        assert "Error loading PCB file" in result


class TestExportKicadBom:
    def test_export_bom_dry_run(self, tmp_path):
        pcb_path = tmp_path / "test_board.kicad_pcb"

        result = export_kicad_bom(pcb_path, dry_run=True)

        expected_dir = tmp_path / "bom"
        assert expected_dir.exists()
        assert "exported successfully" in result
        assert "test_board_bom.csv" in result
        assert "(Dry Run)" in result

    def test_export_bom_custom_output_dir(self, tmp_path):
        pcb_path = tmp_path / "test_board.kicad_pcb"
        custom_dir = tmp_path / "custom_bom_dir"

        result = export_kicad_bom(pcb_path, output_dir=custom_dir, dry_run=True)

        assert custom_dir.exists()
        assert "exported successfully" in result
        assert str(custom_dir) in result

    def test_export_bom_nonexistent_parent_directory(self, tmp_path):
        # Path in a directory that does not exist yet to trigger non-existent parent branch
        pcb_path = tmp_path / "new_dir" / "test_board.kicad_pcb"

        result = export_kicad_bom(pcb_path, dry_run=True)

        expected_dir = tmp_path / "new_dir"
        assert expected_dir.exists()
        assert "exported successfully" in result
        assert "test_board_bom.csv" in result

    @patch("charon.tools.eda.shutil.which")
    def test_export_bom_missing_cli(self, mock_which, tmp_path):
        mock_which.return_value = None
        pcb_path = tmp_path / "test_board.kicad_pcb"

        result = export_kicad_bom(pcb_path)

        assert "exported successfully" in result
        assert "(Simulated: KiCad CLI not found)" in result

    @patch("charon.tools.eda.shutil.which")
    @patch("charon.tools.eda.subprocess.run")
    def test_export_bom_success(self, mock_run, mock_which, tmp_path):
        mock_which.return_value = "/usr/bin/kicad-cli"
        pcb_path = tmp_path / "test_board.kicad_pcb"
        expected_sch_path = tmp_path / "test_board.kicad_sch"

        result = export_kicad_bom(pcb_path)

        assert "exported successfully" in result

        # Verify correct schematic generation target was passed to subprocess
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]

        assert "sch" in cmd_args
        assert "bom" in cmd_args
        assert str(expected_sch_path) in cmd_args
        assert any("test_board_bom.csv" in arg for arg in cmd_args)

    @patch("charon.tools.eda.shutil.which")
    @patch("charon.tools.eda.subprocess.run")
    def test_export_bom_subprocess_error(self, mock_run, mock_which, tmp_path):
        mock_which.return_value = "/usr/bin/kicad-cli"
        pcb_path = tmp_path / "test_board.kicad_pcb"

        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=2,
            cmd=["kicad-cli"],
            stderr="Could not parse schematic file",
            output=""
        )

        result = export_kicad_bom(pcb_path)

        assert "failure occurred" in result
        assert "Could not parse schematic file" in result
