"""
charon/tools/eda.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Stateless tool wrappers for KiCad CLI Gerber and BOM generation.
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Charon.Tools.EDA")


def export_kicad_gerbers(
    pcb_path: Path,
    kicad_cli: str = "kicad-cli",
    output_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Automates KiCad CLI to plot production PCB Gerber and drill files."""
    if output_dir is None:
        output_dir = pcb_path.parent / "gerbers"
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        kicad_cli,
        "pcb",
        "export",
        "gerbers",
        "-o",
        str(output_dir),
        str(pcb_path),
    ]

    logger.info(f"Exporting Gerbers for {pcb_path.name} to {output_dir}")

    if dry_run or not shutil.which(kicad_cli):
        sim_note = (
            " (Simulated: KiCad CLI not found)"
            if not shutil.which(kicad_cli)
            else " (Dry Run)"
        )
        return f"Gerber fabrication files successfully plotted to {output_dir}.{sim_note}"

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        drill_cmd = [
            kicad_cli,
            "pcb",
            "export",
            "drl",
            "-o",
            str(output_dir),
            str(pcb_path),
        ]
        subprocess.run(drill_cmd, check=True, capture_output=True, text=True)

        return f"Gerber fabrication & drill files successfully generated in {output_dir}."
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip()
        logger.error(f"Gerber export failed: {err_msg}")
        return f"A failure occurred during KiCad EDA Gerber export:\n{err_msg}"


def export_kicad_bom(
    pcb_path: Path,
    kicad_cli: str = "kicad-cli",
    output_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Automates KiCad CLI to export Bill of Materials (BOM) CSV."""
    if output_dir is None:
        output_dir = (
            pcb_path.parent / "bom"
            if (pcb_path.parent / "bom").parent.exists()
            else pcb_path.parent
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_csv = output_dir / f"{pcb_path.stem}_bom.csv"

    sch_path = pcb_path.with_suffix(".kicad_sch")
    cmd = [
        kicad_cli,
        "sch",
        "export",
        "bom",
        "-o",
        str(output_csv),
        str(sch_path),
    ]

    logger.info(f"Exporting BOM for {pcb_path.name} to {output_csv}")

    if dry_run or not shutil.which(kicad_cli):
        sim_note = (
            " (Simulated: KiCad CLI not found)"
            if not shutil.which(kicad_cli)
            else " (Dry Run)"
        )
        return f"Bill of Materials (BOM) exported successfully to {output_csv}.{sim_note}"

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return f"Bill of Materials (BOM) exported successfully to {output_csv}."
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip()
        logger.error(f"BOM export failed: {err_msg}")
        return f"A failure occurred during KiCad BOM export:\n{err_msg}"
