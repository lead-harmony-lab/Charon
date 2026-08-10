"""
charon/agents/archivist/datasheets.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Management logic for PDF datasheet chunking, SHA-256 deduplication,
ChromaDB vector embedding, and SQLite PartVault synchronization.
Updated for DynamicActionPayload integration.
"""

import hashlib
import logging
from pathlib import Path
import shutil
import time
from typing import Any, Dict, Optional, Union
import chromadb

from charon.agents.archivist.utils import _get_payload_val
from charon.agents.quartermaster.inventory import init_quartermaster_db
from charon.agents.quartermaster.utils import get_db_connection
from charon.config.paths import DATASHEETS_DIR, QUARTERMASTER_DB_PATH
from charon.intent import DynamicActionPayload
from charon.tools.pdf import chunk_text, extract_text_from_pdf, sanitize_metadata

logger = logging.getLogger("CHAROND.Archivist.Datasheets")


class DatasheetManager:
    """Handles PDF datasheet indexing, deduplication, SQLite linking, and RAG vector searches."""

    def __init__(self, datasheet_collection: chromadb.Collection):
        self.datasheet_collection = datasheet_collection

    def index_pdf_datasheet(
        self,
        pdf_path: Union[str, Path],
        mpn: str,
        metadata: Optional[Dict[str, Any]] = None,
        sha256_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Parses, deduplicates (SHA-256), embeds a PDF into ChromaDB, and updates entries in quartermaster.db."""
        resolved_path = Path(pdf_path).resolve()
        if not resolved_path.exists():
            raise FileNotFoundError(
                f"Datasheet PDF file not found at: {resolved_path}"
            )

        clean_metadata = sanitize_metadata(metadata)
        safe_mpn = str(mpn).strip().upper()

        # 1. Resolve or compute SHA-256 hash for strict deduplication
        if not sha256_hash:
            hasher = hashlib.sha256()
            with open(resolved_path, "rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            sha256_hash = hasher.hexdigest()

        # 2. Store canonically inside XDG DATASHEETS_DIR (~/.local/share/partvault/datasheets/)
        DATASHEETS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            rel_path = resolved_path.relative_to(DATASHEETS_DIR)
            canonical_pdf_path = resolved_path
            db_file_path = str(rel_path)
        except ValueError:
            target_filename = f"{safe_mpn}_{sha256_hash[:10]}.pdf"
            canonical_pdf_path = DATASHEETS_DIR / target_filename
            if resolved_path != canonical_pdf_path:
                shutil.copy2(resolved_path, canonical_pdf_path)
                logger.info(
                    f"Copied datasheet to canonical storage: {canonical_pdf_path}"
                )
            db_file_path = target_filename

        # 3. Extract text pages and build chunk list
        logger.info(f"Extracting text from {canonical_pdf_path.name}...")
        page_texts = extract_text_from_pdf(canonical_pdf_path)

        chunks = []
        doc_ids = []
        metadatas = []

        chroma_root_id = f"doc_{sha256_hash[:16]}"
        global_chunk_idx = 0

        for page_num, text in page_texts:
            page_chunks = chunk_text(text, chunk_size=1000, overlap=200)

            for chunk_sub_idx, chunk in enumerate(page_chunks):
                chunk_id = f"{chroma_root_id}_p{page_num}_c{chunk_sub_idx}_{global_chunk_idx}"
                chunk_meta = {
                    "mpn": safe_mpn,
                    "sha256": sha256_hash,
                    "chroma_doc_id": chroma_root_id,
                    "page": page_num,
                    "chunk_index": chunk_sub_idx,
                    "file_path": str(canonical_pdf_path),
                    "category": clean_metadata.get("category", "General"),
                    "indexed_at": time.time(),
                }
                for k, v in clean_metadata.items():
                    if k not in chunk_meta:
                        chunk_meta[k] = v

                chunks.append(chunk)
                doc_ids.append(chunk_id)
                metadatas.append(chunk_meta)
                global_chunk_idx += 1

        # 4. Upsert into ChromaDB Vector Store
        if chunks:
            self.datasheet_collection.upsert(
                documents=chunks, ids=doc_ids, metadatas=metadatas
            )
            logger.info(
                f"Successfully embedded {len(chunks)} text chunks for MPN '{safe_mpn}' into ChromaDB (Root ID: '{chroma_root_id}')."
            )

        # 5. Synchronize with PartVault SQLite Database (quartermaster.db)
        init_quartermaster_db(QUARTERMASTER_DB_PATH)
        with get_db_connection(QUARTERMASTER_DB_PATH) as conn:
            cursor = conn.cursor()

            # Ensure part exists in catalog
            cursor.execute("SELECT id FROM parts WHERE mpn = ?", (safe_mpn,))
            row = cursor.fetchone()
            if row:
                part_id = row["id"] if hasattr(row, "keys") else row[0]
            else:
                cursor.execute(
                    "INSERT INTO parts (mpn, category) VALUES (?, ?)",
                    (safe_mpn, clean_metadata.get("category", "General")),
                )
                part_id = cursor.lastrowid

            # Locate existing record by hash or relative file path
            cursor.execute(
                "SELECT id FROM datasheets WHERE sha256_hash = ?", (sha256_hash,)
            )
            existing_hash = cursor.fetchone()

            cursor.execute(
                "SELECT id FROM datasheets WHERE file_path = ?", (db_file_path,)
            )
            existing_path = cursor.fetchone()

            hash_id = (
                existing_hash["id"]
                if hasattr(existing_hash, "keys")
                else (existing_hash[0] if existing_hash else None)
            )
            path_id = (
                existing_path["id"]
                if hasattr(existing_path, "keys")
                else (existing_path[0] if existing_path else None)
            )

            if hash_id and path_id and hash_id != path_id:
                cursor.execute("DELETE FROM datasheets WHERE id = ?", (path_id,))

            if hash_id:
                cursor.execute(
                    "UPDATE datasheets SET part_id = ?, file_path = ?, chroma_doc_id = ? WHERE id = ?",
                    (part_id, db_file_path, chroma_root_id, hash_id),
                )
            elif path_id:
                cursor.execute(
                    "UPDATE datasheets SET part_id = ?, sha256_hash = ?, chroma_doc_id = ? WHERE id = ?",
                    (part_id, sha256_hash, chroma_root_id, path_id),
                )
            else:
                cursor.execute(
                    "INSERT INTO datasheets (part_id, file_path, sha256_hash, chroma_doc_id) VALUES (?, ?, ?, ?)",
                    (part_id, db_file_path, sha256_hash, chroma_root_id),
                )
            conn.commit()

        return {
            "chunks": len(chunks),
            "mpn": safe_mpn,
            "sha256_hash": sha256_hash,
            "chroma_doc_id": chroma_root_id,
            "file_path": str(canonical_pdf_path),
        }

    def index_datasheet_action(
        self, params: Union[DynamicActionPayload, Dict[str, Any]]
    ) -> str:
        """Action handler wrapper for indexing datasheets via agent parameter calls."""
        file_path = _get_payload_val(
            params, "file_path", "pdf_path", "document_path"
        )
        mpn = _get_payload_val(params, "mpn", "part_number")
        category = _get_payload_val(params, "category", default="General")
        sha256_hash = _get_payload_val(params, "sha256_hash", "sha256", "hash")

        if not file_path or not mpn:
            return "Error: Both 'file_path' and 'mpn' parameters are required to index a datasheet."

        try:
            result = self.index_pdf_datasheet(
                pdf_path=Path(file_path),
                mpn=str(mpn),
                metadata={"category": str(category)},
                sha256_hash=str(sha256_hash) if sha256_hash else None,
            )
            count = result["chunks"]
            doc_id = result["chroma_doc_id"]
            hash_str = result["sha256_hash"][:16]

            return (
                f"✅ Successfully indexed {count} text chunk(s) from '{Path(file_path).name}' under MPN '{mpn}'.\n"
                f"  • Chroma Doc ID: {doc_id}\n"
                f"  • SHA-256 Hash: {hash_str}...\n"
                f"  • PartVault SQLite database linked."
            )
        except Exception as e:
            logger.error(f"Failed to index datasheet: {e}")
            return f"Error indexing datasheet: {str(e)}"

    def search_datasheets(
        self,
        params: Union[DynamicActionPayload, Dict[str, Any]],
        raw_prompt: str = "",
    ) -> str:
        """Queries the datasheet vector store for technical specifications or RAG answers."""
        raw_query = (
            _get_payload_val(params, "query", "prompt", "raw_prompt")
            or raw_prompt
        )
        mpn = _get_payload_val(params, "mpn", "part_number")

        total_chunks = self.datasheet_collection.count()
        if total_chunks == 0:
            return "The datasheet vector store is currently empty."

        if not raw_query or not str(raw_query).strip():
            return "Error: A 'query' parameter is required to search datasheets."

        query = str(raw_query).strip()

        try:
            requested_n = int(
                _get_payload_val(params, "n_results", "top_k", default=4)
            )
        except (ValueError, TypeError):
            requested_n = 4

        n_results = min(requested_n, total_chunks)
        where_clause = (
            {"mpn": str(mpn).strip().upper()}
            if mpn and str(mpn).strip()
            else None
        )

        try:
            results = self.datasheet_collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_clause,
                include=["documents", "metadatas"],
            )

            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]

            # Fallback: Retry globally if exact MPN filter produced no results
            if not docs and where_clause:
                logger.info(
                    f"No exact matches for MPN filter {where_clause}; retrying global vector search..."
                )
                results = self.datasheet_collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    include=["documents", "metadatas"],
                )
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]

            if not docs:
                target_str = f" for MPN '{mpn}'" if mpn else ""
                return f"No relevant technical text found in datasheet memory{target_str}."

            formatted_chunks = []
            for i, (doc, meta) in enumerate(zip(docs, metas), start=1):
                snippet = doc.strip() if doc else ""
                if len(snippet) > 800:
                    snippet = snippet[:800] + "...\n[Snippet Truncated]"

                item = (
                    f"--- Match {i} [MPN: {meta.get('mpn', 'N/A')} | Page {meta.get('page', '?')}] ---\n"
                    f"File: {meta.get('file_path', 'Unknown')}\n"
                    f"Doc ID: {meta.get('chroma_doc_id', 'N/A')}\n"
                    f"Excerpt:\n{snippet}"
                )
                formatted_chunks.append(item)

            return (
                f"Retrieved {len(docs)} relevant excerpt(s) from datasheet memory:\n\n"
                + "\n\n".join(formatted_chunks)
            )

        except Exception as e:
            logger.error(f"Datasheet RAG search failed: {e}")
            return f"Error searching datasheet vector store: {str(e)}"