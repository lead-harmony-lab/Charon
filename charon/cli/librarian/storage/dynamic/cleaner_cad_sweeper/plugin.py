"""Plugin entrypoint module for cleaner_cad_sweeper."""

import logging
from pathlib import Path
from typing import Any, Dict, Union
from charon.agents.cleaner.cad import CADManager

logger = logging.getLogger("CHAROND.Skills.CleanerCADSweeper")


def handle_sweep_cad_iterations(
    params: Dict[str, Any], projects_dir: Union[str, Path] = None, raw_prompt: str = ""
) -> Dict[str, Any]:
    """Sweeps old CAD version iterations into archive subdirectories."""
    manager = CADManager(projects_dir=projects_dir)
    result = manager.sweep_cad_iterations(params=params, raw_prompt=raw_prompt)
    return {"status": "success", "result": result}


def execute_action(
    action_name: str,
    params: Dict[str, Any],
    projects_dir: Union[str, Path] = None,
    raw_prompt: str = "",
) -> Dict[str, Any]:
    """Main dispatch router for CAD sweeping operations."""
    if action_name == "sweep_cad_iterations":
        return handle_sweep_cad_iterations(params, projects_dir, raw_prompt)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'cleaner_cad_sweeper'."
    )