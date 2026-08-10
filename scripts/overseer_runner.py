"""
scripts/overseer_runner.py — Standalone script for background systemd maintenance.
Executes non-blocking maintenance tasks managed by TheOverseer.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure root Charon directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from charon.agents.overseer import TheOverseer

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [OVERSEER-CRON] %(message)s",
)
logger = logging.getLogger("Charon.OverseerRunner")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Charon Overseer Maintenance Runner")
    parser.add_argument(
        "--action",
        type=str,
        default="run_full_maintenance",
        choices=[
            "optimize_databases",
            "audit_vector_store",
            "prune_logs_and_cache",
            "prune_orphaned_assets",
            "audit_resource_guard",
            "get_system_health",
            "resolve_skill_gaps",
            "run_full_maintenance",
        ],
        help="Maintenance action to execute.",
    )
    parser.add_argument(
        "--prune-days",
        type=int,
        default=7,
        help="Age threshold in days for pruning stale logs and cache.",
    )
    parser.add_argument(
        "--target-db",
        type=str,
        default=None,
        help="Optional specific database file or directory path.",
    )

    args = parser.parse_args()

    logger.info(f"Initiating background maintenance task: '{args.action}'")
    overseer = TheOverseer()

    params = {
        "prune_days": args.prune_days,
        "target_db": args.target_db,
    }

    try:
        res = overseer.execute(args.action, params)
        if asyncio.iscoroutine(res):
            res = await res
        logger.info("Maintenance run completed successfully.")
        logger.info(f"Result summary:\n{res}")
    except Exception as e:
        logger.error(f"Overseer background task failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())