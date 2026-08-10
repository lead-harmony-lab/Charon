"""
charon/core/dispatcher/artifacts.py
System Version: v0.4.0 | File Revision: 1.3.0

Module: Artifact extraction utilities for inspecting step execution results.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.core.skills.librarian import SkillLibrarian


def extract_artifacts_from_result(
    action: str,
    result: Any,
    parameters: Dict[str, Any],
    capability_info: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[Path, str]] = None,
) -> Dict[str, Any]:
    """Inspects step output and automatically extracts produced ground truth artifacts."""
    produced: Dict[str, Any] = {}
    res_str = str(result)

    if capability_info is None:
        librarian = SkillLibrarian.get_instance(db_path)
        capability_info = librarian.get_action_details(action) or {}

    expected_artifacts = capability_info.get("produced_artifacts", [])

    # Handle stringified JSON arrays from SQLite Schema V2
    if isinstance(expected_artifacts, str):
        try:
            expected_artifacts = json.loads(expected_artifacts)
        except Exception:
            expected_artifacts = [expected_artifacts]

    if not isinstance(expected_artifacts, (list, tuple, set)):
        expected_artifacts = []

    # 1. Path extraction for file-producing capabilities (POSIX & Windows compatible)
    if not expected_artifacts or any(
        k in expected_artifacts for k in ("resolved_file_path", "file_path", "target_path")
    ):
        path_pattern = (
            r'(?:[a-zA-Z]:[/\\][^\s\'"\n]+|/[^\s\'"\n]+)'
            r'\.(?:pdf|png|jpg|jpeg|txt|csv|json|py|gcode|stl|step|igs|dxf|dwg|xlsx|md)'
        )
        path_match = re.search(path_pattern, res_str)
        if path_match:
            produced["resolved_file_path"] = path_match.group(0)
        elif "target_path" in parameters:
            produced["resolved_file_path"] = parameters["target_path"]
        elif "resolved_file_path" in parameters:
            produced["resolved_file_path"] = parameters["resolved_file_path"]

    # 2. Status / PID extraction for OS GUI launching
    if "launch_status" in expected_artifacts or action in (
        "launch_gui_viewer",
        "open_file",
        "execute_command",
    ):
        produced["launch_status"] = "LAUNCHED"
        produced["last_executed_command"] = parameters.get("command", "")

    # 3. Output text synthesis
    produced["response_text"] = res_str

    return produced