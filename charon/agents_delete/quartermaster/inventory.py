"""
charon/agents/quartermaster/inventory.py
System Version: v0.1.0 | File Revision: 1.2.0

Module: Management logic for PartVault inventory logging, stock queries, and DB schema setup.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.agents.quartermaster.utils import (
    _extract_param_dict,
    clean_mpn,
    get_db_connection,
)
from charon.intent import DynamicActionPayload

logger = logging.getLogger("CHAROND.Quartermaster.Inventory")


def init_quartermaster_db(db_path: Path) -> None:
    """Initializes the PartVault SQLite schema and KiCad Library SQL View."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mpn TEXT UNIQUE NOT NULL,
                manufacturer TEXT,
                description TEXT,
                category TEXT DEFAULT 'General',
                symbol TEXT,
                footprint TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 0,
                bin_location TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS datasheets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                sha256_hash TEXT UNIQUE NOT NULL,
                chroma_doc_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
            );

            DROP VIEW IF EXISTS kicad_parts_view;

            CREATE VIEW kicad_parts_view AS
            SELECT 
                p.id AS id,
                p.mpn AS mpn,
                p.manufacturer AS manufacturer,
                p.description AS description,
                p.category AS category,
                p.symbol AS symbol,
                p.footprint AS footprint,
                COALESCE(SUM(i.quantity), 0) AS stock,
                GROUP_CONCAT(DISTINCT i.bin_location) AS bin_location,
                d.file_path AS datasheet_path
            FROM parts p
            LEFT JOIN inventory i ON p.id = i.part_id
            LEFT JOIN datasheets d ON p.id = d.part_id
            GROUP BY p.id;
            """
        )
        conn.commit()


def log_inventory(
    db_path: Path,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    raw_prompt: str = "",
) -> str:
    """Logs incoming component inventory quantities and updates physical bin locations."""
    init_quartermaster_db(db_path)

    p_dict = _extract_param_dict(payload)

    raw_mpn = (
        p_dict.get("mpn")
        or getattr(payload, "mpn", None)
        or (raw_prompt.strip() if raw_prompt else None)
    )

    if not raw_mpn:
        return "Error: An 'mpn' (Manufacturer Part Number) is required to log inventory."

    safe_mpn = clean_mpn(str(raw_mpn))

    raw_qty = p_dict.get("quantity", getattr(payload, "quantity", 1))
    try:
        quantity = int(raw_qty)
    except (ValueError, TypeError):
        quantity = 1

    storage_bin = (
        p_dict.get("storage_bin")
        or getattr(payload, "storage_bin", None)
        or "Unassigned"
    )

    category = (
        p_dict.get("category")
        or getattr(payload, "category", None)
        or "General"
    )

    manufacturer = (
        p_dict.get("manufacturer")
        or getattr(payload, "manufacturer", None)
        or ""
    )

    description = (
        p_dict.get("description")
        or getattr(payload, "description", None)
        or ""
    )

    footprint = (
        p_dict.get("package_footprint")
        or p_dict.get("footprint")
        or getattr(payload, "package_footprint", None)
        or getattr(payload, "footprint", None)
        or ""
    )

    symbol = (
        p_dict.get("symbol")
        or getattr(payload, "symbol", None)
        or ""
    )

    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()

            # Insert or update base part details
            cursor.execute(
                """
                INSERT INTO parts (mpn, manufacturer, description, category, symbol, footprint)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(mpn) DO UPDATE SET
                    manufacturer = CASE WHEN excluded.manufacturer != '' THEN excluded.manufacturer ELSE parts.manufacturer END,
                    description = CASE WHEN excluded.description != '' THEN excluded.description ELSE parts.description END,
                    category = CASE WHEN excluded.category != 'General' THEN excluded.category ELSE parts.category END,
                    symbol = CASE WHEN excluded.symbol != '' THEN excluded.symbol ELSE parts.symbol END,
                    footprint = CASE WHEN excluded.footprint != '' THEN excluded.footprint ELSE parts.footprint END;
                """,
                (safe_mpn, manufacturer, description, category, symbol, footprint),
            )

            cursor.execute("SELECT id FROM parts WHERE mpn = ?", (safe_mpn,))
            part_id = cursor.fetchone()["id"]

            # Record inventory count log
            cursor.execute(
                """
                INSERT INTO inventory (part_id, quantity, bin_location)
                VALUES (?, ?, ?);
                """,
                (part_id, quantity, storage_bin),
            )
            conn.commit()

        return (
            f"Logged {quantity} unit(s) of '{safe_mpn}' into bin '{storage_bin}' "
            f"under category '{category}' in PartVault."
        )

    except Exception as e:
        logger.error(f"Failed to log inventory for {safe_mpn}: {e}")
        return f"Error logging inventory into PartVault: {str(e)}"


def check_inventory(
    db_path: Path,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    raw_prompt: str = "",
) -> str:
    """Queries PartVault inventory for stock levels, bin locations, and technical metadata."""
    init_quartermaster_db(db_path)

    p_dict = _extract_param_dict(payload)

    raw_mpn = (
        p_dict.get("mpn")
        or p_dict.get("query")
        or getattr(payload, "mpn", None)
        or getattr(payload, "query", None)
        or (raw_prompt.strip() if raw_prompt else None)
    )

    if not raw_mpn:
        return "Error: An 'mpn' or query parameter is required to check inventory."

    safe_mpn = clean_mpn(str(raw_mpn))

    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT mpn, manufacturer, description, category, stock, bin_location, footprint, datasheet_path
                FROM kicad_parts_view
                WHERE mpn = ? OR mpn LIKE ?;
                """,
                (safe_mpn, f"%{safe_mpn}%"),
            )
            results = cursor.fetchall()

        if not results:
            return f"No stock or record found for part '{safe_mpn}' in PartVault."

        output = [f"=== PartVault Inventory Query: '{safe_mpn}' ==="]
        for row in results:
            bins = row["bin_location"] or "Unassigned"
            ds = row["datasheet_path"] or "None"
            output.append(
                f"• MPN: {row['mpn']}\n"
                f"  Stock Level: {row['stock']} unit(s)\n"
                f"  Bin Location(s): {bins}\n"
                f"  Manufacturer: {row['manufacturer'] or 'N/A'}\n"
                f"  Category: {row['category']}\n"
                f"  Footprint: {row['footprint'] or 'N/A'}\n"
                f"  Datasheet: {ds}"
            )

        return "\n\n".join(output)

    except Exception as e:
        logger.error(f"Failed to query inventory for {safe_mpn}: {e}")
        return f"Error checking PartVault inventory: {str(e)}"