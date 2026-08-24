"""
charon/gateway/routes/docs.py
System Version: v3.2.0 | File Revision: 3.2.2

Module:
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("Charon.Gateway.Routes.Docs")

router = APIRouter(prefix="/v1/docs", tags=["Knowledge Base"])

BASE_DIR = Path.cwd()
DOCS_DIR = BASE_DIR / "data" / "docs"
ADRS_DIR = DOCS_DIR / "adrs"
SPECS_DIR = DOCS_DIR / "specs"
MANUAL_DIR = DOCS_DIR / "manual"
MANUAL_FILE = MANUAL_DIR / "manual.json"

for d in [ADRS_DIR, SPECS_DIR, MANUAL_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def get_utc_timestamp() -> str:
    """Generates an ISO-8601 UTC timestamp string ending with Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================================
# Architecture Decision Records (ADRs)
# ============================================================================

@router.get("/adrs")
async def list_adrs():
    """Fetches all ADRs for the AdrViewer sidebar."""
    adrs = []
    for file_path in ADRS_DIR.glob("*.json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            adrs.append(data)
        except Exception as e:
            logger.error(f"Failed to parse ADR {file_path.name}: {e}")

    adrs.sort(key=lambda x: x.get("id", ""), reverse=True)
    return {"adrs": adrs}


@router.put("/adrs/{doc_id}")
async def update_adr(doc_id: str, request: Request):
    """Saves updates from the AdrViewer editor panel."""
    try:
        data = await request.json()
        data["lastUpdated"] = get_utc_timestamp()
        file_path = ADRS_DIR / f"{doc_id}.json"

        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"status": "success", "message": "ADR updated"}
    except Exception as e:
        logger.error(f"Failed to update ADR {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save ADR.")


@router.post("/adrs")
async def create_adr(request: Request):
    """Handles new document creation from the CreateDocModal."""
    try:
        data = await request.json()
        doc_id = data.get("id")
        if not doc_id:
            raise HTTPException(status_code=400, detail="Missing document ID")

        data["lastUpdated"] = get_utc_timestamp()
        file_path = ADRS_DIR / f"{doc_id}.json"

        if file_path.exists():
            raise HTTPException(status_code=409, detail="Document ID already exists")

        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"status": "success", "message": "ADR created"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create ADR: {e}")
        raise HTTPException(status_code=500, detail="Failed to create ADR.")


# ============================================================================
# System Specifications (Specs)
# ============================================================================

@router.get("/specs")
async def list_specs():
    """Fetches all Specs for the SpecsViewer sidebar."""
    specs = []
    for file_path in SPECS_DIR.glob("*.json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            specs.append(data)
        except Exception as e:
            logger.error(f"Failed to parse Spec {file_path.name}: {e}")

    specs.sort(key=lambda x: x.get("name", ""))
    return {"specs": specs}


@router.put("/specs/{doc_id}")
async def update_spec(doc_id: str, request: Request):
    """Saves updates from the SpecsViewer editor panel and sets lastUpdated."""
    try:
        data = await request.json()
        data["lastUpdated"] = get_utc_timestamp()
        file_path = SPECS_DIR / f"{doc_id}.json"

        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"status": "success", "message": "Spec updated"}
    except Exception as e:
        logger.error(f"Failed to update Spec {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save Spec.")


@router.post("/specs")
async def create_spec(request: Request):
    """Handles new spec creation from the CreateDocModal and sets lastUpdated."""
    try:
        data = await request.json()
        doc_id = data.get("id")
        if not doc_id:
            raise HTTPException(status_code=400, detail="Missing document ID")

        data["lastUpdated"] = get_utc_timestamp()
        file_path = SPECS_DIR / f"{doc_id}.json"

        if file_path.exists():
            raise HTTPException(status_code=409, detail="Document ID already exists")

        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"status": "success", "message": "Spec created"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create Spec: {e}")
        raise HTTPException(status_code=500, detail="Failed to create Spec.")


# ============================================================================
# Manual Tree
# ============================================================================

def apply_timestamps(new_nodes: List[Dict], old_nodes: List[Dict]) -> List[Dict]:
    """
    Recursively compares nodes, injects UTC timestamps if mutated,
    and bubbles up the most recent child updates to parents.
    """
    old_map = {node.get("id"): node for node in (old_nodes or [])}
    current_time = datetime.now(timezone.utc).isoformat()

    for new_node in new_nodes:
        node_id = new_node.get("id")
        old_node = old_map.get(node_id)

        # 1. Evaluate self for mutations
        if not old_node or \
           old_node.get("title") != new_node.get("title") or \
           old_node.get("content") != new_node.get("content"):
            new_node["updatedAt"] = current_time
        elif old_node and "updatedAt" in old_node:
            new_node["updatedAt"] = old_node["updatedAt"]

        # 2. Process children recursively
        if "children" in new_node and isinstance(new_node["children"], list):
            old_children = old_node.get("children", []) if old_node else []
            new_node["children"] = apply_timestamps(new_node["children"], old_children)

            # 3. Bubble up the most recent child update
            most_recent_child = None
            most_recent_time = None

            for child in new_node["children"]:
                if "updatedAt" in child:
                    try:
                        child_time = datetime.fromisoformat(child["updatedAt"])
                        if not most_recent_time or child_time > most_recent_time:
                            most_recent_time = child_time
                            most_recent_child = {
                                "id": child["id"],
                                "title": child["title"],
                                "timestamp": child["updatedAt"]
                            }
                    except ValueError:
                        pass

                if "lastChildUpdate" in child:
                    try:
                        grandchild_time = datetime.fromisoformat(child["lastChildUpdate"]["timestamp"])
                        if not most_recent_time or grandchild_time > most_recent_time:
                            most_recent_time = grandchild_time
                            most_recent_child = child["lastChildUpdate"]
                    except ValueError:
                        pass

            if most_recent_child:
                new_node["lastChildUpdate"] = most_recent_child
            else:
                new_node.pop("lastChildUpdate", None)

    return new_nodes


@router.get("/manual")
async def get_manual_tree():
    """Fetches the manual tree structure for the ManualViewer."""
    try:
        if not MANUAL_FILE.exists():
            return {"tree": []}

        data = json.loads(MANUAL_FILE.read_text(encoding="utf-8"))
        return {"tree": data}
    except Exception as e:
        logger.error(f"Failed to read manual tree: {e}")
        raise HTTPException(status_code=500, detail="Failed to load manual data.")


@router.put("/manual")
async def update_manual_tree(request: Request):
    """Saves updates from the ManualViewer with authoritative timestamps."""
    try:
        incoming_tree = await request.json()
        existing_tree = []
        if MANUAL_FILE.exists():
            existing_tree = json.loads(MANUAL_FILE.read_text(encoding="utf-8"))

        processed_tree = apply_timestamps(incoming_tree, existing_tree)

        MANUAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        MANUAL_FILE.write_text(json.dumps(processed_tree, indent=2), encoding="utf-8")

        return {"status": "success", "message": "Manual tree updated"}
    except Exception as e:
        logger.error(f"Failed to update manual tree: {e}")
        raise HTTPException(status_code=500, detail="Failed to save manual tree.")