"""
Dynamic skill plugin for action 'extract_pdf_ocr'.
Synthesized and finalized for Charon Skill Forge.
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Union

logger = logging.getLogger("charon.skills.extract_pdf_ocr_skill")


def execute(
    agent_name: str, parameters: Dict[str, Any], raw_prompt: str = ""
) -> Union[str, Dict[str, Any]]:
    """Performs Tesseract OCR on a document file with system requirement checks."""

    # 1. Host binary availability check
    if not shutil.which("tesseract"):
        logger.warning(
            f"[extract_pdf_ocr_skill] Aborting for '{agent_name}': "
            "'tesseract' binary is not installed on host system PATH."
        )
        return {
            "status": "error",
            "action": "extract_pdf_ocr",
            "executed_by": agent_name,
            "error_type": "MissingSystemPrerequisite",
            "message": (
                "Execution aborted: 'tesseract' CLI binary is missing on the host OS PATH. "
                "Install via 'sudo apt install tesseract-ocr' to enable OCR capability."
            ),
        }

    # 2. Input validation
    pdf_path_str = parameters.get("pdf_path") or parameters.get("file_path")
    if not pdf_path_str:
        return {"status": "error", "message": "Missing required parameter 'pdf_path'"}

    pdf_path = Path(pdf_path_str).resolve()
    if not pdf_path.exists():
        return {"status": "error", "message": f"Input PDF file not found at {pdf_path}"}

    output_txt_base = pdf_path.with_suffix(".ocr")
    output_txt_file = Path(f"{output_txt_base}.txt")

    cmd = ["tesseract", str(pdf_path), str(output_txt_base)]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        extracted_text = ""
        if output_txt_file.exists():
            extracted_text = output_txt_file.read_text(encoding="utf-8")

        return {
            "status": "success",
            "action": "extract_pdf_ocr",
            "executed_by": agent_name,
            "output_file": str(output_txt_file),
            "text_preview": extracted_text[:500],
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "error_type": "MissingSystemPrerequisite",
            "message": "'tesseract' executable was not found on system PATH.",
        }
    except subprocess.CalledProcessError as err:
        logger.error(f"[extract_pdf_ocr_skill] OCR execution error: {err.stderr}")
        return {
            "status": "failed",
            "error": err.stderr.strip(),
            "command": " ".join(cmd),
        }