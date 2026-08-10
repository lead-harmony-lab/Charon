"""
charon/tools/web.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Pure, domain-agnostic web search and HTTP scraping tools.
"""

import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

# Defensive package detection for DuckDuckGo search
try:
    from ddgs import DDGS

    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS

        DDGS_AVAILABLE = True
    except ImportError:
        DDGS = None
        DDGS_AVAILABLE = False

# Defensive package detection for Google search
try:
    from googlesearch import search as google_search

    GOOGLE_AVAILABLE = True
except ImportError:
    google_search = None
    GOOGLE_AVAILABLE = False

logger = logging.getLogger("Charon.Tools.Web")


def clean_search_query(query: str) -> str:
    """Strips common LLM quote prefixes, Markdown tags, or formatting artifacts."""
    cleaned = str(query).strip()
    return re.sub(r"^[`'\">]+|[`'\">]+$", "", cleaned).strip()


def execute_web_search(
    query: str,
    max_results: int = 5,
    ignored_domains: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """Performs web search via DuckDuckGo with fallback to Google.

    Returns raw dictionaries: [{'title': str, 'link': str, 'snippet': str}].
    """
    cleaned_query = clean_search_query(query)
    if not cleaned_query:
        return []

    try:
        safe_max = max(1, int(max_results))
    except (ValueError, TypeError):
        safe_max = 5

    ignored = [d.lower() for d in (ignored_domains or [])]
    results: List[Dict[str, str]] = []

    # Primary Search Engine: DuckDuckGo / DDGS
    if DDGS_AVAILABLE and DDGS is not None:
        try:
            with DDGS() as ddgs:
                ddg_hits = list(ddgs.text(cleaned_query, max_results=safe_max * 2))
                for item in ddg_hits:
                    link = str(item.get("href") or item.get("link", "#"))
                    if any(domain in link.lower() for domain in ignored):
                        continue

                    results.append(
                        {
                            "title": str(item.get("title", "Untitled")).strip(),
                            "link": link,
                            "snippet": str(item.get("body", "")).strip(),
                        }
                    )
                    if len(results) >= safe_max:
                        break
        except Exception as e:
            logger.warning(
                f"DDGS search failed for '{cleaned_query}': {e}. Falling back to Google..."
            )

    # Secondary Fallback: Google Search
    if not results and GOOGLE_AVAILABLE and google_search is not None:
        try:
            g_hits = list(
                google_search(
                    cleaned_query,
                    num_results=safe_max * 2,
                    advanced=True,
                )
            )
            for item in g_hits:
                if isinstance(item, str):
                    link = item
                    title = "Google Result"
                    snippet = ""
                else:
                    link = str(getattr(item, "url", getattr(item, "link", "#")))
                    raw_title = getattr(item, "title", None)
                    title = raw_title if isinstance(raw_title, str) else "Google Result"
                    raw_snippet = getattr(item, "description", getattr(item, "snippet", None))
                    snippet = raw_snippet if isinstance(raw_snippet, str) else ""

                if any(domain in link.lower() for domain in ignored):
                    continue

                results.append(
                    {
                        "title": str(title).strip(),
                        "link": link,
                        "snippet": str(snippet).strip(),
                    }
                )
                if len(results) >= safe_max:
                    break
        except Exception as e:
            logger.error(f"Google search fallback failed: {e}")

    return results


def fetch_url_raw_content(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    max_chars: int = 4000,
) -> Dict[str, Any]:
    """Fetches a URL via HTTP, extracts clean text from HTML/JSON/Text, and returns a result dict."""
    target_url = str(url).strip()
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    default_headers = headers or {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        with httpx.Client(
            timeout=12.0, follow_redirects=True, headers=default_headers
        ) as client:
            res = client.get(target_url)
            res.raise_for_status()

        content_type = res.headers.get("content-type", "").lower()

        if "text/plain" in content_type or "application/json" in content_type:
            clean_text = re.sub(r"\s+", " ", res.text).strip()
            page_title = "Raw Content"
        else:
            soup = BeautifulSoup(res.text, "html.parser")
            page_title = (
                soup.title.string.strip()
                if soup.title and soup.title.string
                else "No Title"
            )

            for element in soup(
                [
                    "head",
                    "title",
                    "script",
                    "style",
                    "nav",
                    "footer",
                    "header",
                    "noscript",
                    "svg",
                    "iframe",
                    "form",
                    "aside",
                    "button",
                ]
            ):
                element.decompose()

            raw_text = soup.get_text(separator=" ", strip=True)
            clean_text = re.sub(r"\s+", " ", raw_text).strip()

        if not clean_text:
            return {
                "success": True,
                "url": target_url,
                "title": page_title,
                "content": "",
                "message": f"Page at '{target_url}' was fetched successfully but contained no extractable text.",
            }

        truncated = False
        if len(clean_text) > max_chars:
            clean_text = clean_text[:max_chars]
            truncated = True

        return {
            "success": True,
            "url": target_url,
            "title": page_title,
            "content": clean_text,
            "truncated": truncated,
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP status error for {target_url}: {e}")
        return {
            "success": False,
            "url": target_url,
            "error": f"HTTP Status {e.response.status_code}",
        }
    except httpx.RequestError as e:
        logger.error(f"Network error for {target_url}: {e}")
        return {
            "success": False,
            "url": target_url,
            "error": "Network connection error.",
        }
    except Exception as e:
        logger.error(f"Scrape error for {target_url}: {e}")
        return {
            "success": False,
            "url": target_url,
            "error": str(e),
        }
