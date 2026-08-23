"""
charon/gateway/routes/journal.py
System Version: v3.2.0 | File Revision: 3.2.0

Module:
"""
import sqlite3
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/journal", tags=["Dev Journal"])

# --- Pydantic Models ---

class NoteCreate(BaseModel):
    target_id: str = Field(default="global", description="Use 'global' or a specific agent_id")
    title: Optional[str] = None
    content: str
    created_by: str = Field(default="system")

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class NoteResponse(BaseModel):
    note_id: str
    target_id: str
    title: Optional[str]
    content: str
    created_by: str
    created_at: str
    updated_at: str

# --- Database Dependency ---
# Adjust the path to match your charon_state.db location
DB_PATH = "/home/godvalve/.local/share/charon/charon_state.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# --- API Endpoints ---

@router.get("/", response_model=List[NoteResponse])
def get_notes(target_id: Optional[str] = None, db: sqlite3.Connection = Depends(get_db)):
    """Retrieve all notes, optionally filtering by target (global or agent_id)."""
    cursor = db.cursor()
    if target_id:
        cursor.execute(
            "SELECT * FROM dev_notes WHERE target_id = ? ORDER BY updated_at DESC", 
            (target_id,)
        )
    else:
        cursor.execute("SELECT * FROM dev_notes ORDER BY updated_at DESC")
        
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

@router.post("/", response_model=NoteResponse)
def create_note(note: NoteCreate, db: sqlite3.Connection = Depends(get_db)):
    """Create a new developer log or agent-specific note."""
    note_id = str(uuid.uuid4())
    cursor = db.cursor()
    
    cursor.execute(
        """
        INSERT INTO dev_notes (note_id, target_id, title, content, created_by)
        VALUES (?, ?, ?, ?, ?)
        """,
        (note_id, note.target_id, note.title, note.content, note.created_by)
    )
    db.commit()
    
    # Fetch the created row to return the generated timestamps
    cursor.execute("SELECT * FROM dev_notes WHERE note_id = ?", (note_id,))
    return dict(cursor.fetchone())

@router.put("/{note_id}", response_model=NoteResponse)
def update_note(note_id: str, updates: NoteUpdate, db: sqlite3.Connection = Depends(get_db)):
    """Update an existing note's title or Markdown content."""
    cursor = db.cursor()
    
    # Build dynamic update query based on provided fields
    update_fields = []
    params = []
    if updates.title is not None:
        update_fields.append("title = ?")
        params.append(updates.title)
    if updates.content is not None:
        update_fields.append("content = ?")
        params.append(updates.content)
        
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields provided to update.")
        
    params.append(note_id)
    query = f"UPDATE dev_notes SET {', '.join(update_fields)} WHERE note_id = ?"
    
    cursor.execute(query, params)
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Note not found.")
        
    db.commit()
    cursor.execute("SELECT * FROM dev_notes WHERE note_id = ?", (note_id,))
    return dict(cursor.fetchone())

@router.delete("/{note_id}")
def delete_note(note_id: str, db: sqlite3.Connection = Depends(get_db)):
    """Remove a note from the ledger."""
    cursor = db.cursor()
    cursor.execute("DELETE FROM dev_notes WHERE note_id = ?", (note_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Note not found.")
    db.commit()
    return {"status": "success", "message": "Note deleted"}