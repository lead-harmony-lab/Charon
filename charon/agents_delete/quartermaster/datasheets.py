"""
charon/agents/quartermaster/datasheets.py
System Version: v0.1.0 | File Revision: 2.3.0

Module: Datasheet acquisition, verification, local storage, and PartVault DB registration.
Strictly handles physical files and SQLite records; vector indexing is delegated via Blackboard.
"""

import hashlib
import logging
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.agents.quartermaster.utils import (
    _extract_param_dict,
    clean_mpn,
    get_db_connection,
    is_valid_mirror_candidate,
)
from charon.intent import DynamicActionPayload
from charon.tools.pdf import download_pdf_bytes

logger = logging.getLogger("CHAROND.Quartermaster.Datasheets")


def _is_valid_pdf(file_path: Path) -> bool:
    """Verifies that a path exists, is non-empty, and begins with valid %PDF- magic bytes."""
    if not file_path or not file_path.exists() or not file_path.is_file():
        return False
    if file_path.stat().st_size < 100:
        return False
    try:
        with open(file_path, "rb") as f:
            header = f.read(5)
        return header.startswith(b"%PDF-")
    except Exception:
        return False


def compute_sha256(file_path: Path) -> Optional[str]:
    """Computes the SHA-256 checksum of a local file."""
    if not _is_valid_pdf(file_path):
        return None
    try:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.warning(f"Failed to calculate SHA256 for {file_path}: {e}")
        return None


def _find_local_datasheet(
    db_path: Path,
    datasheet_dir: Path,
    safe_mpn: str,
    category: Optional[str] = None,
) -> Optional[Path]:
    """Searches for an existing valid local PDF datasheet across PartVault records and disk."""
    # 1. Check SQLite database
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT d.file_path 
                FROM datasheets d
                JOIN parts p ON d.part_id = p.id
                WHERE p.mpn = ? OR p.mpn LIKE ?
                """,
                (safe_mpn, f"%{safe_mpn}%"),
            )
            row = cursor.fetchone()
            if row:
                candidate_rel = row["file_path"] if hasattr(row, "keys") else row[0]
                candidate_path = datasheet_dir / candidate_rel
                if _is_valid_pdf(candidate_path):
                    return candidate_path
    except Exception as db_err:
        logger.debug(f"SQLite datasheet lookup failed for '{safe_mpn}': {db_err}")

    # 2. Check category or General directory
    if category:
        candidate_cat = datasheet_dir / category / f"{safe_mpn}.pdf"
        if _is_valid_pdf(candidate_cat):
            return candidate_cat

    candidate_gen = datasheet_dir / "General" / f"{safe_mpn}.pdf"
    if _is_valid_pdf(candidate_gen):
        return candidate_gen

    # 3. Recursive directory search
    if datasheet_dir.exists():
        clean_target = re.sub(r"[^a-zA-Z0-9]", "", safe_mpn).lower()
        if clean_target:
            for pdf_file in datasheet_dir.rglob("*.pdf"):
                clean_stem = re.sub(r"[^a-zA-Z0-9]", "", pdf_file.stem).lower()
                if clean_target in clean_stem or clean_stem in clean_target:
                    if _is_valid_pdf(pdf_file):
                        logger.info(f"Found matching local PDF in PartVault: {pdf_file}")
                        return pdf_file

    return None


def search_pdf_mirrors(scout_agent: Any, safe_mpn: str) -> List[str]:
    """Searches for downloadable datasheet links via web scraping / search tools."""
    query = f"{safe_mpn} datasheet filetype:pdf"
    candidates: List[str] = []

    if scout_agent:
        try:
            search_hits = scout_agent.search_links(query, max_results=8)
            for hit in search_hits:
                link = hit.get("link", "")
                if link and link not in candidates:
                    if is_valid_mirror_candidate(link, safe_mpn):
                        candidates.append(link)
        except Exception as e:
            logger.warning(f"TheScout mirror search failed: {e}")

    if not candidates:
        ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            req = urllib.request.Request(ddg_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                raw_uddgs = re.findall(r'uddg=([^&"\']+)', html)
                for raw in raw_uddgs:
                    decoded_url = urllib.parse.unquote(raw)
                    if decoded_url not in candidates:
                        if is_valid_mirror_candidate(decoded_url, safe_mpn):
                            candidates.append(decoded_url)
        except Exception as e:
            logger.error(f"Direct DDG mirror discovery fallback failed: {e}")

    return candidates


def _sync_partvault_db(
    db_path: Path,
    safe_mpn: str,
    rel_path: str,
    url: str,
    category: str,
    sha256_hash: Optional[str] = None,
) -> int:
    """Inserts/updates `parts` and `datasheets` in SQLite. Returns the `datasheet_id`."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Resolve or create parent part
        cursor.execute("SELECT id FROM parts WHERE mpn = ?", (safe_mpn,))
        row = cursor.fetchone()

        if row:
            part_id = row["id"] if hasattr(row, "keys") else row[0]
        else:
            cursor.execute(
                """
                INSERT INTO parts (mpn, category, description)
                VALUES (?, ?, ?)
                """,
                (
                    safe_mpn,
                    category or "General",
                    f"Auto-created entry for {safe_mpn}",
                ),
            )
            part_id = cursor.lastrowid

        # 2. Upsert into datasheets
        cursor.execute(
            """
            INSERT INTO datasheets (part_id, file_path, source_url, sha256_hash)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                part_id = excluded.part_id,
                source_url = COALESCE(excluded.source_url, datasheets.source_url),
                sha256_hash = COALESCE(excluded.sha256_hash, datasheets.sha256_hash)
            RETURNING id;
            """,
            (part_id, rel_path, url or "Local Import", sha256_hash),
        )
        fetched = cursor.fetchone()
        datasheet_id = fetched["id"] if hasattr(fetched, "keys") else fetched[0]
        conn.commit()
        return datasheet_id


def fetch_datasheet(
    db_path: Path,
    datasheet_dir: Path,
    scout_agent: Any,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    raw_prompt: str = "",
) -> Dict[str, Any]:
    """
    Acquires datasheet PDF, registers it in PartVault SQLite, and returns execution status dict.
    The returned dictionary contains everything required for the Blackboard state.
    """
    p_dict = _extract_param_dict(payload)

    raw_part = (
        p_dict.get("part_number")
        or p_dict.get("mpn")
        or p_dict.get("query")
        or getattr(payload, "part_number", None)
        or getattr(payload, "mpn", None)
        or getattr(payload, "query", None)
        or raw_prompt.strip()
    )
    url = p_dict.get("url") or getattr(payload, "url", None)
    category = p_dict.get("category") or getattr(payload, "category", None)

    if not raw_part and not url:
        return {"success": False, "error": "A 'part_number' or 'url' is required."}

    if not raw_part and url:
        raw_part = Path(url.split("?")[0]).stem

    safe_mpn = clean_mpn(str(raw_part))

    # Query category if available
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT category FROM parts WHERE mpn = ?", (safe_mpn,))
            existing = cursor.fetchone()
            if existing:
                category = existing["category"] if hasattr(existing, "keys") else existing[0]
    except Exception as db_err:
        logger.debug(f"Could not query existing category for {safe_mpn}: {db_err}")

    # 1. Check local storage first
    local_pdf = _find_local_datasheet(db_path, datasheet_dir, safe_mpn, category)

    if local_pdf:
        full_pdf_path = local_pdf
        logger.info(f"Resolved valid local datasheet: {full_pdf_path}")
    else:
        category = category or "General"
        rel_path = f"{category}/{safe_mpn}.pdf"
        full_pdf_path = datasheet_dir / rel_path
        full_pdf_path.parent.mkdir(parents=True, exist_ok=True)

        download_success = False

        if url and is_valid_mirror_candidate(url, safe_mpn):
            try:
                content = download_pdf_bytes(url, timeout=25)
                if content and content.startswith(b"%PDF-"):
                    full_pdf_path.write_bytes(content)
                    download_success = True
            except Exception as e:
                logger.warning(f"Primary download URL failed ({url}): {e}")

        if not download_success:
            mirror_urls = search_pdf_mirrors(scout_agent, safe_mpn)
            for candidate in mirror_urls:
                if candidate == url:
                    continue
                try:
                    content = download_pdf_bytes(candidate, timeout=25)
                    if content and content.startswith(b"%PDF-"):
                        full_pdf_path.write_bytes(content)
                        download_success = True
                        url = candidate
                        break
                except Exception as mirror_err:
                    logger.warning(f"Mirror attempt failed ({candidate}): {mirror_err}")

        if not full_pdf_path.exists() or not _is_valid_pdf(full_pdf_path):
            return {
                "success": False,
                "error": f"Failed to retrieve valid PDF for {safe_mpn}.",
            }

    # Compute relative path for PartVault
    try:
        rel_path = str(full_pdf_path.relative_to(datasheet_dir))
    except ValueError:
        rel_path = full_pdf_path.name

    sha256_hash = compute_sha256(full_pdf_path)

    # 2. SQLite Sync
    try:
        ds_id = _sync_partvault_db(
            db_path=db_path,
            safe_mpn=safe_mpn,
            rel_path=rel_path,
            url=url or "",
            category=category or "General",
            sha256_hash=sha256_hash,
        )
    except Exception as e:
        logger.error(f"PartVault DB registration failed: {e}")
        return {"success": False, "error": f"Database registration failed: {str(e)}"}

    return {
        "success": True,
        "mpn": safe_mpn,
        "category": category or "General",
        "file_path": str(full_pdf_path.resolve()),
        "rel_path": rel_path,
        "sha256_hash": sha256_hash,
        "source_url": url or "Local Import",
        "datasheet_id": ds_id,
        "message": (
            f"✅ Datasheet registered for {safe_mpn}:\n"
            f"  • File Path: {full_pdf_path.resolve()}\n"
            f"  • SHA-256: {sha256_hash[:16] if sha256_hash else 'N/A'}...\n"
            f"  • Rel Path: {rel_path}"
        ),
    }