"""
tests/artifact_manager.py — Git-aware artifact versioning and isolation manager.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shutil
from typing import Any, Dict

from charon.core.version import get_git_revision

logger = logging.getLogger("Charon.Tests.ArtifactManager")

ARTIFACT_SCHEMA_VERSION = "1.0.0"
DEFAULT_ARTIFACT_DIR = Path(".charon_test_artifacts")


class ArtifactVersionManager:
    """Manages versioned, isolated directory spaces for test artifacts with auto-cleanup."""

    def __init__(
        self,
        base_dir: Path = DEFAULT_ARTIFACT_DIR,
        schema_version: str = ARTIFACT_SCHEMA_VERSION,
        auto_purge_stale: bool = True,
    ):
        self.base_dir = base_dir.resolve()
        self.schema_version = schema_version
        self.version_info = get_git_revision()
        self.git_sha = self.version_info["git_sha"]

        self.version_dir = self.base_dir / f"v{self.schema_version}" / self.git_sha

        if auto_purge_stale:
            self.purge_stale_versions()

        self._ensure_ignore_files()
        self.version_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_ignore_files(self) -> None:
        """Ensures VCS and parsers ignore test artifact directories."""
        self.base_dir.mkdir(parents=True, exist_ok=True)

        gitignore_path = self.base_dir / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text("*\n!.gitignore\n!.opencodeignore\n", encoding="utf-8")

        opencodeignore_path = self.base_dir / ".opencodeignore"
        if not opencodeignore_path.exists():
            opencodeignore_path.write_text("*\n", encoding="utf-8")

    def purge_stale_versions(self) -> None:
        """Purges artifact folders from outdated schema versions or stale commit runs."""
        if not self.base_dir.exists():
            return

        current_v_dir = f"v{self.schema_version}"
        for item in self.base_dir.iterdir():
            if item.is_dir():
                if item.name != current_v_dir:
                    logger.info(f"Purging outdated schema version directory: {item}")
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    for sha_dir in item.iterdir():
                        if sha_dir.is_dir() and sha_dir.name != self.git_sha:
                            logger.info(f"Purging stale run artifacts from commit: {sha_dir.name}")
                            shutil.rmtree(sha_dir, ignore_errors=True)

    def get_test_run_path(self, test_name: str) -> Path:
        """Returns an isolated workspace directory dedicated to a specific test case."""
        run_path = self.version_dir / test_name
        run_path.mkdir(parents=True, exist_ok=True)
        return run_path

    def write_json_artifact(
        self, test_name: str, filename: str, data: Dict[str, Any]
    ) -> Path:
        """Writes a JSON artifact stamped with system version, schema, and revision metadata."""
        target_dir = self.get_test_run_path(test_name)
        target_file = target_dir / filename

        payload = {
            "_charon_metadata": {
                "system_version": self.version_info["version"],
                "schema_version": self.schema_version,
                "git_sha": self.git_sha,
                "git_branch": self.version_info["git_branch"],
                "is_dirty": self.version_info["is_dirty"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "artifact_file": filename,
            },
            "data": data,
        }

        target_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target_file

    def wipe_all(self) -> None:
        """Completely purges all test artifacts."""
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir, ignore_errors=True)
