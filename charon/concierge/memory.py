"""
charon/concierge/memory.py
System Version: v3.0.0

Module: Semantic User Memory
Extracts, stores, and retrieves short-term ephemeral actions and long-term heuristics using ChromaDB.
"""

import json
import logging
import datetime
import chromadb
from typing import List, Optional

from charon.config.paths import CONCIERGE_MEMORY_DIR

logger = logging.getLogger("Charon.Concierge.Memory")

MEMORY_EXTRACTION_PROMPT = """You are Charon's background memory processor.
Analyze the user's input and extract key state information, classifying it strictly into two categories:
1. "action": Short-term tasks, active contexts, or immediate emotional states (e.g., "Debugging the database", "Frustrated with a memory leak").
2. "rule": Long-term facts, preferences, rules, or entities (e.g., "Prefers concise answers", "Main project is called Apollo").

Ignore transient conversational filler (e.g., "Hello", "Yes").

Format your response strictly as a JSON list of objects. If no actionable memory is found, return an empty list: []
Example Output: 
[
  {"type": "rule", "content": "User prefers dark mode"},
  {"type": "action", "content": "Troubleshooting core.py compilation errors"}
]
"""

class SemanticMemory:
    """Manages extraction and retrieval of short-term actions and long-term user state."""

    def __init__(self, llm_client, model_name: str, chroma_client: Optional[chromadb.ClientAPI] = None):
        self.client = llm_client
        self.model_name = model_name

        try:
            self.chroma_client = chroma_client or chromadb.PersistentClient(path=str(CONCIERGE_MEMORY_DIR))
            self.ephemera_db = self.chroma_client.get_or_create_collection(name="concierge_ephemera")
            self.heuristics_db = self.chroma_client.get_or_create_collection(name="core_heuristics")
            logger.info("Semantic User Memory (Ephemera & Heuristics) connected.")
        except Exception as e:
            logger.error(f"Failed to connect to Semantic Memory DB: {e}")
            self.ephemera_db = None
            self.heuristics_db = None

    async def extract_and_store(self, user_input: str) -> None:
        """Silently extracts facts from user input and routes them to Ephemera or Heuristics."""
        if not self.ephemera_db or not self.heuristics_db or not user_input.strip():
            return

        raw_text = ""

        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": MEMORY_EXTRACTION_PROMPT},
                    {"role": "user", "content": f"User Input: {user_input}"}
                ],
                temperature=0.1
            )

            raw_text = response.choices[0].message.content.strip()

            if raw_text.startswith("```json"):
                raw_text = raw_text[7:-3].strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:-3].strip()

            extracted_items: List[dict] = json.loads(raw_text)

            if not extracted_items:
                return

            now = datetime.datetime.now()
            timestamp = now.isoformat()

            actions = [item["content"] for item in extracted_items if item.get("type") == "action"]
            rules = [item["content"] for item in extracted_items if item.get("type") == "rule"]

            # Route Actions to Ephemera DB
            if actions:
                action_ids = [f"act_{now.timestamp()}_{i}" for i in range(len(actions))]
                action_metas = [{"timestamp": timestamp, "type": "action"} for _ in actions]
                self.ephemera_db.add(ids=action_ids, documents=actions, metadatas=action_metas)
                logger.debug(f"Stored {len(actions)} ephemeral actions.")

            # Route Rules to Heuristics DB
            if rules:
                rule_ids = [f"rul_{now.timestamp()}_{i}" for i in range(len(rules))]
                rule_metas = [{"timestamp": timestamp, "type": "rule"} for _ in rules]
                self.heuristics_db.add(ids=rule_ids, documents=rules, metadatas=rule_metas)
                logger.debug(f"Stored {len(rules)} long-term heuristics.")

        except json.JSONDecodeError:
            logger.debug(f"Memory extraction failed to parse JSON: {raw_text}")
        except Exception as e:
            logger.error(f"Memory extraction error: {e}")

    async def query_ephemera(self, limit: int = 3) -> List[dict]:
        """
        Retrieves recent chronological events from short-term memory.
        Used to determine what the user was doing right before going idle.
        """
        if not self.ephemera_db:
            return []

        try:
            # Fetch a larger batch, sort by metadata timestamp locally
            results = self.ephemera_db.get(
                limit=limit * 5,
                include=["documents", "metadatas"]
            )

            if not results or not results.get("documents"):
                return []

            docs = results["documents"]
            metas = results["metadatas"]

            combined = [
                {"summary": doc, "timestamp": meta.get("timestamp", "")}
                for doc, meta in zip(docs, metas)
            ]

            # Sort descending by timestamp (newest first)
            combined.sort(key=lambda x: x["timestamp"], reverse=True)
            return combined[:limit]

        except Exception as e:
            logger.error(f"[Memory] Failed to query ephemera: {e}")
            return []

    async def query_heuristics(self, query: str, limit: int = 3) -> dict:
        """
        Retrieves long-term semantic rules and preferences based on a query.
        """
        if not self.heuristics_db or not query.strip():
            return {"summary": "None specific"}

        try:
            results = self.heuristics_db.query(
                query_texts=[query],
                n_results=limit,
                include=["documents"]
            )

            documents = results.get("documents", [[]])[0]
            if not documents:
                return {"summary": "None specific"}

            return {"summary": " | ".join(documents)}

        except Exception as e:
            logger.error(f"[Memory] Failed to query heuristics: {e}")
            return {"summary": "None specific"}

    def get_relevant_memories(self, context_query: str, limit: int = 5) -> str:
        """
        Legacy wrapper for backwards compatibility with older system prompts.
        Routes to heuristics_db.
        """
        if not self.heuristics_db or not context_query.strip():
            return ""

        try:
            results = self.heuristics_db.query(
                query_texts=[context_query],
                n_results=limit
            )

            documents = results.get("documents", [[]])[0]
            if not documents:
                return ""

            memory_str = "\n".join([f"- {doc}" for doc in documents])
            return f"\nRelevant User Memory:\n{memory_str}\n"

        except Exception as e:
            logger.error(f"Memory retrieval error: {e}")
            return ""