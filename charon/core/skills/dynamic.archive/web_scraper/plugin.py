"""Plugin entrypoint module for web_scraper."""

import logging
from typing import Any, Dict

from charon.agents.scout.scraping import scrape_url_content

logger = logging.getLogger("CHAROND.Skills.WebScraper")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def handle_scrape_page_content(params: Dict[str, Any]) -> Dict[str, Any]:
    """Scrapes content from a specified URL and formats as Markdown."""
    url = params.get("url") or params.get("link")
    if not url or not str(url).strip():
        return {
            "status": "error",
            "message": "Missing required 'url' parameter for page content scraping.",
        }

    try:
        max_chars = int(params.get("max_chars", 4000))
    except (ValueError, TypeError):
        max_chars = 4000

    headers = params.get("headers")
    if not headers or not isinstance(headers, dict):
        headers = {"User-Agent": DEFAULT_USER_AGENT}

    logger.info(f"Scraping web page content from URL: {url}")
    result = scrape_url_content(
        url=str(url).strip(),
        max_chars=max_chars,
        headers=headers,
    )
    return {"status": "success", "result": result}


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Main dispatch router for web_scraper."""
    if action_name in ("scrape_page_content", "scrape", "fetch_url", "scrape_url"):
        return handle_scrape_page_content(params)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'web_scraper'."
    )