"""
charon/db/chroma_connection.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Centralized ChromaDB vector store client manager.
Enforces vector database directory paths, prevents file collision with relational
databases, and manages cached PersistentClient instances across execution loops.
"""

import logging
from pathlib import Path
from typing import Dict, Union

import chromadb
from chromadb.config import Settings

logger = logging.getLogger("Charon.DB.Vector")

# Global client cache indexed by canonical path to avoid redundant disk locks
_CLIENT_CACHE: Dict[Path, chromadb.PersistentClient] = {}


def get_vector_client(
        db_dir: Union[str, Path],
        anonymized_telemetry: bool = False,
        allow_reset: bool = False,
) -> chromadb.PersistentClient:
    """
    Creates or retrieves a cached persistent ChromaDB client bound to a directory.

    Args:
        db_dir: Path to the target directory for vector persistence.
        anonymized_telemetry: Disable or enable ChromaDB anonymous usage metrics.
        allow_reset: Allow system database resetting (keep False for safety in prod).

    Raises:
        NotADirectoryError: If target path points to a file (e.g. SQLite DB file).
    """
    path = Path(db_dir).expanduser().resolve()

    # 1. ENFORCE VECTOR DB DIRECTORY GUARDRAIL
    if path.exists() and path.is_file():
        raise NotADirectoryError(
            f"Cannot initialize ChromaDB client at file path: '{path}'. "
            f"ChromaDB requires a persistence directory (e.g., CHROMA_DB_DIR), "
            f"not a relational database file (e.g., STATE_DB_PATH)."
        )

    # 2. GUARANTEE DIRECTORY STRUCTURE EXISTS
    if not path.exists():
        logger.info(f"Creating vector store directory structure at: {path}")
        path.mkdir(parents=True, exist_ok=True)

    # 3. RETURN CACHED CLIENT OR INITIALIZE NEW INSTANCE
    if path not in _CLIENT_CACHE:
        logger.debug(f"Initializing new PersistentClient connection at '{path}'")
        _CLIENT_CACHE[path] = chromadb.PersistentClient(
            path=str(path),
            settings=Settings(
                anonymized_telemetry=anonymized_telemetry,
                allow_reset=allow_reset,
                is_persistent=True,
            ),
        )

    return _CLIENT_CACHE[path]


def close_all_vector_clients() -> None:
    """Flushes and clears all cached vector store connections (useful during daemon shutdown)."""
    global _CLIENT_CACHE
    _CLIENT_CACHE.clear()
    logger.info("Cleared all active ChromaDB client references.")