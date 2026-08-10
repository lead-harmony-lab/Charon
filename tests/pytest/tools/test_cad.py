import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from charon.tools.cad import run_cad_export, run_slicer, transmit_gcode_http


class TestRunCADExport:
    @pytest.fixture
    def mock_paths(self, tmp_path):
        return {
            "scad": tmp_path / "model.scad",
            "fcstd": tmp_path / "model.FCStd",
            "out": tmp_path / "output.stl",
        }

    def test_run_cad_export_openscad_success(self, mock_paths):
        with patch("shutil.which") as mock_which, patch(
                "subprocess.run"
        ) as mock_run:
            mock_which.return_value = "/usr/bin/openscad"

            result = run_cad_export(mock_paths["scad"], mock_paths["out"])

            mock_run.assert_called_once_with(
                ["openscad", "-o", str(mock_paths["out"]), str(mock_paths["scad"])],
                check=True,
                capture_output=True,
                text=True,
            )
            assert "Successfully exported geometric data" in result

    def test_run_cad_export_freecad_success(self, mock_paths):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/FreeCADcmd" if x == "FreeCADcmd" else None):
            with patch("subprocess.run") as mock_run:
                result = run_cad_export(mock_paths["fcstd"], mock_paths["out"])

                mock_run.assert_called_once_with(
                    ["FreeCADcmd", str(mock_paths["fcstd"]), str(mock_paths["out"])],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                assert "Successfully exported geometric data" in result

    def test_run_cad_export_dry_run(self, mock_paths):
        result = run_cad_export(mock_paths["scad"], mock_paths["out"], dry_run=True)
        assert "simulated successfully" in result
        assert "(Dry Run)" in result
        assert mock_paths["out"].exists()

    def test_run_cad_export_no_cli_found(self, mock_paths):
        with patch("shutil.which", return_value=None):
            result = run_cad_export(mock_paths["scad"], mock_paths["out"])
            assert "simulated successfully" in result
            assert "No FreeCADcmd/OpenSCAD CLI found" in result
            assert mock_paths["out"].exists()

    def test_run_cad_export_subprocess_error(self, mock_paths):
        with patch("shutil.which", return_value="/usr/bin/openscad"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    returncode=1, cmd="openscad", stderr="Syntax error in file", output=""
                )
                result = run_cad_export(mock_paths["scad"], mock_paths["out"])
                assert "A failure occurred during CAD translation" in result
                assert "Syntax error in file" in result

    def test_run_cad_export_subprocess_error_stdout_fallback(self, mock_paths):
        with patch("shutil.which", return_value="/usr/bin/openscad"):
            with patch("subprocess.run") as mock_run:
                # Test fallback to stdout if stderr is empty
                mock_run.side_effect = subprocess.CalledProcessError(
                    returncode=1, cmd="openscad", stderr="", output="Output error info"
                )
                result = run_cad_export(mock_paths["scad"], mock_paths["out"])
                assert "Output error info" in result


class TestRunSlicer:
    @pytest.fixture
    def mock_paths(self, tmp_path):
        return {
            "stl": tmp_path / "model.stl",
            "gcode": tmp_path / "model.gcode",
        }

    def test_run_slicer_basic(self, mock_paths):
        with patch("shutil.which", return_value="/usr/bin/prusa-slicer"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.stdout = "Slicing complete."

                result = run_slicer(
                    "prusa-slicer", mock_paths["stl"], mock_paths["gcode"]
                )

                mock_run.assert_called_once_with(
                    [
                        "prusa-slicer",
                        "--export-gcode",
                        str(mock_paths["stl"]),
                        "--output",
                        str(mock_paths["gcode"]),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                assert "G-Code generated successfully" in result
                assert "Slicing complete." in result

    def test_run_slicer_with_all_flags(self, mock_paths):
        with patch("shutil.which", return_value="/usr/bin/prusa-slicer"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.stdout = "Slicing complete."

                run_slicer(
                    "prusa-slicer",
                    mock_paths["stl"],
                    mock_paths["gcode"],
                    profile="PLA_Profile.ini",
                    layer_height=0.15,
                    infill=20
                )

                cmd_called = mock_run.call_args[0][0]
                assert "--load" in cmd_called
                assert "PLA_Profile.ini" in cmd_called
                assert "--layer-height" in cmd_called
                assert "0.15" in cmd_called
                assert "--fill-density" in cmd_called
                assert "20%" in cmd_called

    def test_run_slicer_output_truncation(self, mock_paths):
        with patch("shutil.which", return_value="/usr/bin/prusa-slicer"):
            with patch("subprocess.run") as mock_run:
                long_output = "A" * 400 + "END_OF_OUTPUT"
                mock_run.return_value.stdout = long_output

                result = run_slicer("prusa-slicer", mock_paths["stl"], mock_paths["gcode"])

                assert "END_OF_OUTPUT" in result
                assert len(result) < 500  # Should be truncated to 300 chars + prefix

    def test_run_slicer_dry_run(self, mock_paths):
        result = run_slicer("prusa-slicer", mock_paths["stl"], mock_paths["gcode"], dry_run=True)
        assert "Toolpaths generated successfully" in result
        assert "(Dry Run)" in result
        assert mock_paths["gcode"].exists()

    def test_run_slicer_not_found(self, mock_paths):
        with patch("shutil.which", return_value=None):
            result = run_slicer("unknown-slicer", mock_paths["stl"], mock_paths["gcode"])
            assert "Simulated: Slicer binary" in result
            assert mock_paths["gcode"].exists()

    def test_run_slicer_subprocess_error(self, mock_paths):
        with patch("shutil.which", return_value="/usr/bin/prusa-slicer"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    returncode=1, cmd="prusa-slicer", stderr="Invalid geometry", output=""
                )
                result = run_slicer("prusa-slicer", mock_paths["stl"], mock_paths["gcode"])
                assert "critical failure occurred" in result
                assert "Invalid geometry" in result


class TestTransmitGCodeHTTP:
    @pytest.fixture
    def mock_gcode(self, tmp_path):
        gcode_file = tmp_path / "test.gcode"
        gcode_file.write_bytes(b"G28 ; home all axes\nG1 Z5 F5000")
        return gcode_file

    def test_transmit_gcode_dry_run(self, mock_gcode):
        result = transmit_gcode_http(
            "http://octopi.local", mock_gcode, dry_run=True
        )
        assert "Transmission simulated (Dry Run)" in result
        assert "test.gcode" in result

    @patch("urllib.request.urlopen")
    def test_transmit_gcode_success(self, mock_urlopen, mock_gcode):
        mock_response = MagicMock()
        mock_response.getcode.return_value = 201
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = transmit_gcode_http(
            "http://octopi.local", mock_gcode, api_key="secret123"
        )

        assert "Transmission complete" in result
        assert "test.gcode" in result
        mock_urlopen.assert_called_once()

        req = mock_urlopen.call_args[0][0]
        assert req.headers["X-api-key"] == "secret123"
        assert req.get_method() == "POST"

    @patch("urllib.request.urlopen")
    def test_transmit_gcode_http_error_code(self, mock_urlopen, mock_gcode):
        mock_response = MagicMock()
        mock_response.getcode.return_value = 400
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = transmit_gcode_http("http://octopi.local", mock_gcode)
        assert "Printer responded with status code HTTP 400" in result

    @patch("urllib.request.urlopen")
    def test_transmit_gcode_network_error(self, mock_urlopen, mock_gcode):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        result = transmit_gcode_http("http://octopi.local", mock_gcode)
        assert "Network transmission attempt to http://octopi.local ended" in result
        assert "Connection refused" in result

    @patch("urllib.request.urlopen")
    def test_transmit_gcode_timeout_error(self, mock_urlopen, mock_gcode):
        mock_urlopen.side_effect = TimeoutError("Timed out")

        result = transmit_gcode_http("http://octopi.local", mock_gcode)
        assert "Network transmission attempt" in result
        assert "Timed out" in result
