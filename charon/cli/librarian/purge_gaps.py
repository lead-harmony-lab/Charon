"""
charon/cli/librarian/purge_gaps.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Database maintenance utilities for purging resolved gap records and optimizing state DB.
"""

import logging
from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.CLI.Librarian")


def purge_resolved_gaps() -> int:
    """
    Purges all resolved gap records from the state database and performs a VACUUM.
    Returns the total number of purged records.
    """
    if not STATE_DB_PATH.exists():
        logger.info(f"[MAINTENANCE] Database file not found at {STATE_DB_PATH}. Skipping purge.")
        return 0

    # 1. Execute the purge within standard managed transaction
    with get_connection(STATE_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM skill_gaps WHERE status = 'resolved'")
        purged_count = cursor.rowcount

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
    purge_resolved_gaps()