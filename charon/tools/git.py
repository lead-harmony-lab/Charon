"""
charon/tools/git.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: tools/git.py
Module: Stateless Git operations for Charon tools and agents.
"""

import logging
import subprocess
from pathlib import Path
from typing import Tuple

logger = logging.getLogger("CHAROND.Tools.Git")


def git_init(target_path: Path) -> Tuple[bool, str]:
    """Initializes a new Git repository at the target path.

    Returns:
        Tuple[bool, str]: (success, status_or_error_message)
    """
    try:
        subprocess.run(
            ["git", "init"],
            cwd=target_path,
            check=True,
            capture_output=True,
        )
        logger.info(f"Git initialized in {target_path}")
        return True, "Initialized successfully"
    except subprocess.CalledProcessError as e:
        err_output = (
            e.stderr.decode().strip()
            if e.stderr
            else str(e)
        )
        logger.error(f"Git initialization failed: {err_output}")
        return False, f"Failed ({err_output})"
    except FileNotFoundError:
        logger.error("Git executable not found on system.")
        return False, "Git executable not found on system"


def git_commit(target_path: Path, commit_message: str) -> Tuple[bool, str, str]:
    """Stages all changes and commits them in the target Git repository.

    Returns:
        Tuple[bool, str, str]: (success, status_code, message_or_error)
        status_code options: "clean", "committed", "failed", "no_git", "no_exe"
    """
    if not (target_path / ".git").exists():
        return (
            False,
            "no_git",
            f"Execution aborted: Target directory {target_path} is not under Git version control.",
        )

    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=target_path,
            check=True,
            capture_output=True,
        )

        if not status.stdout.strip():
            logger.info(f"Workspace {target_path} is clean. No commit necessary.")
            return True, "clean", "Skipped (Workspace is already clean)"

        subprocess.run(
            ["git", "add", "."],
            cwd=target_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=target_path,
            check=True,
            capture_output=True,
        )

        logger.info(f"Workspace committed: {commit_message}")
        return True, "committed", commit_message

    except subprocess.CalledProcessError as e:
        err = (
            (e.stderr.decode().strip() if e.stderr else "")
            or (e.stdout.decode().strip() if e.stdout else "")
            or str(e)
        )
        logger.error(f"Git commit failed in {target_path}: {err}")
        return False, "failed", err
    except FileNotFoundError:
        return False, "no_exe", "Warning: Git executable not found on system."
