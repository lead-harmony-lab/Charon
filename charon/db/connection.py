"""
charon/db/connection.py
System Version: v0.1.0 | File Revision: 1.3.0

Module: Centralized SQLite connection manager.
Enforces foreign key constraints, optimizes concurrency via WAL mode, standardizes timeouts,
guarantees explicit transactional commits/rollbacks, and ensures connection cleanup.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Union


@contextmanager
def get_connection(
    db_path: Union[str, Path],
    timeout: float = 30.0,
    read_only: bool = False,
    row_factory: bool = True,
) -> Generator[sqlite3.Connection, None, None]:
    """Creates, yields, and safely closes a strict, configured SQLite connection."""
    # 1. Sanitize input path (strip protocol if raw URI string was passed)
    raw_path = str(db_path)
    if raw_path.startswith("file:"):
        raw_path = raw_path.replace("file://", "").replace("file:", "").split("?")[0]

    path = Path(raw_path).expanduser().resolve()

    # 2. Validate that target path is not a directory
    if path.is_dir():
        raise IsADirectoryError(
            f"Cannot open SQLite connection: '{path}' is a directory, not a database file."
        )

    # 3. Guarantee parent directory exists
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    # 4. Standardize RFC 3986 compliant file URI formatting
    db_uri = path.as_uri()
    if read_only:
        db_uri = f"{db_uri}?mode=ro"

    conn = sqlite3.connect(db_uri, timeout=timeout, uri=True)

    # 5. ENFORCE STRICT RELATIONAL INTEGRITY
    conn.execute("PRAGMA foreign_keys = ON;")

    # 6. ENHANCE CONCURRENCY
    if not read_only:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")

    # 7. DICTIONARY & KEY-BASED ROW ACCESS
    if row_factory:
        conn.row_factory = sqlite3.Row

    try:
        yield conn
        # Automatically commit write transactions on clean context exit
        if not read_only:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()