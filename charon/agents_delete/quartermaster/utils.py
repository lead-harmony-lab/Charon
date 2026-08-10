"""
charon/agents/quartermaster/utils.py
System Version: v0.1.0 | File Revision: 1.5.0

Module: Helper utilities for MPN sanitization, URL validation, database connections,
and payload parameter extraction.
"""

import logging
import re
import sqlite3
import urllib.parse
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Union

from charon.db.connection import get_connection
from charon.intent import DynamicActionPayload

logger = logging.getLogger("charon.agents.quartermaster.utils")


def _extract_param_dict(
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]]
) -> Dict[str, Any]:
    """Helper utility to extract parameter dictionary from DynamicActionPayload or standard dict."""
    if isinstance(payload, DynamicActionPayload):
        return payload.params or {}
    elif isinstance(payload, dict):
        return payload
    return {}


@contextmanager
def get_db_connection(
    db_path: Union[str, Path],
    read_only: bool = False,
) -> Generator[sqlite3.Connection, None, None]:
    """Establishes a managed connection to the PartVault SQLite database via the central DAL."""
    with get_connection(db_path, timeout=10.0, read_only=read_only) as conn:
        yield conn


def clean_mpn(raw_mpn: str) -> str:
    """Strips conversational context, prompt verbs, and generic engineering nouns to isolate true MPNs."""
    if not raw_mpn or not isinstance(raw_mpn, str):
        return "UNKNOWN_PART"

    # Strip conversational noise and descriptive engineering nouns
    cleaned = re.sub(
        r"(?i)\b(download|fetch|get|find|search|datasheet|for|a|the|please|check|part|what|is|pinout|pdf|lookup|microcontroller|component|ic|chip|module|board|sensor|regulator|amplifier|transistor)\b",
        " ",
        raw_mpn,
    )

    tokens = re.findall(r"\b[A-Za-z0-9\-\_]{3,}\b", cleaned)
    if not tokens:
        fallback = re.sub(r"[^A-Za-z0-9\-\_]", "", raw_mpn).upper()
        return fallback if fallback else "UNKNOWN_PART"

    # Prioritize tokens containing both digits and letters (classic alphanumeric MPNs)
    mpn_candidates = [
        t for t in tokens if re.search(r"\d", t) and re.search(r"[A-Za-z]", t)
    ]
    if mpn_candidates:
        return max(mpn_candidates, key=len).upper()

    return max(tokens, key=len).upper()


def is_valid_mirror_candidate(url: str, safe_mpn: str) -> bool:
    """Validates candidate URL domain and file extension."""
    if not url or not safe_mpn:
        return False

    url_lower = url.lower()

    blocked_domains = [
        "youtube.com",
        "youtu.be",
        "wikipedia.org",
        "grokipedia.com",
        "yandex.com",
        "google.com",
        "bing.com",
        "duckduckgo.com",
    ]
    if any(domain in url_lower for domain in blocked_domains):
        logger.debug(f"Rejecting candidate URL (blocked domain): {url}")
        return False

    # Reject non-PDF documents or media formats
    parsed_path = urllib.parse.urlparse(url_lower).path
    if parsed_path.endswith(
        (".html", ".htm", ".php", ".asp", ".jpg", ".png", ".zip", ".exe")
    ):
        logger.debug(f"Rejecting candidate URL (non-PDF extension): {url}")
        return False

    return True