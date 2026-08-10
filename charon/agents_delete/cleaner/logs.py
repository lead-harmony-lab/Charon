"""
charon/agents/cleaner/logs.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Log maintenance and hygiene domain module for The Cleaner.
Updated for DynamicActionPayload intent parsing.
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.agents.cleaner.utils import get_param
from charon.config.paths import LOGS_DIR
from charon.intent import DynamicActionPayload

logger = logging.getLogger("CHAROND.Cleaner.Logs")


class LogManager:
    """Handles log pruning, age checks, and retention windows."""

    def __init__(self, logs_dir: Optional[Union[str, Path]] = None):
        self.logs_dir = (
            Path(logs_dir).resolve() if logs_dir else LOGS_DIR
        )

    def prune_logs(
        self,
        payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
        params: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
    ) -> str:
        """Prunes historical/rotated log files from the system logs directory."""
        params = params or {}
        raw_logs_dir = get_param(
            payload, params, "logs_dir", "target_path"
        )
        logs_dir = (
            Path(str(raw_logs_dir)).expanduser().resolve()
            if raw_logs_dir
            else self.logs_dir
        )

        raw_days = get_param(
            payload, params, "max_age_days", "days", default=7
        )
        try:
            max_age_days = int(raw_days)
        except (ValueError, TypeError):
            max_age_days = 7

        keep_active = get_param(
            payload, params, "keep_active", default=True
        )

        if not logs_dir.exists() or not logs_dir.is_dir():
            return f"Log directory does not exist or is inaccessible: {logs_dir}"

        now = time.time()
        max_age_seconds = max_age_days * 86400

        pruned_files = []
        skipped_files = []
        bytes_freed = 0

        try:
            for log_file in logs_dir.iterdir():
                if not log_file.is_file():
                    continue

                # Protect active main logs from deletion unless explicitly requested
                if keep_active and log_file.name in (
                    "charond.log",
                    "charond.error.log",
                ):
                    skipped_files.append(f"{log_file.name} (active stream)")
                    continue

                file_age = now - log_file.stat().st_mtime

                # Remove file ONLY if file_age strictly exceeds retention max_age_seconds
                if file_age > max_age_seconds:
                    file_size = log_file.stat().st_size
                    log_file.unlink()
                    bytes_freed += file_size
                    pruned_files.append(
                        f"{log_file.name} ({file_size / 1024:.1f} KB)"
                    )
                else:
                    skipped_files.append(
                        f"{log_file.name} (within retention window)"
                    )

            mb_freed = bytes_freed / (1024 * 1024)
            logger.info(
                f"Log pruning completed in {logs_dir}. Freed {mb_freed:.2f} MB."
            )

            summary = (
                f"[SYSTEM EXECUTION REPORT]\n"
                f"Action      : System Log Pruning\n"
                f"Target      : {logs_dir}\n"
                f"Freed Space : {mb_freed:.2f} MB\n"
                f"Pruned Files ({len(pruned_files)}):\n"
            )
            if pruned_files:
                summary += "\n".join([f" • {item}" for item in pruned_files])
            else:
                summary += " • None (no qualifying rotated/expired logs found)\n"

            if skipped_files:
                summary += "\nRetained Logs:\n" + "\n".join(
                    [f" • {item}" for item in skipped_files]
                )

            return summary.strip()

        except Exception as e:
            logger.error(f"Error pruning log directory {logs_dir}: {e}")
            return f"An unexpected error occurred while pruning logs: {e}"