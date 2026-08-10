"""Unit tests for charon.agents.scout.scraping."""

from unittest.mock import patch
import pytest

from charon.agents.scout.scraping import scrape_url_content


@patch("charon.agents.scout.scraping.fetch_url_raw_content")
def test_scrape_url_content_success(mock_fetch):
    """Verify successful scraping returns correctly formatted Markdown."""
    mock_fetch.return_value = {
        "success": True,
        "title": "Example Domain",
        "url": "https://example.com",
        "content": "This is example page text content.",
        "truncated": False,
    }

    result = scrape_url_content("https://example.com")

    mock_fetch.assert_called_once_with(
        "https://example.com", headers=None, max_chars=4000
    )
    assert "### Content from [Example Domain](https://example.com):" in result
    assert "This is example page text content." in result
    assert "[Content Truncated]" not in result


@patch("charon.agents.scout.scraping.fetch_url_raw_content")
def test_scrape_url_content_truncated(mock_fetch):
    """Verify truncation notice is appended when content exceeds length limit."""
    mock_fetch.return_value = {
        "success": True,
        "title": "Large Page",
        "url": "https://example.com/large",
        "content": "A long document excerpt",
        "truncated": True,
    }

    result = scrape_url_content("https://example.com/large", max_chars=100)

    assert "...\n[Content Truncated]" in result


@patch("charon.agents.scout.scraping.fetch_url_raw_content")
def test_scrape_url_content_message_override(mock_fetch):
    """Verify custom response message override is returned directly."""
    mock_fetch.return_value = {
        "success": True,
        "message": "Cached content already processed.",
    }

    result = scrape_url_content("https://example.com")
    assert result == "Cached content already processed."


@patch("charon.agents.scout.scraping.fetch_url_raw_content")
def test_scrape_url_content_failure_with_error(mock_fetch):
    """Verify proper error formatting when retrieval fails with an explicit error message."""
    mock_fetch.return_value = {
        "success": False,
        "error": "HTTP 404 Not Found",
    }

    result = scrape_url_content("https://example.com/404")
    assert result == "Failed to retrieve content from 'https://example.com/404': HTTP 404 Not Found"


@patch("charon.agents.scout.scraping.fetch_url_raw_content")
def test_scrape_url_content_failure_default_error(mock_fetch):
    """Verify default error string when failure response contains no error key."""
    mock_fetch.return_value = {"success": False}

    result = scrape_url_content("https://example.com/fail")
    assert result == "Failed to retrieve content from 'https://example.com/fail': Unknown error"


@patch("charon.agents.scout.scraping.fetch_url_raw_content")
def test_scrape_url_content_with_custom_headers(mock_fetch):
    """Verify custom HTTP headers are propagated through to the fetch tool."""
    mock_fetch.return_value = {"success": True, "content": "Header test"}
    custom_headers = {"User-Agent": "CustomScout/1.0"}

    scrape_url_content("https://example.com", headers=custom_headers)

    mock_fetch.assert_called_once_with(
        "https://example.com", headers=custom_headers, max_chars=4000
    )
