"""test_scout.py — Unit tests for The Scout agent and web tools."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from charon.agents import TheScout, get_agent_class
from charon.agents.scout.agent import VALID_SCOUT_ACTIONS
from charon.tools.web import (
    clean_search_query,
    execute_web_search,
    fetch_url_raw_content,
)


# =============================================================================
# 1. TOOL TESTS: charon/tools/web.py
# =============================================================================

class TestWebTools:
    """Tests for stateless web search and scraping tools."""

    def test_clean_search_query(self):
        """Validates query sanitization logic."""
        assert clean_search_query("   'python tutorials'   ") == "python tutorials"
        assert clean_search_query('"`machine learning`"') == "machine learning"
        assert clean_search_query(">>> clean query <<<") == "clean query <<<"

    @patch("charon.tools.web.DDGS_AVAILABLE", True)
    @patch("charon.tools.web.DDGS")
    def test_execute_web_search_ddg_success(self, mock_ddgs_cls):
        """Tests successful web search using DuckDuckGo with domain filtering."""
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value.__enter__.return_value = mock_ddgs
        mock_ddgs.text.return_value = [
            {"title": "Python Docs", "href": "https://docs.python.org", "body": "Official docs."},
            {"title": "Wiki Page", "href": "https://wikipedia.org/wiki/Python", "body": "Wiki info."},
            {"title": "PyPI", "href": "https://pypi.org", "body": "Package index."},
        ]

        results = execute_web_search("python", max_results=2, ignored_domains=["wikipedia.org"])

        assert len(results) == 2
        assert results[0]["title"] == "Python Docs"
        assert results[1]["title"] == "PyPI"
        # Wikipedia should be filtered out
        assert not any("wikipedia.org" in r["link"] for r in results)

    @patch("charon.tools.web.DDGS_AVAILABLE", True)
    @patch("charon.tools.web.DDGS")
    @patch("charon.tools.web.GOOGLE_AVAILABLE", True)
    @patch("charon.tools.web.google_search")
    def test_execute_web_search_google_fallback(self, mock_google, mock_ddgs_cls):
        """Tests fallback to Google search when DuckDuckGo fails."""
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value.__enter__.return_value = mock_ddgs
        mock_ddgs.text.side_effect = Exception("DDGS rate limit exceeded")

        mock_item = MagicMock()
        mock_item.title = "Google Result"
        mock_item.url = "https://example.com"
        mock_item.description = "Example snippet"
        mock_google.return_value = [mock_item]

        results = execute_web_search("test query", max_results=1)

        assert len(results) == 1
        assert results[0]["title"] == "Google Result"
        assert results[0]["link"] == "https://example.com"

    @patch("charon.tools.web.httpx.Client")
    def test_fetch_url_raw_content_html_cleaning(self, mock_client_cls):
        """Tests HTML parsing, stripping of unwanted tags (script/nav), and title extraction."""
        html_content = """
        <html>
            <head><title>Test Page</title></head>
            <body>
                <nav>Navigation bar</nav>
                <script>var x = 10;</script>
                <h1>Main Content Header</h1>
                <p>This is useful paragraph text.</p>
                <footer>Footer content</footer>
            </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.text = html_content
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_response

        result = fetch_url_raw_content("example.com")

        assert result["success"] is True
        assert result["title"] == "Test Page"
        assert "Main Content Header" in result["content"]
        assert "This is useful paragraph text." in result["content"]
        assert "Navigation bar" not in result["content"]
        assert "var x = 10;" not in result["content"]

    @patch("charon.tools.web.httpx.Client")
    def test_fetch_url_raw_content_truncation(self, mock_client_cls):
        """Tests content truncation when text exceeds max_chars."""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = "A" * 100
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_response

        result = fetch_url_raw_content("https://example.com", max_chars=50)

        assert result["success"] is True
        assert len(result["content"]) == 50
        assert result["truncated"] is True

    @patch("charon.tools.web.httpx.Client")
    def test_fetch_url_raw_content_http_error(self, mock_client_cls):
        """Tests handling of HTTP 404/500 errors."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=mock_response
        )

        result = fetch_url_raw_content("https://example.com/notfound")

        assert result["success"] is False
        assert "HTTP Status 404" in result["error"]


# =============================================================================
# 2. AGENT TESTS: charon/agents/scout/
# =============================================================================

class TestTheScoutAgent:
    """Tests for TheScout agent routing, parameters, and outputs."""

    def test_scout_initialization(self):
        """Tests initialization with default and custom HTTP headers."""
        scout_default = TheScout()
        assert "User-Agent" in scout_default.headers

        scout_custom = TheScout(headers={"User-Agent": "CustomBot/1.0"})
        assert scout_custom.headers["User-Agent"] == "CustomBot/1.0"

    @patch("charon.agents.scout.agent.perform_web_search")
    def test_execute_web_search_action_routing(self, mock_perform_search):
        """Tests routing and normalization of web_search action and aliases."""
        mock_perform_search.return_value = "### Reconnaissance Results..."
        scout = TheScout()

        # Direct action name
        res1 = scout.execute("web_search", {"query": "CAD tools"})
        assert "Reconnaissance Results" in res1

        # Alias action name
        res2 = scout.execute("search", {"query": "CAD tools"})
        assert "Reconnaissance Results" in res2

        assert mock_perform_search.call_count == 2

    @patch("charon.agents.scout.agent.scrape_url_content")
    def test_execute_scrape_page_content_routing(self, mock_scrape_url):
        """Tests routing and normalization of scrape action and aliases."""
        mock_scrape_url.return_value = "### Content from [Example](https://example.com)"
        scout = TheScout()

        # Alias action 'fetch_url'
        res = scout.execute("fetch_url", {"url": "https://example.com", "max_chars": 2000})

        assert "Content from" in res
        mock_scrape_url.assert_called_once_with(
            "https://example.com", max_chars=2000, headers=scout.headers
        )

    def test_execute_scrape_missing_url(self):
        """Ensures scraping without a URL returns a clear error message."""
        scout = TheScout()
        res = scout.execute("scrape_page_content", {})
        assert "Error: A target 'url' parameter is required for scraping." in res

    def test_execute_unknown_action_raises_value_error(self):
        """Ensures an invalid action raises ValueError."""
        scout = TheScout()
        with pytest.raises(ValueError, match="Unknown action"):
            scout.execute("invalid_scout_action", {"query": "something"})

    @patch("charon.agents.scout.agent.search_links")
    def test_search_links_method(self, mock_search_links):
        """Tests the direct search_links helper method."""
        mock_search_links.return_value = [{"title": "Item 1", "link": "https://item1.com", "snippet": "S1"}]
        scout = TheScout()

        hits = scout.search_links("microcontroller", max_results=3)

        assert len(hits) == 1
        assert hits[0]["title"] == "Item 1"
        mock_search_links.assert_called_once_with(
            "microcontroller", max_results=3, ignored_domains=scout.IGNORED_DOMAINS
        )

    def test_execute_payload_validation_fallback(self):
        """Verify fallback payload construction when ScoutPayload.model_validate fails."""
        scout = TheScout()
        with patch("charon.intent.ScoutPayload.model_validate", side_effect=ValueError("Validation failed")):
            with patch.object(scout, "_search_web", return_value="Fallback search ok") as mock_search:
                result = scout.execute("search_web", {"query": "test query"})
                assert result == "Fallback search ok"
                mock_search.assert_called_once_with("test query", max_results=5)

    def test_execute_invalid_numeric_params_fallback(self):
        """Verify fallback to defaults when max_results or max_chars are invalid types."""
        scout = TheScout()

        # Invalid max_results -> defaults to 5
        with patch.object(scout, "_search_web", return_value="ok") as mock_search:
            scout.execute("search_web", {"query": "test", "max_results": "invalid_int"})
            mock_search.assert_called_once_with("test", max_results=5)

        # Invalid max_chars -> defaults to 4000
        with patch.object(scout, "_scrape_url", return_value="ok") as mock_scrape:
            scout.execute("scrape_page_content", {"url": "https://example.com", "max_chars": "invalid_int"})
            mock_scrape.assert_called_once_with("https://example.com", max_chars=4000)

    def test_execute_unhandled_payload_action_raises_value_error(self):
        """Verify error when payload action bypasses validation but is unhandled in execution branches."""
        scout = TheScout()
        mock_payload = MagicMock()
        mock_payload.action = "unsupported_action"

        with patch("charon.intent.ScoutPayload.model_validate", return_value=mock_payload):
            with patch("charon.agents.scout.agent.VALID_SCOUT_ACTIONS", ("unsupported_action",)):
                with pytest.raises(ValueError, match="Unknown action 'unsupported_action'"):
                    scout.execute("unsupported_action", {})


# =============================================================================
# 3. LAZY LOADING INTEGRATION TEST
# =============================================================================

def test_lazy_loading_scout():
    """Verifies that TheScout can be dynamically loaded via agents gateway."""
    agent_cls = get_agent_class("scout")
    assert agent_cls is TheScout

    scout_instance = agent_cls()
    assert isinstance(scout_instance, TheScout)
