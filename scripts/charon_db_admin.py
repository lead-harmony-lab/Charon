#!/usr/bin/env python3
"""
charon_db_admin.py — Consolidated ChromaDB Maintenance & Memory Ledger Utility for Charon.
"""

import argparse
from pathlib import Path
import sys
from typing import List, Optional

import chromadb

# Resolve default database path (preferring global user path)
XDG_DB_PATH = Path.home() / ".local" / "share" / "charon" / "chroma_db"
LOCAL_DB_PATH = Path(__file__).resolve().parent.parent / "memory"

DEFAULT_DB_PATH = XDG_DB_PATH if XDG_DB_PATH.exists() else LOCAL_DB_PATH


def resolve_collection(client: chromadb.PersistentClient, target_name: Optional[str] = None):
    """Resolves target collection or falls back to default/first available."""
    collections = client.list_collections()
    if not collections:
        print(f"❌ No vector collections found at path: {client._path}")
        sys.exit(1)

    if target_name:
        try:
            return client.get_collection(target_name)
        except Exception:
            print(f"⚠️ Collection '{target_name}' not found. Available: {[c.name for c in collections]}")
            sys.exit(1)

    # Prefer 'ledger' if present, otherwise default to first available
    for col in collections:
        if col.name.lower() == "ledger":
            return col

    return collections[0]


def list_entries(col, limit: Optional[int] = None):
    """Lists entries in the collection."""
    results = col.get(include=["documents", "metadatas"])
    ids = results.get("ids", [])
    docs = results.get("documents", [])
    metas = results.get("metadatas", [])

    total = len(ids)
    display_count = min(limit, total) if limit else total

    print(f"\n📦 Collection: '{col.name}' ({total} total records)\n" + "─" * 70)
    for idx in range(display_count):
        doc_id = ids[idx]
        doc = docs[idx] if docs else ""
        meta = metas[idx] if metas else {}
        print(f"[{doc_id}] {doc[:100]}{'...' if len(doc) > 100 else ''}")
        print(f" └─ Metadata: {meta}")
    print("─" * 70)


def search_entries(col, query: str):
    """Substrings/Fuzzy text search inside stored documents."""
    results = col.get(include=["documents", "metadatas"])
    ids = results.get("ids", [])
    docs = results.get("documents", [])
    metas = results.get("metadatas", [])

    matches = [
        (i, d, m) for i, d, m in zip(ids, docs, metas)
        if query.lower() in d.lower()
    ]

    print(f"\n🔍 Found {len(matches)} matching records for query '{query}':\n" + "─" * 70)
    for doc_id, doc, meta in matches:
        print(f"[{doc_id}] {doc}")
        print(f" └─ Metadata: {meta}")
    print("─" * 70)


def prune_duplicates(col, force: bool = False):
    """Scans and prunes duplicate document entries, keeping the first occurrence."""
    results = col.get(include=["documents"])
    ids = results.get("ids", [])
    docs = results.get("documents", [])

    seen_docs = set()
    ids_to_delete: List[str] = []

    for doc_id, doc in zip(ids, docs):
        if doc in seen_docs:
            ids_to_delete.append(doc_id)
        else:
            seen_docs.add(doc)

    if not ids_to_delete:
        print("✨ Ledger is clean. No duplicate documents found.")
        return

    print(f"⚠️ Found {len(ids_to_delete)} duplicate records.")
    if not force:
        confirm = input(f"Remove {len(ids_to_delete)} duplicates? (y/N): ")
        if confirm.lower() != "y":
            print("Operation cancelled.")
            return

    col.delete(ids=ids_to_delete)
    print(f"✅ Successfully pruned {len(ids_to_delete)} duplicate records.")


def delete_by_id(col, doc_id: str):
    """Deletes a record by exact ID."""
    col.delete(ids=[doc_id])
    print(f"✅ Removed record ID: {doc_id}")


def purge_by_pattern(col, pattern: str, force: bool = False):
    """Deletes all records containing matching substring."""
    results = col.get(include=["documents"])
    ids = results.get("ids", [])
    docs = results.get("documents", [])

    to_delete = [i for i, d in zip(ids, docs) if pattern.lower() in d.lower()]
    if not to_delete:
        print(f"⚠️ No documents matched pattern '{pattern}'.")
        return

    print(f"⚠️ Found {len(to_delete)} records matching pattern '{pattern}'.")
    if not force:
        confirm = input(f"Delete {len(to_delete)} matching records? (y/N): ")
        if confirm.lower() != "y":
            print("Operation cancelled.")
            return

    col.delete(ids=to_delete)
    print(f"✅ Purged {len(to_delete)} records matching pattern '{pattern}'.")


def purge_all(col, force: bool = False):
    """Wipes all contents of the collection."""
    ids = col.get().get("ids", [])
    if not ids:
        print("Collection is already empty.")
        return

    print(f"🚨 CRITICAL ACTION: About to wipe ALL {len(ids)} records from '{col.name}'!")
    if not force:
        confirm = input("Are you absolutely sure? (y/N): ")
        if confirm.lower() != "y":
            print("Wipe cancelled.")
            return

    col.delete(ids=ids)
    print(f"🧹 Collection '{col.name}' has been completely cleared.")


def main():
    parser = argparse.ArgumentParser(description="Charon Memory Ledger DB Administration Tool")
    parser.add_argument("--db-path", type=str, default=str(DEFAULT_DB_PATH), help="Path to ChromaDB directory")
    parser.add_argument("--collection", "-c", type=str, help="Specific collection name (defaults to 'ledger')")
    parser.add_argument("--list", "-l", action="store_true", help="List stored records")
    parser.add_argument("--limit", type=int, help="Limit output rows for --list")
    parser.add_argument("--search", "-s", type=str, help="Search records containing substring")
    parser.add_argument("--dedupe", action="store_true", help="Scan and prune exact duplicate records")
    parser.add_argument("--delete-id", type=str, help="Delete record by exact ID")
    parser.add_argument("--purge-pattern", type=str, help="Delete all records matching substring")
    parser.add_argument("--wipe-all", action="store_true", help="Wipe entire memory collection")
    parser.add_argument("--force", "-f", action="store_true", help="Bypass confirmation prompts")

    args = parser.parse_args()

    db_path = Path(args.db_path).resolve()
    if not db_path.exists():
        print(f"❌ Specified DB path does not exist: {db_path}")
        sys.exit(1)

    client = chromadb.PersistentClient(path=str(db_path))
    collection = resolve_collection(client, args.collection)

    if args.list:
        list_entries(collection, limit=args.limit)
    elif args.search:
        search_entries(collection, args.search)
    elif args.dedupe:
        prune_duplicates(collection, force=args.force)
    elif args.delete_id:
        delete_by_id(collection, args.delete_id)
    elif args.purge_pattern:
        purge_by_pattern(collection, args.purge_pattern, force=args.force)
    elif args.wipe_all:
        purge_all(collection, force=args.force)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
