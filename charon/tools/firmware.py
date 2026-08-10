"""
charon/tools/firmware.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Stateless tool wrappers for PlatformIO firmware operations.
"""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("Charon.Tools.Firmware")


def compile_platformio_firmware(
    target_path: Path,
    pio_cmd: str = "pio",
    environment: str = "",
    dry_run: bool = False,
) -> str:
    """Triggers a PlatformIO build sequence for embedded firmware."""
    ini_file = target_path / "platformio.ini"
    if not ini_file.exists():
        return f"Error: No PlatformIO configuration (platformio.ini) found in {target_path}."

    cmd = [pio_cmd, "run"]
    if environment:
        cmd.extend(["-e", str(environment)])

    logger.info(
        f"Initiating firmware compilation in {target_path} using command: {' '.join(cmd)}"
    )

    if dry_run or not shutil.which(pio_cmd):
        sim_note = (
            " (Simulated: PlatformIO CLI not found)"
            if not shutil.which(pio_cmd)
            else " (Dry Run)"
        )
        return (
            f"Firmware compilation simulated successfully for environment "
            f"'{environment or 'default'}' in {target_path}.{sim_note}"
        )

    try:
        result = subprocess.run(
            cmd, cwd=target_path, check=True, capture_output=True, text=True
        )
        output = result.stdout.strip()
        trimmed_out = output[-500:] if len(output) > 500 else output
        return f"Firmware compiled successfully for environment '{environment or 'default'}'.\n\n{trimmed_out}"
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip()
        logger.error(f"Compilation failed in {target_path}: {err_msg}")
        return f"Firmware compilation failed:\n{err_msg}"


def flash_platformio_firmware(
    target_path: Path,
    pio_cmd: str = "pio",
    port: str = "auto",
    environment: str = "",
    dry_run: bool = False,
) -> str:
    """Pushes compiled binaries via serial/USB to target microcontroller."""
    cmd = [pio_cmd, "run", "--target", "upload"]
    if environment:
        cmd.extend(["-e", str(environment)])
    if port and port != "auto":
        cmd.extend(["--upload-port", str(port)])

    logger.info(f"Attempting to flash hardware on port '{port}' from {target_path}...")

    if dry_run or not shutil.which(pio_cmd):
        sim_note = (
            " (Simulated: PlatformIO CLI not found)"
            if not shutil.which(pio_cmd)
            else " (Dry Run)"
        )
        return (
            f"Firmware upload sequence simulated successfully on port '{port}' "
            f"in {target_path}.{sim_note}"
        )

    try:
        result = subprocess.run(
            cmd, cwd=target_path, check=True, capture_output=True, text=True
        )
        output = result.stdout.strip()
        trimmed_out = output[-500:] if len(output) > 500 else output
        return f"Firmware successfully flashed to target hardware on port '{port}'.\n\n{trimmed_out}"
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip()
        logger.error(f"Hardware flash failed: {err_msg}")
        return f"Failed to write to target microcontroller on port '{port}':\n{err_msg}"
