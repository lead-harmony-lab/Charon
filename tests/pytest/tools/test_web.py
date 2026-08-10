"""tests/tools/test_web.py — Complete test suite for charon.tools.web targeting 100% coverage."""

import importlib
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest

import charon.tools.web as web_module
from charon.tools.web import (
    clean_search_query,
    execute_web_search,
    fetch_url_raw_content,
)


# ============================================================================
# 1. Import Fallback Tests (Top-level module import branches)
# ============================================================================

def test_import_fallbacks_ddgs_and_google_missing():
    """Tests module behavior when ddgs, duckduckgo_search, and googlesearch are missing."""
    with patch.dict(
        "sys.modules",
        {
            "ddgs": None,
            "duckduckgo_search": None,
            "googlesearch": None,
        },
    ):
        reloaded = importlib.reload(web_module)
        assert reloaded.DDGS_AVAILABLE is False
        assert reloaded.DDGS is None
        assert reloaded.GOOGLE_AVAILABLE is False
        assert reloaded.google_search is None

    # Reload again to restore normal module state for remaining tests
    importlib.reload(web_module)


def test_import_fallback_duckduckgo_search_secondary():
    """Tests import fallback to duckduckgo_search when ddgs is missing."""
    mock_ddgs_class = MagicMock()
    with patch.dict(
        "sys.modules",
        {
            "ddgs": None,
            "duckduckgo_search": MagicMock(DDGS=mock_ddgs_class),
            "googlesearch": None,
        },
    ):
        reloaded = importlib.reload(web_module)
        assert reloaded.DDGS_AVAILABLE is True
        assert reloaded.DDGS is mock_ddgs_class

    # Reload again to restore normal module state
    importlib.reload(web_module)


# ============================================================================
# 2. Query Cleaner Unit Tests
# ============================================================================

def test_clean_search_query():
    assert clean_search_query("  `'\" python tutorials  ") == "python tutorials"
    assert clean_search_query("") == ""
    assert clean_search_query("   ") == ""


# ============================================================================
# 3. execute_web_search Tests
# ============================================================================

def test_execute_web_search_empty_query():
    assert execute_web_search("   ") == []


def test_execute_web_search_invalid_max_results():
    with patch("charon.tools.web.DDGS") as mock_ddgs_cls:
        mock_instance = MagicMock()
        mock_instance.text.return_value = []
        mock_ddgs_cls.return_value.__enter__.return_value = mock_instance

        # Test invalid string max_results defaults to 5
        res = execute_web_search("python", max_results="invalid")  # type: ignore
        assert res == []


def test_execute_web_search_ddgs_fewer_results_than_max():
    """Tests natural termination of DDGS results loop when hits are fewer than max_results."""
    raw_hits = [
        {"link": "https://example.com/single", "title": "Single", "body": "Snippet"},
    ]

    with patch("charon.tools.web.DDGS") as mock_ddgs_cls:
        mock_instance = MagicMock()
        mock_instance.text.return_value = raw_hits
        mock_ddgs_cls.return_value.__enter__.return_value = mock_instance

        results = execute_web_search("test query", max_results=10)
        assert len(results) == 1
        assert results[0]["link"] == "https://example.com/single"


def test_execute_web_search_ddgs_success_and_domain_filtering():
    raw_hits = [
        {"href": "https://ignore-me.com/page", "title": "Ignored", "body": "Skip"},
        {"link": "https://example.com/a", "title": "Valid 1", "body": "Snippet 1"},
        {"href": "https://example.com/b", "body": "Snippet 2"},  # Missing title
    ]

    with patch("charon.tools.web.DDGS") as mock_ddgs_cls:
        mock_instance = MagicMock()
        mock_instance.text.return_value = raw_hits
        mock_ddgs_cls.return_value.__enter__.return_value = mock_instance

        results = execute_web_search(
            query="test query",
            max_results=2,
            ignored_domains=["ignore-me.com"],
        )

        assert len(results) == 2
        assert results[0] == {
            "title": "Valid 1",
            "link": "https://example.com/a",
            "snippet": "Snippet 1",
        }
        assert results[1] == {
            "title": "Untitled",
            "link": "https://example.com/b",
            "snippet": "Snippet 2",
        }


def test_execute_web_search_ddgs_fallback_to_google_on_exception():
    """Tests break branch in Google search loop when safe_max threshold is hit."""
    class GoogleHit:
        def __init__(self, url, title, description):
            self.url = url
            self.title = title
            self.description = description

    g_hits = [
        GoogleHit("https://ignored.com", "Ignored", "Desc"),
        GoogleHit("https://google-result.com", "Google Title", "Google Desc"),
    ]

    with (
        patch("charon.tools.web.DDGS", side_effect=Exception("DDGS connection error")),
        patch("charon.tools.web.google_search", return_value=g_hits),
        patch("charon.tools.web.GOOGLE_AVAILABLE", True),
    ):
        results = execute_web_search(
            "test query",
            max_results=1,
            ignored_domains=["ignored.com"],
        )

        assert len(results) == 1
        assert results[0] == {
            "title": "Google Title",
            "link": "https://google-result.com",
            "snippet": "Google Desc",
        }


def test_execute_web_search_google_fewer_results_than_max():
    """Tests Google loop when hits are fewer than max_results (evaluates False on branch 109->97)."""
    class GoogleHit:
        def __init__(self, url, title, description):
            self.url = url
            self.title = title
            self.description = description

    g_hits = [
        GoogleHit("https://google-result.com/1", "Title 1", "Desc 1"),
    ]

    with (
        patch("charon.tools.web.DDGS", side_effect=Exception("DDGS connection error")),
        patch("charon.tools.web.google_search", return_value=g_hits),
        patch("charon.tools.web.GOOGLE_AVAILABLE", True),
    ):
        results = execute_web_search("test query", max_results=5)
        assert len(results) == 1
        assert results[0]["link"] == "https://google-result.com/1"


def test_execute_web_search_google_string_results_fallback():
    """Tests Google search fallback handling raw string URLs (testing getattr defaults)."""
    g_hits = ["https://plain-url.com"]

    with (
        patch("charon.tools.web.DDGS_AVAILABLE", False),
        patch("charon.tools.web.google_search", return_value=g_hits),
        patch("charon.tools.web.GOOGLE_AVAILABLE", True),
    ):
        results = execute_web_search("test query", max_results=5)
        assert len(results) == 1
        assert results[0] == {
            "title": "Google Result",
            "link": "https://plain-url.com",
            "snippet": "",
        }


def test_execute_web_search_google_exception_handled():
    with (
        patch("charon.tools.web.DDGS_AVAILABLE", False),
        patch("charon.tools.web.GOOGLE_AVAILABLE", True),
        patch(
            "charon.tools.web.google_search",
            side_effect=Exception("Google rate limit"),
        ),
    ):
        results = execute_web_search("test query")
        assert results == []


# ============================================================================
# 4. fetch_url_raw_content Tests
# ============================================================================

def test_fetch_url_raw_content_prepends_https():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.headers = {"content-type": "text/plain"}
        mock_res.text = "Hello World"
        mock_client.get.return_value = mock_res
        mock_client_cls.return_value.__enter__.return_value = mock_client

        res = fetch_url_raw_content("example.com")
        assert res["url"] == "https://example.com"
        assert res["content"] == "Hello World"
        assert res["title"] == "Raw Content"


def test_fetch_url_raw_content_json_plain_text():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.headers = {"content-type": "application/json"}
        mock_res.text = '{"status":    "ok"}'
        mock_client.get.return_value = mock_res
        mock_client_cls.return_value.__enter__.return_value = mock_client

        res = fetch_url_raw_content("https://api.example.com/data")
        assert res["content"] == '{"status": "ok"}'
        assert res["title"] == "Raw Content"


def test_fetch_url_raw_content_html_no_title():
    html_content = "<html><body><p>Some text content here.</p></body></html>"
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.headers = {"content-type": "text/html"}
        mock_res.text = html_content
        mock_client.get.return_value = mock_res
        mock_client_cls.return_value.__enter__.return_value = mock_client

        res = fetch_url_raw_content("https://example.com")
        assert res["title"] == "No Title"
        assert res["content"] == "Some text content here."


def test_fetch_url_raw_content_empty_content():
    html_content = "<html><head><title>Empty</title></head><body><script>var x = 1;</script></body></html>"
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.headers = {"content-type": "text/html"}
        mock_res.text = html_content
        mock_client.get.return_value = mock_res
        mock_client_cls.return_value.__enter__.return_value = mock_client

        res = fetch_url_raw_content("https://example.com")
        assert res["success"] is True
        assert res["content"] == ""
        assert "contained no extractable text" in res["message"]


def test_fetch_url_raw_content_truncation():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.headers = {"content-type": "text/plain"}
        mock_res.text = "A" * 100
        mock_client.get.return_value = mock_res
        mock_client_cls.return_value.__enter__.return_value = mock_client

        res = fetch_url_raw_content("https://example.com", max_chars=10)
        assert res["content"] == "A" * 10
        assert res["truncated"] is True


def test_fetch_url_raw_content_http_status_error():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)
        mock_client.get.side_effect = error
        mock_client_cls.return_value.__enter__.return_value = mock_client

        res = fetch_url_raw_content("https://example.com/404")
        assert res["success"] is False
        assert res["error"] == "HTTP Status 404"


def test_fetch_url_raw_content_network_error():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.RequestError("DNS resolution failed")
        mock_client_cls.return_value.__enter__.return_value = mock_client

        res = fetch_url_raw_content("https://bad-domain.com")
        assert res["success"] is False
        assert res["error"] == "Network connection error."


def test_fetch_url_raw_content_generic_exception():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.get.side_effect = ValueError("Unexpected internal error")
        mock_client_cls.return_value.__enter__.return_value = mock_client

        res = fetch_url_raw_content("https://example.com")
        assert res["success"] is False
        assert res["error"] == "Unexpected internal error"
