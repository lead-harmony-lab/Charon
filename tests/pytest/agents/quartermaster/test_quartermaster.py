"""test_quartermaster.py — Unit tests for TheQuartermaster agent and modules."""

import csv
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from charon.agents.quartermaster import TheQuartermaster
from charon.agents.quartermaster.utils import (
from charon.db.connection import get_connection
    clean_mpn,
    get_db_connection,
    is_valid_mirror_candidate,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db(tmp_path: Path) -> Path:
    """Creates a temporary SQLite database with the full Quartermaster schema."""
    db_path = tmp_path / "quartermaster.db"
    conn = get_connection(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mpn TEXT UNIQUE NOT NULL,
            manufacturer TEXT,
            category TEXT,
            description TEXT,
            package_footprint TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 0,
            storage_bin TEXT DEFAULT 'Unsorted',
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(part_id) REFERENCES parts(id),
            UNIQUE(part_id, storage_bin)
        );
    """)

    cursor.execute("""
        CREATE TABLE datasheets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER NOT NULL,
            file_path TEXT UNIQUE NOT NULL,
            source_url TEXT,
            FOREIGN KEY(part_id) REFERENCES parts(id)
        );
    """)

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def quartermaster(mock_db: Path, tmp_path: Path) -> TheQuartermaster:
    """Instantiates TheQuartermaster configured with temporary paths."""
    datasheet_dir = tmp_path / "datasheets"
    datasheet_dir.mkdir(parents=True, exist_ok=True)
    return TheQuartermaster(db_path=mock_db, datasheet_dir=datasheet_dir)


# ============================================================================
# 1. Utility Function Tests
# ============================================================================

class TestQuartermasterUtils:
    """Tests for sanitization, candidate validation, and DB helpers."""

    def test_clean_mpn_removes_query_noise(self):
        raw_query = "download datasheet for NE555P please"
        cleaned = clean_mpn(raw_query)
        assert cleaned == "NE555P"

    def test_clean_mpn_fallback_for_empty(self):
        assert clean_mpn("") == "UNKNOWN_PART"

    def test_is_valid_mirror_candidate_blocked_domains(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert not is_valid_mirror_candidate(url, "NE555P")

    def test_is_valid_mirror_candidate_pdf_matching(self):
        valid_pdf = "https://example.com/datasheets/NE555P.pdf"
        mismatched_pdf = "https://example.com/datasheets/LM358.pdf"

        assert is_valid_mirror_candidate(valid_pdf, "NE555P") is True
        assert is_valid_mirror_candidate(mismatched_pdf, "NE555P") is False

    def test_get_db_connection_wal_mode(self, mock_db: Path):
        conn = get_db_connection(mock_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        row = cursor.fetchone()
        conn.close()
        assert row[0].lower() == "wal"


# ============================================================================
# 2. Inventory Operation Tests
# ============================================================================

class TestInventoryOperations:
    """Tests stock logging and inventory queries."""

    def test_log_inventory_new_part(self, quartermaster: TheQuartermaster, mock_db: Path):
        result = quartermaster.execute(
            action="log_inventory",
            parameters={
                "part_number": "STM32F401RE",
                "quantity": 15,
                "storage_bin": "Bin-A1",
                "category": "Microcontrollers",
                "manufacturer": "STMicroelectronics",
            },
        )

        assert "Logged 15 unit(s) of STM32F401RE" in result

        conn = get_connection(str(mock_db))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT p.mpn, i.quantity, i.storage_bin FROM parts p JOIN inventory i ON p.id = i.part_id WHERE p.mpn = 'STM32F401RE'"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "STM32F401RE"
        assert row[1] == 15
        assert row[2] == "Bin-A1"

    def test_check_inventory_found(self, quartermaster: TheQuartermaster):
        quartermaster.execute(
            action="log_inventory",
            parameters={"part_number": "LM7805", "quantity": 5, "storage_bin": "Bin-B2"},
        )

        query_res = quartermaster.execute(
            action="check_inventory",
            parameters={"part_number": "LM7805"},
        )

        assert "Found 1 matching component(s)" in query_res
        assert "LM7805" in query_res
        assert "5 unit(s)" in query_res
        assert "Bin-B2" in query_res

    def test_check_inventory_not_found(self, quartermaster: TheQuartermaster):
        query_res = quartermaster.execute(
            action="check_inventory",
            parameters={"part_number": "NONEXISTENT_PART_999"},
        )

        assert "No parts matching 'NONEXISTENT_PART_999' were found" in query_res


# ============================================================================
# 3. BOM Audit Tests
# ============================================================================

class TestBOMOperations:
    """Tests parsing and auditing project assembly BOM CSV files."""

    def test_generate_bom_shortage_and_available(
        self, quartermaster: TheQuartermaster, tmp_path: Path
    ):
        # 1. Seed stock for one component, leave another missing
        quartermaster.execute(
            action="log_inventory",
            parameters={"part_number": "RES-10K", "quantity": 100, "storage_bin": "Bin-R1"},
        )

        # 2. Setup project folder structure with assembly_bom.csv
        project_dir = tmp_path / "TestProject"
        bom_dir = project_dir / "bom"
        bom_dir.mkdir(parents=True, exist_ok=True)
        bom_csv = bom_dir / "assembly_bom.csv"

        with bom_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Part Number", "Quantity"])
            writer.writerow(["RES-10K", "10"])
            writer.writerow(["CAP-100NF", "5"])

        # 3. Execute BOM audit
        report = quartermaster.execute(
            action="generate_bom",
            parameters={"project_directory": str(project_dir)},
        )

        assert "AVAILABLE" in report
        assert "SHORTAGE" in report
        assert "Need 5 more" in report
        assert "1 component shortage(s) detected" in report


# ============================================================================
# 4. Datasheet Fetch & Indexing Tests
# ============================================================================

class TestDatasheetOperations:
    """Tests downloading, local disk storage, SQLite registration, and vector indexing."""

    @patch("charon.agents.quartermaster.datasheets.download_pdf_bytes")
    def test_fetch_datasheet_success(
        self,
        mock_download: MagicMock,
        quartermaster: TheQuartermaster,
        mock_db: Path,
        tmp_path: Path,
    ):
        # Mock valid PDF bytes return
        mock_download.return_value = b"%PDF-1.4 fake pdf content for testing"

        # Mock TheArchivist dynamically imported inside fetch_datasheet
        mock_archivist_cls = MagicMock()
        mock_archivist_instance = MagicMock()
        mock_archivist_instance.index_pdf_datasheet.return_value = 4
        mock_archivist_cls.return_value = mock_archivist_instance

        with patch.dict("sys.modules", {"charon.agents": MagicMock(TheArchivist=mock_archivist_cls)}):
            result = quartermaster.execute(
                action="fetch_datasheet",
                parameters={
                    "part_number": "ATMEGA328P",
                    "url": "https://example.com/ATMEGA328P.pdf",
                    "category": "Microcontrollers",
                },
            )

        assert "Datasheet pipeline complete for ATMEGA328P" in result
        assert "Indexed 4 chunks into ChromaDB vector memory" in result

        # Verify SQLite registration
        conn = get_connection(str(mock_db))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT d.file_path, d.source_url FROM datasheets d JOIN parts p ON d.part_id = p.id WHERE p.mpn = 'ATMEGA328P'"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "Microcontrollers/ATMEGA328P.pdf"
        assert row[1] == "https://example.com/ATMEGA328P.pdf"


# ============================================================================
# 5. Router & Invalid Actions Test
# ============================================================================

def test_quartermaster_unknown_action(quartermaster: TheQuartermaster):
    with pytest.raises(ValueError, match="Unknown action 'invalid_action'"):
        quartermaster.execute(action="invalid_action", parameters={})