"""
charon/agents/quartermaster/bom.py
System Version: v0.1.0 | File Revision: 1.2.0

Module: Handlers for parsing project assembly BOM CSV files and auditing stock availability
against the PartVault database view.
"""

import csv
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from charon.agents.quartermaster.inventory import init_quartermaster_db
from charon.agents.quartermaster.utils import (
    _extract_param_dict,
    clean_mpn,
    get_db_connection,
)
from charon.config.paths import resolve_project_path
from charon.intent import DynamicActionPayload

logger = logging.getLogger("CHAROND.Quartermaster.BOM")


def _find_bom_file(project_path: Path) -> Optional[Path]:
    """Locates the project assembly BOM CSV file across standard project folder locations."""
    candidates = [
        project_path / "bom" / "assembly_bom.csv",
        project_path / "bom" / "bom.csv",
        project_path / "assembly_bom.csv",
        project_path / "bom.csv",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    # Fallback: Check if project_path itself points directly to a CSV file
    if project_path.is_file() and project_path.suffix.lower() == ".csv":
        return project_path

    return None


def generate_bom(
    db_path: Path,
    payload: Optional[Union[DynamicActionPayload, Dict[str, Any]]] = None,
    raw_prompt: str = "",
) -> str:
    """Audits a project BOM CSV against quartermaster.db inventory to calculate shortages."""
    init_quartermaster_db(db_path)

    p_dict = _extract_param_dict(payload)
    project_dir = (
        p_dict.get("project_directory")
        or getattr(payload, "project_directory", None)
        or raw_prompt.strip()
    )
    if not project_dir:
        return "Error: A 'project_directory' path is required to audit or generate a BOM."

    try:
        target_path = resolve_project_path(project_dir)
        bom_path = _find_bom_file(target_path)

        if not bom_path:
            return (
                f"No BOM CSV found in '{target_path}'. "
                "Please place 'assembly_bom.csv' or 'bom.csv' inside the project directory or 'bom/' folder."
            )

        audit_report = [f"=== BOM Stock Audit: {bom_path.name} ({target_path.name}) ==="]
        shortages = 0
        total_items = 0

        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()

            with bom_path.open(mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Normalize field name lookups for flexibility across KiCad exports
                    mpn = (
                        row.get("Part Number")
                        or row.get("MPN")
                        or row.get("PartNumber")
                        or row.get("Value")
                    )

                    raw_qty = (
                        row.get("Quantity")
                        or row.get("Qty")
                        or row.get("COUNT")
                        or 1
                    )
                    try:
                        qty_req = int(float(raw_qty))
                    except (ValueError, TypeError):
                        qty_req = 1

                    if not mpn or not str(mpn).strip():
                        continue

                    safe_mpn = clean_mpn(str(mpn))
                    total_items += 1

                    # Query inventory via the unified KiCad view
                    cursor.execute(
                        """
                        SELECT stock, bin_location
                        FROM kicad_parts_view
                        WHERE mpn = ?
                        """,
                        (safe_mpn,)
                    )
                    result = cursor.fetchone()

                    if result:
                        in_stock = result["stock"] or 0
                        bin_loc = result["bin_location"] or "Unassigned"
                    else:
                        in_stock = 0
                        bin_loc = "N/A"

                    if in_stock >= qty_req:
                        status = "✅ AVAILABLE"
                    else:
                        shortage_qty = qty_req - in_stock
                        status = f"❌ SHORTAGE (Need {shortage_qty} more)"
                        shortages += 1

                    audit_report.append(
                        f"• {safe_mpn}: Needed = {qty_req} | Stock = {in_stock} | Bins: [{bin_loc}] | Status: {status}"
                    )

        if total_items == 0:
            return f"BOM file at '{bom_path}' was read, but no valid component rows were recognized."

        audit_report.append("\n" + "=" * 50)
        if shortages > 0:
            audit_report.append(
                f"Audit complete: {shortages} component shortage(s) out of {total_items} item(s) detected.\n"
                f"👉 Recommendation: Dispatch 'The Scout' agent to procure missing quantities."
            )
        else:
            audit_report.append(
                f"Audit complete: All {total_items} required component(s) are fully in stock!"
            )

        return "\n".join(audit_report)

    except Exception as e:
        logger.error(f"BOM audit failed: {e}")
        return f"Failed to execute BOM inventory audit: {str(e)}"