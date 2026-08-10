import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from charon.agents.quartermaster.bom import generate_bom
from charon.intent import QuartermasterPayload
from charon.db.connection import get_connection


@pytest.fixture
def mock_db(tmp_path: Path) -> Path:
    """Creates a temporary SQLite database with Quartermaster schema and test parts."""
    db_path = tmp_path / "quartermaster.db"
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mpn TEXT UNIQUE,
            manufacturer TEXT,
            category TEXT,
            description TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER,
            quantity INTEGER,
            storage_bin TEXT
        )
        """
    )
    cursor.execute(
        "INSERT INTO parts (id, mpn) VALUES (1, 'NE555'), (2, 'LM317')"
    )
    cursor.execute(
        "INSERT INTO inventory (part_id, quantity, storage_bin) VALUES (1, 10, 'Bin-1'), (2, 2, 'Bin-2')"
    )
    conn.commit()
    conn.close()
    return db_path


class TestGenerateBom:
    """Tests for project BOM inventory audits."""

    def test_generate_bom_missing_project_directory(self, mock_db: Path):
        payload = QuartermasterPayload(action="generate_bom")
        result = generate_bom(db_path=mock_db, payload=payload, raw_prompt="")
        assert "Error: A 'project_directory' path is required" in result

    def test_generate_bom_file_not_found(self, mock_db: Path, tmp_path: Path):
        project_dir = tmp_path / "my_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        payload = QuartermasterPayload(
            action="generate_bom",
            project_directory=str(project_dir),
        )

        with patch(
            "charon.agents.quartermaster.bom.resolve_project_path",
            return_value=project_dir,
        ):
            result = generate_bom(db_path=mock_db, payload=payload)

        assert "No BOM CSV found at" in result

    def test_generate_bom_all_in_stock(self, mock_db: Path, tmp_path: Path):
        project_dir = tmp_path / "my_project"
        bom_dir = project_dir / "bom"
        bom_dir.mkdir(parents=True, exist_ok=True)

        bom_csv = bom_dir / "assembly_bom.csv"
        bom_csv.write_text(
            "Part Number,Quantity\n"
            "NE555,5\n"
            "LM317,2\n"
        )

        payload = QuartermasterPayload(
            action="generate_bom",
            project_directory=str(project_dir),
        )

        with patch(
            "charon.agents.quartermaster.bom.resolve_project_path",
            return_value=project_dir,
        ):
            result = generate_bom(db_path=mock_db, payload=payload)

        assert f"=== BOM Audit for {project_dir.name} ===" in result
        assert "• NE555: Required = 5 | Owned = 10 | Status: ✅ AVAILABLE" in result
        assert "• LM317: Required = 2 | Owned = 2 | Status: ✅ AVAILABLE" in result
        assert "Audit complete: All required components are available in stock!" in result

    def test_generate_bom_shortages_detected(self, mock_db: Path, tmp_path: Path):
        project_dir = tmp_path / "my_project"
        bom_dir = project_dir / "bom"
        bom_dir.mkdir(parents=True, exist_ok=True)

        bom_csv = bom_dir / "assembly_bom.csv"
        bom_csv.write_text(
            "Part Number,Quantity\n"
            "NE555,15\n"  # Owned: 10, Need: 5
            "LM317,5\n"   # Owned: 2, Need: 3
        )

        payload = QuartermasterPayload(
            action="generate_bom",
            project_directory=str(project_dir),
        )

        with patch(
            "charon.agents.quartermaster.bom.resolve_project_path",
            return_value=project_dir,
        ):
            result = generate_bom(db_path=mock_db, payload=payload)

        assert "• NE555: Required = 15 | Owned = 10 | Status: ❌ SHORTAGE (Need 5 more)" in result
        assert "• LM317: Required = 5 | Owned = 2 | Status: ❌ SHORTAGE (Need 3 more)" in result
        assert "Audit complete: 2 component shortage(s) detected." in result

    def test_generate_bom_alternate_csv_headers_and_bad_qty(
        self, mock_db: Path, tmp_path: Path
    ):
        project_dir = tmp_path / "my_project"
        bom_dir = project_dir / "bom"
        bom_dir.mkdir(parents=True, exist_ok=True)

        bom_csv = bom_dir / "assembly_bom.csv"
        bom_csv.write_text(
            "MPN,Qty\n"
            "NE555,invalid_number\n"  # Fallback qty = 1
            ",5\n"                    # Empty MPN row (skipped)
            "LM317,\n"                 # Missing qty (Fallback qty = 1)
        )

        payload = QuartermasterPayload(
            action="generate_bom",
            project_directory=str(project_dir),
        )

        with patch(
            "charon.agents.quartermaster.bom.resolve_project_path",
            return_value=project_dir,
        ):
            result = generate_bom(db_path=mock_db, payload=payload)

        assert "• NE555: Required = 1 | Owned = 10 | Status: ✅ AVAILABLE" in result
        assert "• LM317: Required = 1 | Owned = 2 | Status: ✅ AVAILABLE" in result

    def test_generate_bom_exception_handled(self, mock_db: Path, tmp_path: Path):
        payload = QuartermasterPayload(
            action="generate_bom",
            project_directory="my_project",
        )

        with patch(
            "charon.agents.quartermaster.bom.resolve_project_path",
            side_effect=RuntimeError("Path resolution failed"),
        ):
            result = generate_bom(db_path=mock_db, payload=payload)

        assert "Failed to execute BOM inventory audit: Path resolution failed" in result