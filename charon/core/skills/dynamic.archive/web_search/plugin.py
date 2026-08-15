"""Plugin entrypoint module for web_search."""

import logging
from typing import Any, Dict

from charon.agents.scout.search import (
    DEFAULT_IGNORED_DOMAINS,
    perform_web_search,
    search_links,
)

logger = logging.getLogger("CHAROND.Skills.WebSearch")


def handle_search_web(params: Dict[str, Any]) -> Dict[str, Any]:
    """Performs web search and returns formatted Markdown content."""
    query = (
        params.get("query")
        or params.get("prompt")
        or params.get("raw_prompt")
    )
    if not query:
        return {"status": "error", "message": "Missing required 'query' parameter."}

    try:
        max_results = int(params.get("max_results", 5))
    except (ValueError, TypeError):
        max_results = 5

    ignored_domains = params.get("ignored_domains") or DEFAULT_IGNORED_DOMAINS

    logger.info(f"Executing web search for query: '{query}' (max_results={max_results})")
    result = perform_web_search(
        query=str(query),
        max_results=max_results,
        ignored_domains=ignored_domains,
    )
    return {"status": "success", "result": result}


def handle_search_links(params: Dict[str, Any]) -> Dict[str, Any]:
    """Performs web search and returns structured link dictionary objects."""
    query = (
        params.get("query")
        or params.get("prompt")
        or params.get("raw_prompt")
    )
    if not query:
        return {"status": "error", "message": "Missing required 'query' parameter."}

    try:
        max_results = int(params.get("max_results", 5))
    except (ValueError, TypeError):
        max_results = 5

    ignored_domains = params.get("ignored_domains") or DEFAULT_IGNORED_DOMAINS

    logger.info(f"Fetching raw search links for query: '{query}'")
    results = search_links(
        query=str(query),
        max_results=max_results,
        ignored_domains=ignored_domains,
    )
    return {"status": "success", "result": results}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router for web_search."""
    if action_name in ("search_web", "web_search"):
        return handle_search_web(params)
    elif action_name == "search_links":
        return handle_search_links(params)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'web_search'."
    )