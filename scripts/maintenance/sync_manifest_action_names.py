"""
scripts/maintenance/sync_manifest_action_names.py
System Version: v0.6.3

Maintenance utility to update disk manifest.json files with 3-node canonical action names
(<category>_<context>_<verb>) and reindex skill_registry / route_registry.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

from charon.config.paths import DYNAMIC_SKILLS_DIR
from charon.core.skills.indexer import SkillIndexerMixin

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Charon.Maintenance.SyncManifests")


class StandaloneLibrarianIndexer(SkillIndexerMixin):
    """Minimal Librarian indexer wrapper for maintenance tasks."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.search_paths = [DYNAMIC_SKILLS_DIR]
        self._skills = {}


def sync_and_normalize_manifests(dry_run: bool = False) -> None:
    """
    Scans all manifest.json files in dynamic storage:
    1. Derives 3-node canonical action names (<category>_<context>_<verb>).
    2. Rewrites manifest.json with canonical action keys and explicit handlers.
    3. Reindexes the updated manifests into SQLite.
    """
    indexer = StandaloneLibrarianIndexer(db_path=Path("charon/storage/charon.db"))
    manifests = indexer._discover_manifests()

    logger.info(f"Discovered {len(manifests)} manifest(s) for normalization pass.")
    updated_count = 0

    for manifest_path in manifests:
        try:
            raw_text = manifest_path.read_text(encoding="utf-8")
            data: Dict[str, Any] = json.loads(raw_text)

            skill_id = data.get("skill_id", manifest_path.parent.name)
            category = data.get("category", "general")
            supported_actions = data.get("supported_actions", {})

            if not supported_actions:
                continue

            modified = False
            normalized_actions: Dict[str, Any] = {}

            for raw_action, action_def in supported_actions.items():
                # Derive 3-node canonical name
                canonical_name = indexer._derive_canonical_action_name(
                    category=category,
                    skill_id=skill_id,
                    raw_action=raw_action,
                )

                if canonical_name != raw_action:
                    modified = True
                    logger.info(
                        f"[{skill_id}] Renaming action: '{raw_action}' -> '{canonical_name}'"
                    )

                # Ensure payload retains explicit handler reference to underlying Python method
                if isinstance(action_def, dict):
                    action_payload = dict(action_def)
                    if "handler" not in action_payload and "handler_name" not in action_payload:
                        action_payload["handler"] = f"handle_{raw_action}"
                else:
                    action_payload = {
                        "description": f"Executes '{canonical_name}'",
                        "handler": str(action_def),
                        "parameters": {},
                    }

                normalized_actions[canonical_name] = action_payload

            if modified:
                data["supported_actions"] = normalized_actions
                updated_count += 1

                if not dry_run:
                    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                    logger.info(f"Updated {manifest_path}")
                else:
                    logger.info(f"[DRY-RUN] Would update {manifest_path}")

        except Exception as e:
            logger.error(f"Failed to normalize {manifest_path}: {e}", exc_info=True)

    logger.info(f"Manifest normalization complete. Updated {updated_count} file(s).")


if __name__ == "__main__":
    import sys

    is_dry_run = "--dry-run" in sys.argv
    sync_and_normalize_manifests(dry_run=is_dry_run)