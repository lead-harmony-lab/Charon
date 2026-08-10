"""Unit tests for Charon logging configuration and file output pipelines."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import pytest

from charon.config import logging as charon_logging
from charon.config import paths


@pytest.fixture
def temp_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirects LOGS_DIR and target log files to an isolated pytest temp directory."""
    test_logs_dir = tmp_path / "logs"
    test_main_log = test_logs_dir / "charond.log"
    test_error_log = test_logs_dir / "charond.error.log"

    # Patch paths configuration module
    monkeypatch.setattr(paths, "LOGS_DIR", test_logs_dir)
    monkeypatch.setattr(paths, "MAIN_LOG_FILE", test_main_log)
    monkeypatch.setattr(paths, "ERROR_LOG_FILE", test_error_log)

    # Patch path constants if imported directly into logging module
    monkeypatch.setattr(charon_logging, "LOGS_DIR", test_logs_dir)
    monkeypatch.setattr(charon_logging, "MAIN_LOG_FILE", test_main_log)
    monkeypatch.setattr(charon_logging, "ERROR_LOG_FILE", test_error_log)

    yield test_logs_dir, test_main_log, test_error_log

    # Reset root and CHAROND loggers after test run to prevent handler pollution
    logging.getLogger("CHAROND").handlers.clear()
    logging.getLogger().handlers.clear()


def test_ensure_ecosystem_directories_creates_logs_dir(temp_log_dir):
    """Verifies setup_logging triggers directory creation if missing."""
    test_logs_dir, _, _ = temp_log_dir

    assert not test_logs_dir.exists()
    charon_logging.setup_logging()
    assert test_logs_dir.exists()
    assert test_logs_dir.is_dir()


def test_setup_logging_attaches_handlers(temp_log_dir):
    """Verifies that handlers (StreamHandler, RotatingFileHandlers) are correctly configured."""
    charon_logging.setup_logging()

    # Fallback to root logger if handlers are bound globally
    charon_logger = logging.getLogger("CHAROND")
    root_logger = logging.getLogger()
    handlers = charon_logger.handlers or root_logger.handlers

    assert len(handlers) > 0, "No log handlers were attached during setup_logging()"

    # Check for stdout StreamHandler and RotatingFileHandler instances
    has_stream_handler = any(type(h) is logging.StreamHandler for h in handlers)
    has_rotating_handler = any(isinstance(h, RotatingFileHandler) for h in handlers)

    assert has_stream_handler, "Console StreamHandler missing from logging configuration"
    assert has_rotating_handler, "RotatingFileHandler missing from logging configuration"


def test_setup_logging_clears_existing_handlers(temp_log_dir):
    """Verifies setup_logging clears pre-existing handlers (covers both branches)."""

    # 1. Strip pytest's default LogCaptureHandler to force hasHandlers() == False
    logging.getLogger().handlers.clear()

    # Now hasHandlers() is False -> execution jumps from line 26 to 30
    charon_logging.setup_logging()
    assert len(logging.getLogger().handlers) == 3

    # 2. Call again. Now hasHandlers() is True -> execution goes 26 -> 27 -> 30
    charon_logging.setup_logging()
    assert len(logging.getLogger().handlers) == 3


def test_main_and_error_log_emission(temp_log_dir):
    """Tests that INFO logs go to main log, and ERROR logs propagate to both main and error logs."""
    _, test_main_log, test_error_log = temp_log_dir

    charon_logging.setup_logging()
    logger = logging.getLogger("CHAROND.TestModule")

    info_msg = "Routine operation heartbeat."
    error_msg = "Critical system fault detected!"

    logger.info(info_msg)
    logger.error(error_msg)

    # Flush all active handlers across logger hierarchy
    for logger_obj in (logging.getLogger("CHAROND"), logging.getLogger()):
        for handler in logger_obj.handlers:
            handler.flush()

    # Verify main log contents
    main_content = test_main_log.read_text()
    assert info_msg in main_content
    assert error_msg in main_content

    # Verify error log contents (INFO level should NOT be present)
    error_content = test_error_log.read_text()
    assert info_msg not in error_content
    assert error_msg in error_content


def test_sublogger_inheritance(temp_log_dir):
    """Ensures child loggers (e.g. CHAROND.Cleaner) correctly inherit daemon handlers."""
    _, test_main_log, _ = temp_log_dir

    charon_logging.setup_logging()
    cleaner_logger = logging.getLogger("CHAROND.Cleaner")

    sweep_msg = "Swept deprecated step files from CAD directory."
    cleaner_logger.info(sweep_msg)

    for logger_obj in (logging.getLogger("CHAROND"), logging.getLogger()):
        for handler in logger_obj.handlers:
            handler.flush()

    main_content = test_main_log.read_text()
    assert sweep_msg in main_content
    assert "CHAROND.Cleaner" in main_content


