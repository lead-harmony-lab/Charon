"""
charon/agents/scout/scraping.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Content scraping domain handlers for The Scout.
"""

import logging
from typing import Dict, Optional

from charon.tools.web import fetch_url_raw_content

logger = logging.getLogger("Charon.Scout.Scraping")


def scrape_url_content(
    url: str,
    max_chars: int = 4000,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    """Fetches a URL and returns formatted Markdown content or error messages."""
    result = fetch_url_raw_content(url, headers=headers, max_chars=max_chars)

    if not result.get("success"):
        error_msg = result.get("error", "Unknown error")
        return f"Failed to retrieve content from '{url}': {error_msg}"

    if result.get("message"):
        return result["message"]

    title = result.get("title", "No Title")
    target_url = result.get("url", url)
    content = result.get("content", "")
    if result.get("truncated"):
        content += "...\n[Content Truncated]"

    return f"### Content from [{title}]({target_url}):\n\n{content}"