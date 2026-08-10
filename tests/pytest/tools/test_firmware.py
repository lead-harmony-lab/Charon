import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from charon.tools.firmware import compile_platformio_firmware, flash_platformio_firmware


class TestCompilePlatformioFirmware:
    def test_compile_missing_ini(self, tmp_path):
        # Should fail fast if there's no platformio.ini present
        result = compile_platformio_firmware(tmp_path)
        assert "Error: No PlatformIO configuration" in result

    @patch("charon.tools.firmware.shutil.which")
    def test_compile_dry_run(self, mock_which, tmp_path):
        mock_which.return_value = "/usr/bin/pio"
        ini_file = tmp_path / "platformio.ini"
        ini_file.touch()

        result = compile_platformio_firmware(tmp_path, dry_run=True, environment="esp32")

        assert "simulated successfully" in result
        assert "esp32" in result
        assert "(Dry Run)" in result

    @patch("charon.tools.firmware.shutil.which")
    def test_compile_missing_cli(self, mock_which, tmp_path):
        mock_which.return_value = None
        ini_file = tmp_path / "platformio.ini"
        ini_file.touch()

        result = compile_platformio_firmware(tmp_path)

        assert "simulated successfully" in result
        assert "(Simulated: PlatformIO CLI not found)" in result

    @patch("charon.tools.firmware.shutil.which")
    @patch("charon.tools.firmware.subprocess.run")
    def test_compile_success(self, mock_run, mock_which, tmp_path):
        mock_which.return_value = "/usr/bin/pio"
        ini_file = tmp_path / "platformio.ini"
        ini_file.touch()

        mock_result = MagicMock()
        # Simulate long output to ensure the 500-char truncation logic runs
        mock_result.stdout = "Building..." * 100
        mock_run.return_value = mock_result

        result = compile_platformio_firmware(tmp_path, environment="stm32")

        assert "successfully for environment 'stm32'" in result
        assert "Building..." in result

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "pio"
        assert cmd[1] == "run"
        assert "-e" in cmd
        assert "stm32" in cmd
        assert mock_run.call_args[1]["cwd"] == tmp_path

    @patch("charon.tools.firmware.shutil.which")
    @patch("charon.tools.firmware.subprocess.run")
    def test_compile_subprocess_error(self, mock_run, mock_which, tmp_path):
        mock_which.return_value = "/usr/bin/pio"
        ini_file = tmp_path / "platformio.ini"
        ini_file.touch()

        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["pio", "run"],
            stderr="Compile failed: missing header",
            output=""
        )

        result = compile_platformio_firmware(tmp_path)

        assert "Firmware compilation failed" in result
        assert "Compile failed: missing header" in result


class TestFlashPlatformioFirmware:
    @patch("charon.tools.firmware.shutil.which")
    def test_flash_dry_run(self, mock_which, tmp_path):
        mock_which.return_value = "/usr/bin/pio"
        result = flash_platformio_firmware(tmp_path, port="/dev/ttyUSB0", dry_run=True)

        assert "simulated successfully" in result
        assert "/dev/ttyUSB0" in result
        assert "(Dry Run)" in result

    @patch("charon.tools.firmware.shutil.which")
    def test_flash_missing_cli(self, mock_which, tmp_path):
        mock_which.return_value = None

        result = flash_platformio_firmware(tmp_path)

        assert "simulated successfully" in result
        assert "(Simulated: PlatformIO CLI not found)" in result

    @patch("charon.tools.firmware.shutil.which")
    @patch("charon.tools.firmware.subprocess.run")
    def test_flash_success(self, mock_run, mock_which, tmp_path):
        mock_which.return_value = "/usr/bin/pio"

        mock_result = MagicMock()
        mock_result.stdout = "Flashing..."
        mock_run.return_value = mock_result

        result = flash_platformio_firmware(tmp_path, port="/dev/ttyACM0", environment="esp32")

        assert "successfully flashed" in result
        assert "/dev/ttyACM0" in result

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "upload" in cmd
        assert "-e" in cmd
        assert "esp32" in cmd
        assert "--upload-port" in cmd
        assert "/dev/ttyACM0" in cmd

    @patch("charon.tools.firmware.shutil.which")
    @patch("charon.tools.firmware.subprocess.run")
    def test_flash_subprocess_error(self, mock_run, mock_which, tmp_path):
        mock_which.return_value = "/usr/bin/pio"

        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["pio", "run", "--target", "upload"],
            stderr="Permission denied: /dev/ttyUSB0",
            output=""
        )

        result = flash_platformio_firmware(tmp_path, port="/dev/ttyUSB0")

        assert "Failed to write to target microcontroller" in result
        assert "Permission denied: /dev/ttyUSB0" in result
