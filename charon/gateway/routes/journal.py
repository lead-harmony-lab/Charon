"""
charon/gateway/routes/journal.py
System Version: v3.2.0 | File Revision: 3.2.2

Module: Filesystem-backed route handlers for the unified Dev Journal & Issue Tracker.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("Charon.Gateway.Routes.Journal")

router = APIRouter(prefix="/v1/journal", tags=["Dev Journal"])

BASE_DIR = Path.cwd()
JOURNAL_DIR = BASE_DIR / "data" / "journal"
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


def get_utc_timestamp() -> str:
    """Generates an ISO-8601 UTC timestamp string ending with Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/entries")
async def list_journal_entries():
    """Fetches all journal entries from data/journal/ for the Dev Log feed."""
    entries = []
    for file_path in JOURNAL_DIR.glob("*.json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            entries.append(data)
        except Exception as e:
            logger.error(f"Failed to parse journal entry {file_path.name}: {e}")

    # Sort entries by timestamp descending (newest first)
    entries.sort(key=lambda x: x.get("timestamp", x.get("id", "")), reverse=True)
    return {"entries": entries}


@router.get("/entries/{entry_id}")
async def get_journal_entry(entry_id: str):
    """Fetches a single journal entry by ID."""
    file_path = JOURNAL_DIR / f"{entry_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Journal entry not found.")

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        logger.error(f"Failed to read journal entry {entry_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load journal entry.")


@router.post("/entries")
async def save_journal_entry(request: Request):
    """Creates or updates a journal entry JSON file directly on the filesystem."""
    try:
        data = await request.json()
        entry_id = data.get("id")
        if not entry_id:
            raise HTTPException(status_code=400, detail="Missing entry ID")

        now = get_utc_timestamp()
        if not data.get("timestamp"):
            data["timestamp"] = now
        data["updatedAt"] = now

        file_path = JOURNAL_DIR / f"{entry_id}.json"
        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        return {"status": "success", "message": "Journal entry saved", "entry": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save journal entry: {e}")
        raise HTTPException(status_code=500, detail="Failed to save journal entry.")


@router.put("/entries/{entry_id}")
async def update_journal_entry(entry_id: str, request: Request):
    """Updates an existing journal entry JSON file."""
    try:
        data = await request.json()
        data["id"] = entry_id
        data["updatedAt"] = get_utc_timestamp()

        file_path = JOURNAL_DIR / f"{entry_id}.json"
        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        return {"status": "success", "message": "Journal entry updated", "entry": data}
    except Exception as e:
        logger.error(f"Failed to update journal entry {entry_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update journal entry.")


@router.delete("/entries/{entry_id}")
async def delete_journal_entry(entry_id: str):
    """Deletes a journal entry JSON file from disk."""
    try:
        file_path = JOURNAL_DIR / f"{entry_id}.json"
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Journal entry not found.")

        file_path.unlink()
        return {"status": "success", "message": f"Entry {entry_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete journal entry {entry_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete journal entry.")