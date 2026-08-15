"""
charon/cli/librarian/purge_gaps.py
System Version: v0.2.0 | File Revision: 1.3.0

Module: Database maintenance utilities for purging resolved gap records and optimizing state DB.
Aligned with Schema V3.
"""

import logging
import sys

from charon.cli.librarian.db import purge_resolved_gaps_db, vacuum_db

logger = logging.getLogger("charon.cli.librarian.purge_gaps")


def purge_resolved_gaps() -> int:
    """
    Purges all resolved gap records from the state database and performs a VACUUM.
    Returns the total number of purged records.
    """
    purged_count = purge_resolved_gaps_db()

    if purged_count > 0:
        if vacuum_db():
            logger.info(
                f"[MAINTENANCE] Purged {purged_count} resolved gaps and vacuumed database."
            )
        else:
            logger.warning(
                f"[MAINTENANCE] Purged {purged_count} records, but VACUUM failed."
            )
    else:
        logger.info("[MAINTENANCE] No resolved gaps found to purge.")

    return purged_count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(0 if purge_resolved_gaps() >= 0 else 1)