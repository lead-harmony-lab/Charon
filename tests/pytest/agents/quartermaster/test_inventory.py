import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from charon.agents.quartermaster.inventory import check_inventory, log_inventory
from charon.intent import QuartermasterPayload
from charon.db.connection import get_connection


@pytest.fixture
def mock_db(tmp_path: Path) -> Path:
    """Creates a temporary SQLite database with Quartermaster schema and row factory."""
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
            description TEXT,
            package_footprint TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER,
            quantity INTEGER,
            storage_bin TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(part_id, storage_bin)
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


class TestCheckInventory:
    """Tests for searching parts and inventory levels."""

    def test_check_inventory_missing_raw_part(self, mock_db: Path, tmp_path: Path):
        payload = QuartermasterPayload(action="check_inventory")
        result = check_inventory(
            db_path=mock_db,
            datasheet_dir=tmp_path,
            payload=payload,
            raw_prompt="",
        )
        assert "Error: A 'part_number' or 'query' parameter is required" in result

    def test_check_inventory_no_matches(self, mock_db: Path, tmp_path: Path):
        payload = QuartermasterPayload(action="check_inventory", query="NONEXISTENT")
        result = check_inventory(
            db_path=mock_db,
            datasheet_dir=tmp_path,
            payload=payload,
        )
        assert "No parts matching 'NONEXISTENT' were found" in result

    def test_check_inventory_found_part_full_details_relative_datasheet(
        self, mock_db: Path, tmp_path: Path
    ):
        conn = get_connection(mock_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO parts (id, mpn, manufacturer, category, description, package_footprint)
            VALUES (1, 'NE555', 'Texas Instruments', 'ICs', 'Precision Timer', 'SOIC-8')
            """
        )
        cursor.execute(
            "INSERT INTO inventory (part_id, quantity, storage_bin) VALUES (1, 10, 'Bin-A1')"
        )
        cursor.execute(
            "INSERT INTO inventory (part_id, quantity, storage_bin) VALUES (1, 5, 'Bin-B2')"
        )
        cursor.execute(
            "INSERT INTO datasheets (part_id, file_path, source_url) VALUES (1, 'ICs/NE555.pdf', 'http://example.com')"
        )
        conn.commit()
        conn.close()

        payload = QuartermasterPayload(action="check_inventory", mpn="NE555")
        result = check_inventory(
            db_path=mock_db,
            datasheet_dir=tmp_path,
            payload=payload,
        )

        assert "Found 1 matching component(s):" in result
        assert "MPN: NE555 (Texas Instruments)" in result
        assert "Category: ICs | Footprint: SOIC-8" in result
        assert "Total Stock: 15 unit(s)" in result
        assert "Storage Location(s): Bin-A1 (10); Bin-B2 (5)" in result
        assert str((tmp_path / "ICs/NE555.pdf").resolve()) in result
        assert "Description: Precision Timer" in result

    def test_check_inventory_found_part_absolute_datasheet(
        self, mock_db: Path, tmp_path: Path
    ):
        abs_ds_path = (tmp_path / "absolute_datasheet.pdf").resolve()

        conn = get_connection(mock_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO parts (id, mpn, manufacturer, category, description, package_footprint)
            VALUES (1, 'LM317', 'ON Semi', 'Regulators', 'Linear Regulator', 'TO-220')
            """
        )
        cursor.execute(
            "INSERT INTO datasheets (part_id, file_path, source_url) VALUES (1, ?, 'http://example.com')",
            (str(abs_ds_path),),
        )
        conn.commit()
        conn.close()

        payload = QuartermasterPayload(action="check_inventory", part_number="LM317")
        result = check_inventory(
            db_path=mock_db,
            datasheet_dir=tmp_path,
            payload=payload,
        )

        assert str(abs_ds_path) in result

    def test_check_inventory_found_part_missing_optional_fields(
        self, mock_db: Path, tmp_path: Path
    ):
        conn = get_connection(mock_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO parts (id, mpn, category) VALUES (1, 'RES_10K', 'Resistors')"
        )
        conn.commit()
        conn.close()

        payload = QuartermasterPayload(action="check_inventory", query="RES_10K")
        result = check_inventory(
            db_path=mock_db,
            datasheet_dir=tmp_path,
            payload=payload,
        )

        assert "MPN: RES_10K (Unknown Manufacturer)" in result
        assert "Footprint: N/A" in result
        assert "Total Stock: 0 unit(s)" in result
        assert "Storage Location(s): No assigned bin" in result
        assert "Datasheet: None on file" in result
        assert "Description: N/A" in result

    def test_check_inventory_db_exception(self, mock_db: Path, tmp_path: Path):
        payload = QuartermasterPayload(action="check_inventory", mpn="NE555")

        with patch(
            "charon.agents.quartermaster.inventory.get_db_connection",
            side_effect=sqlite3.OperationalError("Database corrupt"),
        ):
            result = check_inventory(
                db_path=mock_db,
                datasheet_dir=tmp_path,
                payload=payload,
            )

        assert "Error accessing inventory ledger: Database corrupt" in result


class TestLogInventory:
    """Tests for logging and upserting component inventory."""

    def test_log_inventory_missing_mpn(self, mock_db: Path):
        payload = QuartermasterPayload(action="log_inventory")
        result = log_inventory(db_path=mock_db, payload=payload, raw_prompt="")
        assert "Error: A 'part_number' (MPN) is required to log inventory." in result

    def test_log_inventory_new_part(self, mock_db: Path):
        payload = QuartermasterPayload(
            action="log_inventory",
            mpn="STM32F103C8T6",
            quantity=25,
            storage_bin="Bin-MCU-1",
            category="Microcontrollers",
            manufacturer="STMicroelectronics",
            description="ARM Cortex-M3 MCU",
            package_footprint="LQFP-48",
        )

        result = log_inventory(db_path=mock_db, payload=payload)
        assert "Logged 25 unit(s) of STM32F103C8T6 into location 'Bin-MCU-1'." in result

        conn = get_connection(mock_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM parts WHERE mpn = 'STM32F103C8T6'")
        part = cursor.fetchone()
        assert part["manufacturer"] == "STMicroelectronics"

        cursor.execute("SELECT * FROM inventory WHERE part_id = ?", (part["id"],))
        inv = cursor.fetchone()
        assert inv["quantity"] == 25
        assert inv["storage_bin"] == "Bin-MCU-1"
        conn.close()

    def test_log_inventory_existing_part_upsert_and_default_bin(self, mock_db: Path):
        # Insert initial part record
        log_inventory(
            db_path=mock_db,
            payload=QuartermasterPayload(
                action="log_inventory",
                mpn="NE555",
                quantity=10,
                storage_bin="Bin-1",
            ),
        )

        # Log additional stock to the same location, updating metadata
        result = log_inventory(
            db_path=mock_db,
            payload=QuartermasterPayload(
                action="log_inventory",
                part_number="NE555",
                quantity=5,
                storage_bin="Bin-1",
                manufacturer="TI",
            ),
        )

        assert "Logged 5 unit(s) of NE555 into location 'Bin-1'." in result

        conn = get_connection(mock_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT quantity FROM inventory WHERE storage_bin = 'Bin-1'"
        )
        inv = cursor.fetchone()
        assert inv["quantity"] == 15
        conn.close()

    def test_log_inventory_select_part_fails(self, mock_db: Path):
        from unittest.mock import MagicMock

        payload = QuartermasterPayload(action="log_inventory", mpn="NE555", quantity=1)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        with patch("charon.agents.quartermaster.inventory.get_db_connection") as mock_db_conn:
            mock_db_conn.return_value.__enter__.return_value = mock_conn
            result = log_inventory(db_path=mock_db, payload=payload)

        assert "Error: Failed to register part 'NE555' in database." in result

    def test_log_inventory_db_exception(self, mock_db: Path):
        payload = QuartermasterPayload(action="log_inventory", mpn="NE555", quantity=1)

        with patch(
            "charon.agents.quartermaster.inventory.get_db_connection",
            side_effect=sqlite3.OperationalError("Disk full"),
        ):
            result = log_inventory(db_path=mock_db, payload=payload)

        assert "Database error logging NE555: Disk full" in result