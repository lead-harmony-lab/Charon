"""Tests for Quartermaster helper utility functions."""

import sqlite3
from pathlib import Path

import pytest

from charon.agents.quartermaster.utils import (
    clean_mpn,
    get_db_connection,
    is_valid_mirror_candidate,
)


class TestGetDbConnection:
    """Tests for SQLite database connection initialization."""

    def test_get_db_connection_missing_file_raises(self, tmp_path: Path):
        db_path = tmp_path / "nonexistent" / "quartermaster.db"
        with pytest.raises(FileNotFoundError, match="Quartermaster database not found"):
            get_db_connection(db_path)
        # Verify parent directory was created as side effect
        assert db_path.parent.exists()

    def test_get_db_connection_success(self, tmp_path: Path):
        db_path = tmp_path / "quartermaster.db"
        db_path.touch()

        conn = get_db_connection(db_path)
        assert isinstance(conn, sqlite3.Connection)
        assert conn.row_factory == sqlite3.Row

        # Verify foreign keys & pragmas executed
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys;")
        fk_status = cursor.fetchone()[0]
        assert fk_status == 1
        conn.close()

    def test_get_db_connection_accepts_string_path(self, tmp_path: Path):
        db_path = tmp_path / "quartermaster.db"
        db_path.touch()

        conn = get_db_connection(str(db_path))
        assert isinstance(conn, sqlite3.Connection)
        conn.close()


class TestCleanMpn:
    """Tests for MPN sanitization logic."""

    @pytest.mark.parametrize(
        "raw_input,expected",
        [
            ("Download datasheet for NE555 please", "NE555"),
            ("get pinout for STM32F103C8T6", "STM32F103C8T6"),
            ("lookup part LM7805", "LM7805"),
            ("ATMEGA328P", "ATMEGA328P"),
            ("  esp32-wroom-32d  ", "ESP32-WROOM-32D"),
            ("", "UNKNOWN_PART"),
            (None, "UNKNOWN_PART"),
            (12345, "UNKNOWN_PART"),
            ("???", "UNKNOWN_PART"),
        ],
    )
    def test_clean_mpn_variations(self, raw_input, expected):
        assert clean_mpn(raw_input) == expected


class TestIsValidMirrorCandidate:
    """Tests for datasheet candidate URL filtering."""

    @pytest.mark.parametrize(
        "url,mpn,expected",
        [
            (
                "https://www.ti.com/lit/ds/symlink/ne555.pdf",
                "NE555",
                True,
            ),
            (
                "https://component-docs.com/files/NE555-datasheet.pdf",
                "NE555",
                True,
            ),
            (
                "https://component-docs.com/files/LM7805.pdf",
                "NE555",
                False,  # MPN mismatch in PDF name
            ),
            (
                "https://www.youtube.com/watch?v=ne555_tutorial",
                "NE555",
                False,  # Blocked domain
            ),
            (
                "https://google.com/search?q=ne555+pdf",
                "NE555",
                False,  # Blocked domain
            ),
            (
                "https://distributor.com/parts/ne555-details.html",
                "NE555",
                True,  # HTML page allowed
            ),
            (
                "",
                "NE555",
                False,  # Invalid URL
            ),
            (
                "https://example.com/sheet.pdf",
                "",
                False,  # Invalid MPN
            ),
        ],
    )
    def test_is_valid_mirror_candidate(self, url, mpn, expected):
        assert is_valid_mirror_candidate(url, mpn) == expected
