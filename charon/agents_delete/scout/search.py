"""
charon/agents/scout/search.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Web search domain handlers for The Scout.
"""

import logging
from typing import Dict, List, Optional

from charon.tools.web import clean_search_query, execute_web_search

logger = logging.getLogger("Charon.Scout.Search")

DEFAULT_IGNORED_DOMAINS = [
    "wikipedia.org",
    "yahoo.com",
    "statista.com",
    "pitchbook.com",
    "financecharts.com",
    "expandedramblings.com",
    "bing.com",
    "google.com",
]


def search_links(
    query: str,
    max_results: int = 5,
    ignored_domains: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """Returns programmatic search result dictionaries."""
    ignored = ignored_domains if ignored_domains is not None else DEFAULT_IGNORED_DOMAINS
    return execute_web_search(query, max_results=max_results, ignored_domains=ignored)


# charon/agents/scout/search.py

def perform_web_search(
    query: str,
    max_results: int = 5,
    ignored_domains: Optional[List[str]] = None,
) -> str:
    """Performs a web search and returns formatted Markdown for LLM output."""
    cleaned_query = clean_search_query(query)
    if not cleaned_query:
        return "Error: No search query provided."

    results = search_links(
        cleaned_query, max_results=max_results, ignored_domains=ignored_domains
    )

    if not results:
        return f"No search results returned for query: '{cleaned_query}'"

    formatted = [f"### Reconnaissance Results for '{cleaned_query}':\n"]
    for idx, item in enumerate(results, 1):
        # Use boolean `or` to handle empty strings as well as missing keys
        title = item.get("title") or "Untitled"
        link = item.get("link") or "#"
        snippet = item.get("snippet") or "No summary available."
        formatted.append(f"**{idx}. [{title}]({link})**\n{snippet}\n")

    return "\n".join(formatted)