"""
charon/concierge/memory.py
System Version: v3.1.0

Module: Semantic User Memory
Extracts, stores, and retrieves short-term ephemeral actions, long-term heuristics,
and HIL (Human-In-The-Loop) decision histories using ChromaDB.
"""

import json
import logging
import datetime
import chromadb
from typing import List, Optional, Dict, Any

from charon.config.paths import CONCIERGE_MEMORY_DIR

logger = logging.getLogger("Charon.Concierge.Memory")

MEMORY_EXTRACTION_PROMPT = """You are Charon's background memory processor.
Analyze the user's input and extract key state information, classifying it strictly into two categories:
1. "action": Short-term tasks, active contexts, or immediate emotional states (e.g., "Debugging the database", "Frustrated with a memory leak").
2. "rule": Long-term facts, preferences, rules, or entities (e.g., "Prefers concise answers", "Main project is called Apollo").

Ignore transient conversational filler (e.g., "Hello", "Yes").

Format your response strictly as a JSON object containing a "memories" key with a list of extracted items. If no actionable memory is found, return an empty list inside the object: {"memories": []}
Example Output: 
{
  "memories": [
    {"type": "rule", "content": "User prefers dark mode"},
    {"type": "action", "content": "Troubleshooting core.py compilation errors"}
  ]
}
"""

class SemanticMemory:
    """Manages extraction, retrieval, and heuristic training for short-term actions, long-term rules, and HIL authorizations."""

    def __init__(self, llm_client, model_name: str, chroma_client: Optional[chromadb.ClientAPI] = None):
        self.client = llm_client
        self.model_name = model_name

        try:
            self.chroma_client = chroma_client or chromadb.PersistentClient(path=str(CONCIERGE_MEMORY_DIR))
            self.ephemera_db = self.chroma_client.get_or_create_collection(name="concierge_ephemera")
            self.heuristics_db = self.chroma_client.get_or_create_collection(name="core_heuristics")
            self.hil_decisions_db = self.chroma_client.get_or_create_collection(name="hil_decisions")
            logger.info("Semantic User Memory (Ephemera, Heuristics & HIL Decisions) connected.")
        except Exception as e:
            logger.error(f"Failed to connect to Semantic Memory DB: {e}")
            self.ephemera_db = None
            self.heuristics_db = None
            self.hil_decisions_db = None

    async def extract_and_store(self, user_input: str) -> None:
        """Silently extracts facts from user input and routes them to Ephemera or Heuristics."""
        if not self.ephemera_db or not self.heuristics_db or not user_input.strip():
            return

        try:
            # The Robust Fix: Force JSON at the API level
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": MEMORY_EXTRACTION_PROMPT},
                    {"role": "user", "content": f"User Input: {user_input}"}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )

            raw_text = response.choices[0].message.content.strip()

            # The Safety Fallback: Never loop, never crash
            try:
                parsed_data = json.loads(raw_text)
                extracted_items = parsed_data.get("memories", [])
            except json.JSONDecodeError as e:
                logger.warning(f"[Memory] JSON parse failed, defaulting to empty. Error: {e} | Raw: {raw_text}")
                extracted_items = []

            # If we have no valid extracted items, exit silently and let the chat bypass continue
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

        except Exception as e:
            logger.error(f"Memory extraction error: {e}")
            # Fails silently so the orchestration loop isn't interrupted

    async def log_hil_decision(
        self,
        task_id: str,
        prompt: str,
        intent_summary: str,
        context: Dict[str, Any],
        granted: bool
    ) -> None:
        """
        Logs Human-In-The-Loop authorization decisions to ChromaDB
        for heuristic confidence model training.
        """
        if not self.hil_decisions_db:
            return

        try:
            now = datetime.datetime.now()
            timestamp = now.isoformat()
            doc_id = f"hil_{now.timestamp()}_{task_id}"

            # Document text forms the vector representation for semantic matching
            document_text = f"Prompt: {prompt} | Intent: {intent_summary} | Window: {context.get('active_window', '')}"

            metadata = {
                "task_id": task_id,
                "timestamp": timestamp,
                "granted": granted,
                "active_window": str(context.get("active_window", "Unknown")),
                "desktop_activity": str(context.get("desktop_activity", "None"))
            }

            self.hil_decisions_db.add(
                ids=[doc_id],
                documents=[document_text],
                metadatas=[metadata]
            )
            logger.info(f"[Memory.HIL] Logged decision for task {task_id}: granted={granted}")
        except Exception as e:
            logger.error(f"[Memory.HIL] Failed to log decision: {e}")

    async def evaluate_routing_confidence(
        self,
        prompt: str,
        context: Dict[str, Any],
        min_sample_size: int = 3,
        limit: int = 5
    ) -> float:
        """
        Queries historical HIL decisions for semantically similar prompts and context.
        Returns a confidence score between 0.0 and 1.0 representing historical approval rate.
        """
        if not self.hil_decisions_db:
            return 0.0

        try:
            query_text = f"Prompt: {prompt} | Window: {context.get('active_window', '')}"
            results = self.hil_decisions_db.query(
                query_texts=[query_text],
                n_results=limit,
                include=["metadatas"]
            )

            metadatas = results.get("metadatas", [[]])[0]
            if not metadatas:
                return 0.0

            granted_count = sum(1 for meta in metadatas if meta.get("granted", False))
            total_count = len(metadatas)

            if total_count < min_sample_size:
                return 0.0

            confidence_score = granted_count / total_count
            logger.debug(f"[Memory.HIL] Evaluated routing confidence: {confidence_score:.2f} ({granted_count}/{total_count})")
            return confidence_score

        except Exception as e:
            logger.error(f"[Memory.HIL] Failed to evaluate routing confidence: {e}")
            return 0.0

    async def query_ephemera(self, limit: int = 3) -> List[dict]:
        """
        Retrieves recent chronological events from short-term memory.
        Used to determine what the user was doing right before going idle.
        """
        if not self.ephemera_db:
            return []

        try:
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