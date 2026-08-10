"""
charon/core/version.py
System Version: v0.3.3 | File Revision: 2.0.0

Module: Runtime Git metadata extraction and SemVer context adhering to the
Janitorial Working Anchor.
"""

import logging
from pathlib import Path
import subprocess
from typing import Any, Dict

try:
    from charon.__version__ import __version__
except ImportError:
    __version__ = "0.3.3"

logger = logging.getLogger("Charon.Core.Version")

SUBPROCESS_TIMEOUT_SECONDS = 3


def get_git_revision(repo_root: Path | None = None) -> Dict[str, Any]:
    """
    Defensively extracts Git revision metadata (commit SHA, branch, dirty status).
    Handles non-git environments, timeouts, and missing subprocess binaries cleanly.
    """
    if repo_root is None:
        # charon/core/version.py -> parents[2] resolves to repository root
        repo_root = Path(__file__).resolve().parents[2]

    metadata: Dict[str, Any] = {
        "version": __version__,
        "git_sha": "uncommitted_workspace",
        "git_branch": "unknown",
        "is_dirty": False,
    }

    git_dir = repo_root / ".git"
    if not git_dir.exists():
        logger.debug(f"[VERSION] No .git directory found at '{repo_root}'. Skipping git rev-parse.")
        return metadata

    try:
        # 1. Get short commit hash
        sha_res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        metadata["git_sha"] = sha_res.stdout.strip()

        # 2. Get current branch name
        branch_res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        metadata["git_branch"] = branch_res.stdout.strip()

        # 3. Check workspace dirty status
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        metadata["is_dirty"] = len(status_res.stdout.strip()) > 0

    except FileNotFoundError:
        logger.warning("[VERSION] 'git' executable not found in system PATH.")
    except subprocess.TimeoutExpired:
        logger.warning(f"[VERSION] Git metadata extraction timed out (> {SUBPROCESS_TIMEOUT_SECONDS}s).")
    except subprocess.CalledProcessError as e:
        logger.debug(f"[VERSION] Git command failed: {e}")
    except Exception as e:
        logger.warning(f"[VERSION] Unexpected error extracting Git revision: {e}")

    return metadata


def get_version_string() -> str:
    """
    Returns a canonical runtime version string (e.g., 'v0.3.3-ga21c3ef (dirty)').
    Normalizes leading version prefixes to avoid duplicate 'v' formatting.
    """
    meta = get_git_revision()
    clean_version = str(meta["version"]).lstrip("vV")
    version_str = f"v{clean_version}"

    if meta["git_sha"] != "uncommitted_workspace":
        version_str += f"-g{meta['git_sha']}"
    if meta["is_dirty"]:
        version_str += " (dirty)"

    return version_str