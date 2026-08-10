"""
charon/agents/archivist/ledger.py
System Version: v0.1.0 | File Revision: 2.0.0

Module: Management logic for the operational rules & system memory ledger.
Updated for DynamicActionPayload intent parsing.
"""

import logging
import time
from collections import Counter
from typing import Any, Dict, Union
import chromadb

from charon.agents.archivist.utils import _get_payload_val
from charon.intent import DynamicActionPayload

logger = logging.getLogger("CHAROND.Archivist.Ledger")

DEDUPLICATION_DISTANCE_THRESHOLD = 0.2
EXPUNGE_MAX_DISTANCE = 1.2


class LedgerManager:
    """Handles operational rule storage, deduplication, search, and expunging."""

    def __init__(
        self,
        collection: chromadb.Collection,
        datasheet_collection: chromadb.Collection,
    ):
        self.collection = collection
        self.datasheet_collection = datasheet_collection

    def search_ledger(
        self,
        params: Union[DynamicActionPayload, Dict[str, Any]],
        datasheet_search_fallback,
        raw_prompt: str = "",
    ) -> str:
        """Retrieves exact historical rules based on a user's explicit query."""
        raw_query = (
            _get_payload_val(params, "query", "prompt", "raw_prompt")
            or raw_prompt
        )
        if not raw_query or not str(raw_query).strip():
            return "No search query provided."

        query = str(raw_query).strip()
        total_records = self.collection.count()

        if total_records == 0:
            if self.datasheet_collection.count() > 0:
                logger.info(
                    "System ledger is empty. Bridging query to datasheet knowledge base..."
                )
                return datasheet_search_fallback(params, raw_prompt=raw_prompt)
            return "The ledger is currently empty. No records to search."

        try:
            requested_n = int(
                _get_payload_val(params, "n_results", "top_k", default=5)
            )
        except (ValueError, TypeError):
            requested_n = 5

        n_results = min(requested_n, total_records)
        results = self.collection.query(
            query_texts=[query], n_results=n_results
        )
        documents = results.get("documents", [[]])[0]

        if not documents:
            if self.datasheet_collection.count() > 0:
                logger.info(
                    "No matching rules in system ledger. Falling back to datasheet knowledge base..."
                )
                return datasheet_search_fallback(params, raw_prompt=raw_prompt)
            return "The ledger contains no records matching that inquiry."

        formatted_results = "\n".join([f"- {doc}" for doc in documents])
        return f"Ledger records retrieved:\n{formatted_results}"

    def store_record(
        self, params: Union[DynamicActionPayload, Dict[str, Any]]
    ) -> str:
        """Explicitly stores a fact/rule into the database with metadata and deduplication."""
        raw_fact = _get_payload_val(params, "fact", "rule", "target_concept")

        if not raw_fact:
            mem_cand = _get_payload_val(params, "memory_candidate")
            if isinstance(mem_cand, dict):
                raw_fact = mem_cand.get("fact")

        category = str(
            _get_payload_val(params, "category", default="system_rule")
        )

        if not raw_fact or not str(raw_fact).strip():
            return "No explicit fact or rule provided to record."

        fact = str(raw_fact).strip()

        # Deduplication Check
        if self.collection.count() > 0:
            check = self.collection.query(
                query_texts=[fact], n_results=1, include=["distances"]
            )
            distances = check.get("distances", [[]])[0]

            if distances and distances[0] < DEDUPLICATION_DISTANCE_THRESHOLD:
                logger.info(
                    f"Duplicate rejected. Fact already exists in ledger: {fact}"
                )
                return f"This information is already present in the ledger under '{category}'."

        fact_id = f"fact_{time.time()}"
        metadata = {"category": category, "timestamp": time.time()}

        self.collection.add(
            documents=[fact], metadatas=[metadata], ids=[fact_id]
        )

        logger.info(f"Committed to ledger [{category}]: {fact}")
        return f"The information has been securely committed to the ledger under the category '{category}'."

    def expunge_record(
        self,
        params: Union[DynamicActionPayload, Dict[str, Any]],
        raw_prompt: str = "",
    ) -> str:
        """Locates and deletes records by keyword substring match or semantic similarity."""
        raw_target = (
            _get_payload_val(params, "target_concept", "fact", "rule", "query")
            or raw_prompt
        )
        if not raw_target:
            mem_cand = _get_payload_val(params, "memory_candidate")
            if isinstance(mem_cand, dict):
                raw_target = mem_cand.get("fact")

        if not raw_target or not str(raw_target).strip():
            return "Please specify the concept, rule, or path fragment to expunge."

        target_concept = str(raw_target).strip()

        if self.collection.count() == 0:
            return "The ledger is currently empty. No records to expunge."

        # Pass 1: Literal Substring Matching
        all_data = self.collection.get()
        all_ids = all_data.get("ids", [])
        all_docs = all_data.get("documents", [])

        matching_ids = [
            doc_id
            for doc_id, doc in zip(all_ids, all_docs)
            if doc and target_concept.lower() in str(doc).lower()
        ]

        if matching_ids:
            self.collection.delete(ids=matching_ids)
            logger.info(
                f"Expunged {len(matching_ids)} record(s) matching substring '{target_concept}'"
            )
            return f"Struck {len(matching_ids)} record(s) matching '{target_concept}' from the ledger."

        # Pass 2: Semantic Similarity Search Fallback
        results = self.collection.query(
            query_texts=[target_concept],
            n_results=1,
            include=["documents", "distances"],
        )

        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not ids or not distances:
            return f"No records found matching '{target_concept}'."

        similarity_distance = distances[0]
        if similarity_distance > EXPUNGE_MAX_DISTANCE:
            return f"No closely related records found for '{target_concept}'. (Nearest match distance: {similarity_distance:.2f})"

        target_id = ids[0]
        archived_fact = docs[0]

        self.collection.delete(ids=[target_id])
        logger.info(
            f"Expunged record {target_id}: {archived_fact} (Distance: {similarity_distance:.2f})"
        )

        return f"The record regarding '{archived_fact}' has been safely struck from the ledger."

    def summarize_ledger(
        self, params: Union[DynamicActionPayload, Dict[str, Any]]
    ) -> str:
        """Returns a categorized, high-level overview of all stored context."""
        count = self.collection.count()
        ds_count = self.datasheet_collection.count()

        if count == 0 and ds_count == 0:
            return "The Continental Ledger is currently empty."

        summary_lines = []

        if count > 0:
            all_data = self.collection.get(include=["metadatas"])
            metadatas = all_data.get("metadatas", [])
            categories = [
                meta.get("category", "uncategorized")
                for meta in metadatas
                if meta
            ]
            category_counts = Counter(categories)

            summary_lines.append(f"System Memory ({count} records):")
            for cat, amount in category_counts.items():
                summary_lines.append(
                    f"  • {amount} {cat.replace('_', ' ').title()}"
                )

        if ds_count > 0:
            summary_lines.append(
                f"\nDatasheet Knowledge Base ({ds_count} vector text chunks indexed)."
            )

        return "\n".join(summary_lines)