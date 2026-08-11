"""
charon/cli/librarian/purge_gaps.py
System Version: v0.2.0 | File Revision: 1.2.0

Module: Database maintenance utilities for purging resolved gap records and optimizing state DB.
Aligned with Schema V3.
"""

import logging
import sys
from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("charon.cli.librarian.purge_gaps")


def purge_resolved_gaps() -> int:
    """
    Purges all resolved gap records from the state database and performs a VACUUM.
    Returns the total number of purged records.
    """
    if not STATE_DB_PATH.exists():
        logger.info(f"[MAINTENANCE] Database file not found at {STATE_DB_PATH}. Skipping purge.")
        return 0

    # 1. Execute the purge within a standard managed transaction
    with get_connection(STATE_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM skill_gaps WHERE LOWER(status) = 'resolved'")
        purged_count = cursor.rowcount
        conn.commit()

    # 2. Run VACUUM in autocommit mode if any records were purged
    if purged_count > 0:
        try:
            with get_connection(STATE_DB_PATH) as conn:
                conn.isolation_level = None  # Enable autocommit for VACUUM
                conn.execute("VACUUM")
            logger.info(f"[MAINTENANCE] Purged {purged_count} resolved gaps and vacuumed database.")
        except Exception as e:
            logger.warning(f"[MAINTENANCE] Purged {purged_count} records, but VACUUM failed: {e}")
    else:
        logger.info("[MAINTENANCE] No resolved gaps found to purge.")

    return purged_count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(0 if purge_resolved_gaps() >= 0 else 1)