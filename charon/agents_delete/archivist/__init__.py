"""
charon/agents/archivist/__init__.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Re-exports TheArchivist class and utility functions for seamless backward compatibility.
"""

from charon.config.paths import ensure_ecosystem_directories
from charon.agents.archivist.agent import TheArchivist
from charon.tools.pdf import chunk_text as _chunk_text
from charon.agents.archivist.utils import _get_payload_val

__all__ = [
    "TheArchivist",
    "_chunk_text",
    "_get_payload_val",
    "ensure_ecosystem_directories",
]