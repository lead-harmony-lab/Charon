"""Tests for Quartermaster datasheet download, mirror discovery, and indexing handlers."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from charon.agents.quartermaster.datasheets import fetch_datasheet, search_pdf_mirrors
from charon.intent import QuartermasterPayload
from charon.db.connection import get_connection


@pytest.fixture
def mock_db(tmp_path: Path) -> Path:
    """Creates a temporary SQLite database with the Quartermaster schema."""
    db_path = tmp_path / "quartermaster.db"
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mpn TEXT UNIQUE,
            category TEXT,
            description TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE datasheets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER,
            file_path TEXT UNIQUE,
            source_url TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def datasheet_dir(tmp_path: Path) -> Path:
    """Creates a temporary directory for storing downloaded datasheet PDFs."""
    path = tmp_path / "datasheets"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestSearchPdfMirrors:
    """Tests for mirror candidate discovery via TheScout and DDG fallbacks."""

    def test_search_pdf_mirrors_scout_success(self):
        """Tests Scout search including empty links, duplicates, and candidate filtering."""
        mock_scout = MagicMock()
        mock_scout.search_links.return_value = [
            {"link": ""},  # Empty link branch
            {"link": "https://example.com/NE555.pdf"},  # Valid candidate
            {"link": "https://example.com/NE555.pdf"},  # Duplicate filtering branch
            {"link": "https://youtube.com/watch?v=123"},  # Invalid candidate filtering branch
        ]

        results = search_pdf_mirrors(mock_scout, "NE555")

        assert results == ["https://example.com/NE555.pdf"]
        mock_scout.search_links.assert_called_once_with(
            "NE555 datasheet filetype:pdf", max_results=8
        )

    def test_search_pdf_mirrors_scout_exception_falls_back_to_ddg(self):
        """Tests fallback to DDG scraping when Scout raises an exception, exercising duplicate and invalid candidate branches."""
        mock_scout = MagicMock()
        mock_scout.search_links.side_effect = RuntimeError("Scout offline")

        # HTML includes valid link, duplicate link, and invalid youtube link
        html_response = (
            b'a href="uddg=https%3A%2F%2Fmirror.com%2FNE555.pdf&amp;" '
            b'a href="uddg=https%3A%2F%2Fmirror.com%2FNE555.pdf&amp;" '
            b'a href="uddg=https%3A%2F%2Fyoutube.com%2Fwatch%3Fv%3DNE555&amp;"'
        )

        mock_resp = MagicMock()
        mock_resp.read.return_value = html_response
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = search_pdf_mirrors(mock_scout, "NE555")

        assert results == ["https://mirror.com/NE555.pdf"]

    def test_search_pdf_mirrors_ddg_exception(self):
        """Tests graceful handling when direct DDG discovery fails."""
        with patch(
            "urllib.request.urlopen", side_effect=Exception("Network error")
        ):
            results = search_pdf_mirrors(None, "NE555")

        assert results == []


class TestFetchDatasheet:
    """Tests for the full datasheet retrieval, storage, and indexing pipeline."""

    def test_fetch_datasheet_missing_part_and_url(
        self, mock_db: Path, datasheet_dir: Path
    ):
        payload = QuartermasterPayload(action="fetch_datasheet")
        result = fetch_datasheet(
            db_path=mock_db,
            datasheet_dir=datasheet_dir,
            scout_agent=None,
            payload=payload,
            raw_prompt="",
        )
        assert "Error: A 'part_number' or 'url' is required" in result

    def test_fetch_datasheet_url_only_derives_part_name(
        self, mock_db: Path, datasheet_dir: Path
    ):
        payload = QuartermasterPayload(
            action="fetch_datasheet",
            url="https://example.com/files/LM317.pdf?v=2",
        )

        with patch(
            "charon.agents.quartermaster.datasheets.download_pdf_bytes",
            return_value=b"%PDF-1.4 dummy content",
        ), patch(
            "charon.agents.TheArchivist"
        ) as mock_archivist_cls:
            mock_archivist_cls.return_value.index_pdf_datasheet.return_value = 5

            result = fetch_datasheet(
                db_path=mock_db,
                datasheet_dir=datasheet_dir,
                scout_agent=None,
                payload=payload,
            )

        assert "✅ Datasheet pipeline complete for LM317" in result
        assert (datasheet_dir / "General" / "LM317.pdf").exists()

    def test_fetch_datasheet_already_exists_on_disk(
        self, mock_db: Path, datasheet_dir: Path
    ):
        """Covers pre-existing local file path branch (skips download loop)."""
        pdf_file = datasheet_dir / "General" / "NE555.pdf"
        pdf_file.parent.mkdir(parents=True, exist_ok=True)
        pdf_file.write_bytes(b"%PDF existing file")

        payload = QuartermasterPayload(
            action="fetch_datasheet",
            part_number="NE555",
            url="https://example.com/NE555.pdf",
        )

        with patch("charon.agents.TheArchivist") as mock_archivist_cls:
            mock_archivist_cls.return_value.index_pdf_datasheet.return_value = 2

            result = fetch_datasheet(
                db_path=mock_db,
                datasheet_dir=datasheet_dir,
                scout_agent=None,
                payload=payload,
            )

        assert "✅ Datasheet pipeline complete for NE555" in result

    def test_fetch_datasheet_primary_url_invalid_candidate(
        self, mock_db: Path, datasheet_dir: Path
    ):
        """Covers branch 95->104 where primary URL fails is_valid_mirror_candidate validation."""
        payload = QuartermasterPayload(
            action="fetch_datasheet",
            part_number="NE555",
            url="https://youtube.com/watch?v=invalid_candidate",
        )

        with patch(
            "charon.agents.quartermaster.datasheets.search_pdf_mirrors",
            return_value=["https://mirror.com/NE555.pdf"],
        ), patch(
            "charon.agents.quartermaster.datasheets.download_pdf_bytes",
            return_value=b"%PDF mirror content",
        ), patch(
            "charon.agents.TheArchivist"
        ) as mock_archivist_cls:
            mock_archivist_cls.return_value.index_pdf_datasheet.return_value = 1

            result = fetch_datasheet(
                db_path=mock_db,
                datasheet_dir=datasheet_dir,
                scout_agent=None,
                payload=payload,
            )

        assert "✅ Datasheet pipeline complete for NE555" in result
        assert "Source URL: https://mirror.com/NE555.pdf" in result

    def test_fetch_datasheet_primary_fails_mirror_succeeds(
        self, mock_db: Path, datasheet_dir: Path
    ):
        """Exercises scout_agent presence and matching primary URL skip branches."""
        mock_scout = MagicMock()
        payload = QuartermasterPayload(
            action="fetch_datasheet",
            part_number="NE555",
            url="https://primary.com/NE555.pdf",
            category="ICs",
        )

        def mock_download(url, timeout=8):
            if "primary.com" in url:
                raise RuntimeError("404 Not Found")
            return b"%PDF mirror bytes"

        with patch(
            "charon.agents.quartermaster.datasheets.download_pdf_bytes",
            side_effect=mock_download,
        ), patch(
            "charon.agents.quartermaster.datasheets.search_pdf_mirrors",
            return_value=[
                "https://primary.com/NE555.pdf",  # Must be skipped (matches primary URL)
                "https://mirror.com/NE555.pdf",
            ],
        ), patch(
            "charon.agents.TheArchivist"
        ) as mock_archivist_cls:
            mock_archivist_cls.return_value.index_pdf_datasheet.return_value = 4

            result = fetch_datasheet(
                db_path=mock_db,
                datasheet_dir=datasheet_dir,
                scout_agent=mock_scout,
                payload=payload,
            )

        assert "✅ Datasheet pipeline complete for NE555" in result
        assert "Source URL: https://mirror.com/NE555.pdf" in result

    def test_fetch_datasheet_mirror_download_exception_handled(
        self, mock_db: Path, datasheet_dir: Path
    ):
        """Exercises scout_agent=None and mirror download exception branches."""
        payload = QuartermasterPayload(
            action="fetch_datasheet",
            part_number="NE555",
        )

        def mock_download(url, timeout=8):
            if "broken.com" in url:
                raise RuntimeError("Connection reset")
            return b"%PDF mirror bytes"

        with patch(
            "charon.agents.quartermaster.datasheets.download_pdf_bytes",
            side_effect=mock_download,
        ), patch(
            "charon.agents.quartermaster.datasheets.search_pdf_mirrors",
            return_value=[
                "https://broken.com/NE555.pdf",
                "https://working.com/NE555.pdf",
            ],
        ), patch(
            "charon.agents.TheArchivist"
        ) as mock_archivist_cls:
            mock_archivist_cls.return_value.index_pdf_datasheet.return_value = 1

            result = fetch_datasheet(
                db_path=mock_db,
                datasheet_dir=datasheet_dir,
                scout_agent=None,
                payload=payload,
            )

        assert "✅ Datasheet pipeline complete for NE555" in result

    def test_fetch_datasheet_all_downloads_fail(
        self, mock_db: Path, datasheet_dir: Path
    ):
        mock_scout = MagicMock()
        payload = QuartermasterPayload(
            action="fetch_datasheet",
            part_number="NE555",
            url="https://primary.com/NE555.pdf",
        )

        with patch(
            "charon.agents.quartermaster.datasheets.download_pdf_bytes",
            side_effect=RuntimeError("Download blocked"),
        ), patch(
            "charon.agents.quartermaster.datasheets.search_pdf_mirrors",
            return_value=["https://mirror1.com/NE555.pdf"],
        ):
            result = fetch_datasheet(
                db_path=mock_db,
                datasheet_dir=datasheet_dir,
                scout_agent=mock_scout,
                payload=payload,
            )

        assert "Failed to retrieve datasheet for NE555" in result

    def test_fetch_datasheet_existing_part_id_in_db(
        self, mock_db: Path, datasheet_dir: Path
    ):
        """Exercises SQL existing part lookup branch."""
        conn = get_connection(mock_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO parts (mpn, category, description) VALUES (?, ?, ?)",
            ("NE555", "ICs", "Timer IC"),
        )
        conn.commit()
        conn.close()

        payload = QuartermasterPayload(
            action="fetch_datasheet",
            part_number="NE555",
            url="https://example.com/NE555.pdf",
        )

        with patch(
            "charon.agents.quartermaster.datasheets.download_pdf_bytes",
            return_value=b"%PDF content",
        ), patch(
            "charon.agents.TheArchivist"
        ) as mock_archivist_cls:
            mock_archivist_cls.return_value.index_pdf_datasheet.return_value = 1

            result = fetch_datasheet(
                db_path=mock_db,
                datasheet_dir=datasheet_dir,
                scout_agent=None,
                payload=payload,
            )

        assert "✅ Datasheet pipeline complete for NE555" in result

    def test_fetch_datasheet_sqlite_error_handled(
        self, mock_db: Path, datasheet_dir: Path
    ):
        payload = QuartermasterPayload(
            action="fetch_datasheet",
            part_number="NE555",
            url="https://example.com/NE555.pdf",
        )

        with patch(
            "charon.agents.quartermaster.datasheets.download_pdf_bytes",
            return_value=b"%PDF content",
        ), patch(
            "charon.agents.quartermaster.datasheets.get_db_connection",
            side_effect=sqlite3.OperationalError("Database locked"),
        ):
            result = fetch_datasheet(
                db_path=mock_db,
                datasheet_dir=datasheet_dir,
                scout_agent=None,
                payload=payload,
            )

        assert "PDF downloaded to disk, but failed to record in quartermaster.db" in result

    def test_fetch_datasheet_archivist_indexing_error_handled(
        self, mock_db: Path, datasheet_dir: Path
    ):
        payload = QuartermasterPayload(
            action="fetch_datasheet",
            part_number="NE555",
            url="https://example.com/NE555.pdf",
        )

        with patch(
            "charon.agents.quartermaster.datasheets.download_pdf_bytes",
            return_value=b"%PDF content",
        ), patch(
            "charon.agents.TheArchivist",
            side_effect=ImportError("ChromaDB unavailable"),
        ):
            result = fetch_datasheet(
                db_path=mock_db,
                datasheet_dir=datasheet_dir,
                scout_agent=None,
                payload=payload,
            )

        assert "Saved to disk/SQLite, but vector indexing skipped" in result