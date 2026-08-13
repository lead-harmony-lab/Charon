#!/usr/bin/env python3
"""
scripts/save/run_skill_reindex.py

Auto-discovers the concrete class inheriting from SkillIndexerMixin,
instantiates it, and executes the reindex + stale purge pipeline.
"""

import importlib
import logging
import pkgutil
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("charon.scripts.reindex")


def auto_discover_indexer_instance():
    """Imports all modules under charon.core.skills to find the class inheriting SkillIndexerMixin."""
    try:
        import charon.core.skills as skills_pkg
        from charon.core.skills.indexer import SkillIndexerMixin
    except ImportError as e:
        logger.error(f"❌ Core import failed: {e}")
        sys.exit(1)

    # Walk and import submodules to ensure subclasses register
    for _, module_name, _ in pkgutil.walk_packages(
        skills_pkg.__path__, skills_pkg.__name__ + "."
    ):
        try:
            importlib.import_module(module_name)
        except Exception:
            pass

    subclasses = SkillIndexerMixin.__subclasses__()

    if not subclasses:
        # Fallback inspection if direct subclassing isn't registered via __subclasses__
        logger.error("❌ No subclasses of SkillIndexerMixin found in charon.core.skills.")
        sys.exit(1)

    target_cls = subclasses[0]
    logger.info(f" Discovered indexer class: '{target_cls.__module__}.{target_cls.__name__}'")
    return target_cls()


def main() -> None:
    print("\n" + "=" * 75)
    print(" 🚀 CHARON LIBRARIAN - SKILL REINDEX & STALE PURGE PIPELINE")
    print("=" * 75)

    try:
        indexer_instance = auto_discover_indexer_instance()

        logger.info("Starting reindexing pipeline (purge_stale=True)...")
        indexer_instance.reindex_skills(auto_promote=False, purge_stale=True)

        print("\n" + "=" * 75)
        logger.info("🎉 Skill reindexing and stale mapping purge complete!")
        print("=" * 75 + "\n")

    except Exception as e:
        logger.error(f"❌ Reindexing pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()