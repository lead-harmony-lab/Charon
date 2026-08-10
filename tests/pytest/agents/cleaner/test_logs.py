"""Tests for The Cleaner log pruning and retention maintenance handlers."""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from charon.agents.cleaner.logs import LogManager
from charon.intent import CleanerPayload


class TestLogManager:
    """Test suite covering log pruning, active stream protection, and age filters."""

    def test_init_default_and_custom_logs_dir(self, tmp_path: Path):
        """Tests LogManager initialization with default and custom paths."""
        manager_custom = LogManager(logs_dir=tmp_path)
        assert manager_custom.logs_dir == tmp_path.resolve()

        manager_default = LogManager()
        assert isinstance(manager_default.logs_dir, Path)

    def test_prune_logs_nonexistent_directory(self, tmp_path: Path):
        """Tests error response when the target log directory is missing."""
        missing_dir = tmp_path / "nonexistent_logs"
        manager = LogManager()
        result = manager.prune_logs(params={"logs_dir": str(missing_dir)})
        assert f"Log directory does not exist or is inaccessible: {missing_dir.resolve()}" in result

    def test_prune_logs_invalid_days_fallback(self, tmp_path: Path):
        """Tests fallback to 7 days retention when max_age_days is non-integer."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        manager = LogManager(logs_dir=logs_dir)
        payload = CleanerPayload(action="prune_logs", days="invalid_number")
        result = manager.prune_logs(payload=payload)

        assert "[SYSTEM EXECUTION REPORT]" in result
        assert "System Log Pruning" in result

    def test_prune_logs_keep_active_and_retention_window(self, tmp_path: Path):
        """Tests that active main log streams and unexpired log files are preserved."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        now = time.time()
        old_time = now - (10 * 86400)  # 10 days old

        # Active log streams
        active_log = logs_dir / "charond.log"
        active_log.write_text("active log content")
        active_err = logs_dir / "charond.error.log"
        active_err.write_text("active err content")

        # Expired rotated log
        old_log = logs_dir / "charond.log.1"
        old_log.write_text("old rotated content")

        # Unexpired rotated log
        recent_log = logs_dir / "charond.log.recent"
        recent_log.write_text("recent content")

        # Set mtimes
        import os
        os.utime(active_log, (old_time, old_time))
        os.utime(old_log, (old_time, old_time))
        os.utime(recent_log, (now, now))

        # Subdirectory to exercise non-file skipping
        (logs_dir / "sub_folder").mkdir()

        manager = LogManager(logs_dir=logs_dir)
        result = manager.prune_logs(params={"max_age_days": 7, "keep_active": True})

        assert "Freed Space :" in result
        assert "charond.log.1" in result
        assert "charond.log (active stream)" in result
        assert "charond.log.recent (within retention window)" in result

        assert not old_log.exists()
        assert active_log.exists()
        assert recent_log.exists()

    def test_prune_logs_keep_active_disabled(self, tmp_path: Path):
        """Tests that active log streams are pruned if keep_active is explicitly False."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        old_time = time.time() - (10 * 86400)
        active_log = logs_dir / "charond.log"
        active_log.write_text("active log content")

        import os
        os.utime(active_log, (old_time, old_time))

        manager = LogManager(logs_dir=logs_dir)
        result = manager.prune_logs(params={"keep_active": False, "days": 5})

        assert "charond.log" in result
        assert not active_log.exists()

    def test_prune_logs_no_qualifying_files(self, tmp_path: Path):
        """Tests report output when no expired log files exist in the target directory."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        manager = LogManager(logs_dir=logs_dir)
        result = manager.prune_logs()

        assert "• None (no qualifying rotated/expired logs found)" in result

    def test_prune_logs_unexpected_exception(self, tmp_path: Path):
        """Tests error handling when an unhandled exception occurs during iteration."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        manager = LogManager(logs_dir=logs_dir)
        with patch.object(Path, "iterdir", side_effect=PermissionError("Access denied")):
            result = manager.prune_logs()

        assert "An unexpected error occurred while pruning logs: Access denied" in result
