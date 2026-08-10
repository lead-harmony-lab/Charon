"""Tests for PDF download, chunking, sanitization, and text extraction tools."""

import importlib
import subprocess
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from charon.tools import pdf


# ==========================================
# Tests for pypdf Import Fallback (Lines 13-14)
# ==========================================

def test_pypdf_import_error_handling():
    """Covers lines 13-14 where pypdf is missing during module import."""
    with patch.dict("sys.modules", {"pypdf": None}):
        importlib.reload(pdf)
        assert pdf.PYPDF_AVAILABLE is False

    # Restore module state
    importlib.reload(pdf)


# ==========================================
# Tests for chunk_text
# ==========================================

def test_chunk_text_empty():
    assert pdf.chunk_text("") == []
    assert pdf.chunk_text("    \n  ") == []


def test_chunk_text_short():
    text = "Short text"
    assert pdf.chunk_text(text, chunk_size=100) == [text]


def test_chunk_text_sliding_window():
    text = "abcdefghij"  # len 10
    # size=4, overlap=2 -> step = 2
    # chunks expected:
    # 0:4 -> abcd
    # 2:6 -> cdef
    # 4:8 -> efgh
    # 6:10 -> ghij
    # 8:12 -> ij
    chunks = pdf.chunk_text(text, chunk_size=4, overlap=2)
    assert chunks == ["abcd", "cdef", "efgh", "ghij", "ij"]


# ==========================================
# Tests for sanitize_metadata
# ==========================================

def test_sanitize_metadata_empty_or_none():
    assert pdf.sanitize_metadata(None) == {}
    assert pdf.sanitize_metadata({}) == {}


def test_sanitize_metadata_removes_none():
    assert pdf.sanitize_metadata({"valid": 123, "invalid": None}) == {"valid": 123}


def test_sanitize_metadata_keeps_primitives():
    metadata = {
        "string": "test",
        "integer": 42,
        "float": 3.14,
        "boolean": True,
    }
    assert pdf.sanitize_metadata(metadata) == metadata


def test_sanitize_metadata_stringifies_complex_types():
    metadata = {
        "list": [1, 2, 3],
        "dict": {"nested": "value"},
    }
    sanitized = pdf.sanitize_metadata(metadata)
    assert sanitized["list"] == "[1, 2, 3]"
    assert sanitized["dict"] == "{'nested': 'value'}"


# ==========================================
# Tests for extract_text_from_pdf
# ==========================================

def test_extract_text_missing_pypdf():
    with patch("charon.tools.pdf.PYPDF_AVAILABLE", False):
        with pytest.raises(ImportError, match="The 'pypdf' package is required"):
            pdf.extract_text_from_pdf(Path("dummy.pdf"))


def test_extract_text_file_not_found(tmp_path):
    missing_file = tmp_path / "does_not_exist.pdf"
    with patch("charon.tools.pdf.PYPDF_AVAILABLE", True):
        with pytest.raises(
            FileNotFoundError, match="Cannot process non-existent PDF file"
        ):
            pdf.extract_text_from_pdf(missing_file)


@patch("charon.tools.pdf.PdfReader")
def test_extract_text_success(mock_pdf_reader, tmp_path):
    # Setup dummy file
    dummy_pdf = tmp_path / "dummy.pdf"
    dummy_pdf.touch()

    # Mock pages
    mock_page_1 = MagicMock()
    mock_page_1.extract_text.return_value = "Page 1 content"
    mock_page_2 = MagicMock()
    mock_page_2.extract_text.return_value = "Page 2 content"

    mock_reader_instance = MagicMock()
    mock_reader_instance.pages = [mock_page_1, mock_page_2]
    mock_pdf_reader.return_value = mock_reader_instance

    with patch("charon.tools.pdf.PYPDF_AVAILABLE", True):
        results = pdf.extract_text_from_pdf(dummy_pdf)

    assert results == [(1, "Page 1 content"), (2, "Page 2 content")]


@patch("charon.tools.pdf.PdfReader")
def test_extract_text_empty_and_blank_pages(mock_pdf_reader, tmp_path):
    """Covers branch 79->76 where empty, blank, or None page text skips insertion."""
    dummy_pdf = tmp_path / "dummy.pdf"
    dummy_pdf.touch()

    mock_page_empty = MagicMock()
    mock_page_empty.extract_text.return_value = ""  # Triggers branch 79->76

    mock_page_none = MagicMock()
    mock_page_none.extract_text.return_value = None  # Triggers branch 79->76

    mock_page_whitespace = MagicMock()
    mock_page_whitespace.extract_text.return_value = "   "  # Triggers branch 79->76

    mock_page_valid = MagicMock()
    mock_page_valid.extract_text.return_value = "Page 4 Content"

    mock_reader_instance = MagicMock()
    mock_reader_instance.pages = [
        mock_page_empty,
        mock_page_none,
        mock_page_whitespace,
        mock_page_valid,
    ]
    mock_pdf_reader.return_value = mock_reader_instance

    with patch("charon.tools.pdf.PYPDF_AVAILABLE", True):
        results = pdf.extract_text_from_pdf(dummy_pdf)

    assert results == [(4, "Page 4 Content")]


@patch("charon.tools.pdf.PdfReader")
def test_extract_text_handles_page_exception(mock_pdf_reader, tmp_path):
    dummy_pdf = tmp_path / "dummy.pdf"
    dummy_pdf.touch()

    mock_page_1 = MagicMock()
    mock_page_1.extract_text.side_effect = Exception("Corrupt page")
    mock_page_2 = MagicMock()
    mock_page_2.extract_text.return_value = "Page 2 OK"

    mock_reader_instance = MagicMock()
    mock_reader_instance.pages = [mock_page_1, mock_page_2]
    mock_pdf_reader.return_value = mock_reader_instance

    with patch("charon.tools.pdf.PYPDF_AVAILABLE", True):
        results = pdf.extract_text_from_pdf(dummy_pdf)

    # Page 1 fails gracefully, Page 2 succeeds
    assert results == [(2, "Page 2 OK")]


# ==========================================
# Tests for download_pdf_bytes
# ==========================================

@patch("charon.tools.pdf.urllib.request.urlopen")
def test_download_pdf_urllib_success(mock_urlopen):
    mock_response = MagicMock()
    mock_response.read.return_value = b"%PDF-1.4\n...fake pdf content..."
    mock_urlopen.return_value.__enter__.return_value = mock_response

    result = pdf.download_pdf_bytes("http://example.com/test.pdf")
    assert result.startswith(b"%PDF")
    mock_urlopen.assert_called_once()


@patch("charon.tools.pdf.subprocess.run")
@patch("charon.tools.pdf.urllib.request.urlopen")
def test_download_pdf_urllib_fails_curl_succeeds(mock_urlopen, mock_subprocess):
    # Force urllib to fail
    mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

    # Mock curl success
    mock_subprocess_result = MagicMock()
    mock_subprocess_result.stdout = b"%PDF-1.5\n...curl fetched content..."
    mock_subprocess.return_value = mock_subprocess_result

    result = pdf.download_pdf_bytes("http://example.com/test.pdf")

    assert result.startswith(b"%PDF")
    mock_urlopen.assert_called_once()
    mock_subprocess.assert_called_once()

    # Ensure curl was called with the target URL
    assert "http://example.com/test.pdf" in mock_subprocess.call_args[0][0]


@patch("charon.tools.pdf.subprocess.run")
@patch("charon.tools.pdf.urllib.request.urlopen")
def test_download_pdf_both_fail(mock_urlopen, mock_subprocess):
    mock_urlopen.side_effect = Exception("urllib error")
    mock_subprocess.side_effect = subprocess.CalledProcessError(1, "curl")

    with pytest.raises(
        ValueError, match="Unable to retrieve valid PDF payload"
    ):
        pdf.download_pdf_bytes("http://example.com/fail.pdf")


@patch("charon.tools.pdf.subprocess.run")
@patch("charon.tools.pdf.urllib.request.urlopen")
def test_download_pdf_invalid_content(mock_urlopen, mock_subprocess):
    # Both methods succeed network-wise, but return HTML instead of PDF
    html_payload = b"<!DOCTYPE html><html><body>Not a PDF</body></html>"

    mock_response = MagicMock()
    mock_response.read.return_value = html_payload
    mock_urlopen.return_value.__enter__.return_value = mock_response

    mock_subprocess_result = MagicMock()
    mock_subprocess_result.stdout = html_payload
    mock_subprocess.return_value = mock_subprocess_result

    with pytest.raises(
        ValueError, match="Unable to retrieve valid PDF payload"
    ):
        pdf.download_pdf_bytes("http://example.com/fake.pdf")
