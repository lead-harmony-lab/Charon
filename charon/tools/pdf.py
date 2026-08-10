"""
charon/tools/pdf.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Reusable tool utilities for PDF parsing, retrieval, and text processing.
"""

import logging
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

logger = logging.getLogger("CHAROND.Tools.PDF")


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks = []
    start = 0
    text_len = len(cleaned)
    step = max(1, chunk_size - overlap)

    while start < text_len:
        end = start + chunk_size
        chunks.append(cleaned[start:end])
        start += step

    return chunks


def sanitize_metadata(metadata: Dict[str, Any] | None) -> Dict[str, Any]:
    if not metadata:
        return {}

    clean_meta = {}
    for k, v in metadata.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            clean_meta[k] = v
        else:
            clean_meta[k] = str(v)
    return clean_meta


def extract_text_from_pdf(pdf_path: Path) -> List[Tuple[int, str]]:
    if not PYPDF_AVAILABLE:
        raise ImportError("The 'pypdf' package is required for PDF operations. Run 'pip install pypdf'.")

    resolved = pdf_path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Cannot process non-existent PDF file: {resolved}")

    reader = PdfReader(resolved)
    page_texts = []

    for page_num, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text()
            if text and text.strip():
                page_texts.append((page_num, text))
        except Exception as err:
            logger.warning(f"Failed to extract text from page {page_num} of {resolved.name}: {err}")

    return page_texts


def download_pdf_bytes(url: str, timeout: int = 25) -> bytes:
    """Downloads PDF binary payload with standard headers, 25s timeout, and curl fallback."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",  # Removed 'br' to prevent unhandled Brotli streams in urllib
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read()
            if b"%PDF" in content[:1024]:
                return content
    except Exception as e:
        logger.warning(f"Standard urllib fetch failed for {url} ({e}); attempting curl fallback...")

    try:
        cmd = [
            "curl",
            "-sSL",
            "--compressed",
            "-A", headers["User-Agent"],
            "-H", f"Accept: {headers['Accept']}",
            "-H", f"Accept-Language: {headers['Accept-Language']}",
            "--max-time", str(timeout),
            url,
        ]
        res = subprocess.run(cmd, capture_output=True, check=True)
        if b"%PDF" in res.stdout[:1024]:
            return res.stdout
    except Exception as e:
        logger.error(f"curl fallback failed for {url}: {e}")

    raise ValueError(f"Unable to retrieve valid PDF payload from {url}.")
