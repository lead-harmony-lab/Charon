import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Set
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("Charon.Gateway.Routes.Docs")

router = APIRouter(prefix="/v1/docs", tags=["Knowledge Base"])

BASE_DIR = Path.cwd()
DOCS_DIR = BASE_DIR / "data" / "docs"
ADRS_DIR = DOCS_DIR / "adrs"
SPECS_DIR = DOCS_DIR / "specs"
MANUAL_DIR = DOCS_DIR / "manual"
MANUAL_FILE = MANUAL_DIR / "manual_tree.json"
MANUAL_CONTENT_DIR = MANUAL_DIR / "content"

# Ensure all directories exist on startup
for d in [ADRS_DIR, SPECS_DIR, MANUAL_DIR, MANUAL_CONTENT_DIR]:
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
    """Saves updates from the SpecsViewer editor panel."""
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
    """Handles new spec creation from the CreateDocModal."""
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
# Manual Tree & Content
# ============================================================================

def get_all_node_ids(nodes: List[Dict]) -> set:
    """Recursively extracts all node IDs from a given tree."""
    ids = set()
    for node in nodes:
        if "id" in node:
            ids.add(node["id"])
        if "children" in node and isinstance(node["children"], list):
            ids.update(get_all_node_ids(node["children"]))
    return ids


def process_manual_tree(new_nodes: List[Dict], old_nodes: List[Dict]) -> List[Dict]:
    """
    Recursively compares nodes, extracts content to Markdown, injects
    UTC timestamps if mutated, and bubbles up child updates safely.
    """
    old_map = {node.get("id"): node for node in (old_nodes or [])}
    current_time = get_utc_timestamp()

    for new_node in new_nodes:
        node_id = new_node.get("id")
        old_node = old_map.get(node_id)

        # 1. Content Extraction (Acts as a safety net if full nodes are passed)
        content_mutated = False
        if "content" in new_node:
            new_content = new_node.pop("content")  # Strip it from the JSON tree
            file_path = MANUAL_CONTENT_DIR / f"{node_id}.md"

            old_content = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            if new_content != old_content:
                file_path.write_text(new_content, encoding="utf-8")
                content_mutated = True

        # 2. Evaluate self for mutations
        title_mutated = not old_node or old_node.get("title") != new_node.get("title")

        if title_mutated or content_mutated:
            new_node["updatedAt"] = current_time
        elif old_node and "updatedAt" in old_node:
            new_node["updatedAt"] = old_node["updatedAt"]

        # 3. Process children recursively
        if "children" in new_node and isinstance(new_node["children"], list):
            old_children = old_node.get("children", []) if old_node else []
            new_node["children"] = process_manual_tree(new_node["children"], old_children)

            # 4. Bubble up the most recent child update (Clean string comparisons)
            most_recent_child = None
            max_timestamp = ""  # Empty string is safely less than any ISO timestamp

            for child in new_node["children"]:
                # Check direct child updates
                child_time = child.get("updatedAt", "")
                if child_time > max_timestamp:
                    max_timestamp = child_time
                    most_recent_child = {
                        "id": child["id"],
                        "title": child.get("title", "Unknown"),
                        "timestamp": child_time
                    }

                # Check grandchild updates
                g_child = child.get("lastChildUpdate", {})
                g_child_time = g_child.get("timestamp", "")
                if g_child_time > max_timestamp:
                    max_timestamp = g_child_time
                    most_recent_child = g_child

            if most_recent_child:
                new_node["lastChildUpdate"] = most_recent_child
            else:
                new_node.pop("lastChildUpdate", None)

    return new_nodes


@router.get("/manual")
async def get_manual_tree():
    """Fetches the lean structural manual tree map."""
    try:
        if not MANUAL_FILE.exists():
            return []

        data = json.loads(MANUAL_FILE.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        logger.error(f"Failed to read manual tree: {e}")
        raise HTTPException(status_code=500, detail="Failed to load manual data.")


@router.put("/manual")
async def update_manual_tree(request: Request):
    """Saves structural updates. Safely strips content if mistakenly sent, and cleans up orphaned files."""
    try:
        incoming_tree = await request.json()
        existing_tree = []
        if MANUAL_FILE.exists():
            existing_tree = json.loads(MANUAL_FILE.read_text(encoding="utf-8"))

        # 1. Detect and delete orphaned markdown files
        existing_ids = get_all_node_ids(existing_tree)
        incoming_ids = get_all_node_ids(incoming_tree)
        deleted_ids = existing_ids - incoming_ids

        for doc_id in deleted_ids:
            file_path = MANUAL_CONTENT_DIR / f"{doc_id}.md"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted orphaned content file: {doc_id}.md")

        # 2. Process and save the new tree
        processed_tree = process_manual_tree(incoming_tree, existing_tree)

        MANUAL_FILE.write_text(json.dumps(processed_tree, indent=2), encoding="utf-8")

        return {"status": "success", "message": "Manual tree updated"}
    except Exception as e:
        logger.error(f"Failed to update manual tree: {e}")
        raise HTTPException(status_code=500, detail="Failed to save manual tree.")


@router.get("/manual/{doc_id}")
async def get_manual_content(doc_id: str):
    """Lazy-loads specific markdown content for a selected node."""
    try:
        file_path = MANUAL_CONTENT_DIR / f"{doc_id}.md"
        if not file_path.exists():
            return {"id": doc_id, "content": ""}

        content = file_path.read_text(encoding="utf-8")
        return {"id": doc_id, "content": content}
    except Exception as e:
        logger.error(f"Failed to load content for {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load document content.")


def update_tree_timestamp_for_node(nodes: List[Dict], target_id: str, new_time: str) -> Dict | None:
    """
    Recursively finds a node by ID, updates its `updatedAt` timestamp,
    and bubbles up the update to parents' `lastChildUpdate`.
    """
    for node in nodes:
        if node.get("id") == target_id:
            node["updatedAt"] = new_time
            return {"id": target_id, "title": node.get("title", "Unknown"), "timestamp": new_time}

        if "children" in node and isinstance(node["children"], list):
            bubbled_update = update_tree_timestamp_for_node(node["children"], target_id, new_time)

            if bubbled_update:
                node["lastChildUpdate"] = bubbled_update
                return bubbled_update

    return None


@router.put("/manual/{doc_id}")
async def update_manual_content(doc_id: str, request: Request):
    """Saves markdown content for a single node, updates tree timestamps, and returns status metadata."""
    try:
        data = await request.json()
        content = data.get("content", "")

        # 1. Save Markdown content
        file_path = MANUAL_CONTENT_DIR / f"{doc_id}.md"
        file_path.write_text(content, encoding="utf-8")

        # 2. Update tree timestamps
        current_time = get_utc_timestamp()
        tree_data = []

        if MANUAL_FILE.exists():
            tree_data = json.loads(MANUAL_FILE.read_text(encoding="utf-8"))
            was_updated = update_tree_timestamp_for_node(tree_data, doc_id, current_time)

            if was_updated:
                MANUAL_FILE.write_text(json.dumps(tree_data, indent=2), encoding="utf-8")

        return {
            "status": "success",
            "message": "Content updated",
            "updatedAt": current_time,
            "tree": tree_data
        }
    except Exception as e:
        logger.error(f"Failed to update content for {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save document content.")