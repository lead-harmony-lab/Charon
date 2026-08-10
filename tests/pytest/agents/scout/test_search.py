"""Unit tests for charon.agents.scout.search."""

from unittest.mock import patch
import pytest

from charon.agents.scout.search import (
    DEFAULT_IGNORED_DOMAINS,
    perform_web_search,
    search_links,
)


@patch("charon.agents.scout.search.execute_web_search")
def test_search_links_defaults(mock_execute):
    """Verify search_links passes default ignored domains when none are supplied."""
    mock_execute.return_value = [{"title": "Test", "link": "https://test.com", "snippet": "Text"}]

    results = search_links("python docs", max_results=3)

    mock_execute.assert_called_once_with(
        "python docs", max_results=3, ignored_domains=DEFAULT_IGNORED_DOMAINS
    )
    assert len(results) == 1


@patch("charon.agents.scout.search.execute_web_search")
def test_search_links_custom_ignored_domains(mock_execute):
    """Verify search_links respects user-supplied ignored domain lists."""
    custom_ignored = ["spam.com"]
    search_links("microcontrollers", max_results=5, ignored_domains=custom_ignored)

    mock_execute.assert_called_once_with(
        "microcontrollers", max_results=5, ignored_domains=custom_ignored
    )


@patch("charon.agents.scout.search.clean_search_query")
def test_perform_web_search_empty_cleaned_query(mock_clean):
    """Verify error message is returned when query cleaning results in an empty string."""
    mock_clean.return_value = ""

    result = perform_web_search("   ")
    assert result == "Error: No search query provided."


@patch("charon.agents.scout.search.search_links")
@patch("charon.agents.scout.search.clean_search_query")
def test_perform_web_search_no_results(mock_clean, mock_links):
    """Verify message when search execution returns no link results."""
    mock_clean.return_value = "obscure search topic"
    mock_links.return_value = []

    result = perform_web_search("obscure search topic")
    assert result == "No search results returned for query: 'obscure search topic'"


@patch("charon.agents.scout.search.search_links")
@patch("charon.agents.scout.search.clean_search_query")
def test_perform_web_search_formatting(mock_clean, mock_links):
    """Verify successful web search results are correctly formatted into Markdown."""
    mock_clean.return_value = "raspberry pi pico datasheet"
    mock_links.return_value = [
        {
            "title": "Raspberry Pi Pico RP2040",
            "link": "https://raspberrypi.com/pico",
            "snippet": "Microcontroller board datasheet.",
        },
        {
            "title": "",  # Test fallback title
            "link": "",   # Test fallback link
            "snippet": None,  # Test fallback snippet
        },
    ]

    result = perform_web_search("raspberry pi pico datasheet", max_results=2)

    assert "### Reconnaissance Results for 'raspberry pi pico datasheet':" in result
    assert "**1. [Raspberry Pi Pico RP2040](https://raspberrypi.com/pico)**" in result
    assert "Microcontroller board datasheet." in result
    assert "**2. [Untitled](#)**" in result
    assert "No summary available." in result
