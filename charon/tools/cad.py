"""
charon/tools/cad.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Stateless CAD/CAM and Fabrication Tools.

Provides low-level functions for CAD file translation, CAM slicer CLI execution,
and HTTP transmission to 3D printers and CNC hardware.
"""

import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger("CHAROND.Tools.CAD")


def run_cad_export(
    source_path: Path,
    out_file: Path,
    dry_run: bool = False,
) -> str:
    """Executes a headless CAD converter (OpenSCAD, FreeCADcmd) to export STL geometry."""
    if source_path.suffix.lower() == ".scad" and shutil.which("openscad"):
        cmd = ["openscad", "-o", str(out_file), str(source_path)]
    elif shutil.which("FreeCADcmd"):
        cmd = ["FreeCADcmd", str(source_path), str(out_file)]
    else:
        cmd = None

    if dry_run or not cmd:
        sim_reason = (
            " (Dry Run)"
            if dry_run
            else " (Simulated: No FreeCADcmd/OpenSCAD CLI found)"
        )
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.touch(exist_ok=True)
        return f"Geometric export simulated successfully: {out_file.name}{sim_reason}."

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return f"Successfully exported geometric data to {out_file}."
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip()
        logger.error(f"CAD Export failed: {err_msg}")
        return f"A failure occurred during CAD translation:\n{err_msg}"


def run_slicer(
    slicer_cmd: str,
    stl_path: Path,
    gcode_path: Path,
    profile: Optional[str] = None,
    layer_height: Optional[float] = None,
    infill: Optional[int] = None,
    dry_run: bool = False,
) -> str:
    """Invokes local slicer CLI executable to generate G-Code toolpaths."""
    cmd = [
        slicer_cmd,
        "--export-gcode",
        str(stl_path),
        "--output",
        str(gcode_path),
    ]
    if profile:
        cmd.extend(["--load", str(profile)])
    if layer_height is not None:
        cmd.extend(["--layer-height", str(layer_height)])
    if infill is not None:
        cmd.extend(["--fill-density", f"{infill}%"])

    logger.info(f"Slicing geometry: {stl_path.name} -> {gcode_path.name}")

    slicer_binary = shutil.which(slicer_cmd)
    if dry_run or not slicer_binary:
        sim_reason = (
            " (Dry Run)"
            if dry_run
            else f" (Simulated: Slicer binary '{slicer_cmd}' not found)"
        )
        gcode_path.parent.mkdir(parents=True, exist_ok=True)
        gcode_path.touch(exist_ok=True)
        return f"Toolpaths generated successfully. Output saved to {gcode_path.name}.{sim_reason}"

    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True
        )
        output = result.stdout.strip()
        trimmed_out = output[-300:] if len(output) > 300 else output
        return f"G-Code generated successfully at {gcode_path}.\n\n{trimmed_out}"
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip()
        logger.error(f"Slicing procedure failed: {err_msg}")
        return f"A critical failure occurred during G-Code generation:\n{err_msg}"


def transmit_gcode_http(
    target_url: str,
    gcode_path: Path,
    api_key: str = "",
    start_print: bool = False,
    dry_run: bool = False,
) -> str:
    """Transmits G-Code via HTTP multi-part upload to an OctoPrint/Moonraker API endpoint."""
    logger.info(f"Connecting to fabrication endpoint at {target_url}...")

    if dry_run:
        return (
            f"Transmission simulated (Dry Run). G-Code file {gcode_path.name} "
            f"prepared for delivery to {target_url} (start_print={start_print})."
        )

    try:
        upload_endpoint = f"{target_url.rstrip('/')}/api/files/local"
        boundary = "----CharonBoundary"

        content = gcode_path.read_bytes()

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{gcode_path.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

        headers = {
            "Content-Type": f"multipart/boundary={boundary}",
            "User-Agent": "Charon-Machinist/1.0",
        }
        if api_key:
            headers["X-Api-Key"] = api_key

        req = urllib.request.Request(
            upload_endpoint, data=body, headers=headers, method="POST"
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.getcode()
            if status in (200, 201):
                return f"Transmission complete. Fabrication unit received {gcode_path.name} at {target_url}."
            else:
                return f"Printer responded with status code HTTP {status}."

    except (urllib.error.URLError, TimeoutError, Exception) as e:
        logger.warning(f"Hardware printer transmission failed or offline: {e}")
        return (
            f"Network transmission attempt to {target_url} ended. "
            f"G-Code file {gcode_path.name} is staged and ready for manual job dispatch ({e})."
        )
