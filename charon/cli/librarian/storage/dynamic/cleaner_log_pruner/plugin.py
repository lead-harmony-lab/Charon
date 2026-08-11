"""Plugin entrypoint module for cleaner_log_pruner."""

import logging
from pathlib import Path
from typing import Any, Dict, Union
from charon.agents.cleaner.logs import LogManager

logger = logging.getLogger("CHAROND.Skills.CleanerLogPruner")


def handle_prune_logs(
    params: Dict[str, Any], logs_dir: Union[str, Path] = None, raw_prompt: str = ""
) -> Dict[str, Any]:
    """Prunes expired log files from the system log directory."""
    manager = LogManager(logs_dir=logs_dir)
    result = manager.prune_logs(params=params, raw_prompt=raw_prompt)
    return {"status": "success", "result": result}


def execute_action(
    action_name: str,
    params: Dict[str, Any],
    logs_dir: Union[str, Path] = None,
    raw_prompt: str = "",
) -> Dict[str, Any]:
    """Main dispatch router for log maintenance operations."""
    if action_name == "prune_logs":
        return handle_prune_logs(params, logs_dir, raw_prompt)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'cleaner_log_pruner'."
    )