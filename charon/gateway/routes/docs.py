"""
charon/gateway/routes/docs.py
System Version: v3.2.0 | File Revision: 3.2.0

Module:
"""
import os
from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/docs", tags=["Knowledge Base"])

# Map your frontend URL categories to actual disk locations
# Assuming charon is run from the project root. Adjust base_dir if needed.
BASE_DIR = Path.cwd()
DOC_MOUNT_POINTS = {
    "adrs": BASE_DIR / "docs" / "adrs",
    "architecture": BASE_DIR / "docs" / "architecture",
    "notebooks": BASE_DIR / "notebook_sources",
}

class DocItem(BaseModel):
    category: str
    filename: str
    title: str

@router.get("/", response_model=List[DocItem])
async def list_documents():
    """Scans the configured directories and returns available Markdown files."""
    available_docs = []
    
    for category, directory in DOC_MOUNT_POINTS.items():
        if not directory.exists():
            continue
            
        for file_path in directory.glob("*.md"):
            # Clean up the filename for a readable title (e.g., adr-001-setup.md -> Adr 001 Setup)
            title = file_path.stem.replace("-", " ").replace("_", " ").title()
            available_docs.append(
                DocItem(category=category, filename=file_path.name, title=title)
            )
            
    return sorted(available_docs, key=lambda x: (x.category, x.filename))

@router.get("/{category}/{filename}")
async def get_document(category: str, filename: str):
    """Serves the raw Markdown content of a specific file."""
    if category not in DOC_MOUNT_POINTS:
        raise HTTPException(status_code=404, detail="Documentation category not found.")
        
    target_dir = DOC_MOUNT_POINTS[category]
    target_file = (target_dir / filename).resolve()
    
    # Security Check: Prevent Path Traversal (e.g., ../../../etc/passwd)
    try:
        target_file.relative_to(target_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied. Invalid path structure.")
        
    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if target_file.suffix.lower() != '.md':
        raise HTTPException(status_code=400, detail="Only Markdown files are served by this endpoint.")
        
    try:
        content = target_file.read_text(encoding="utf-8")
        return {"content": content, "filename": filename, "category": category}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read document: {str(e)}")