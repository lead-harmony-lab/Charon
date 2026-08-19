"""
charon/concierge/memory.py
System Version: v2.4.1

Module: Semantic User Memory
Extracts, stores, and retrieves long-term user facts and preferences using ChromaDB.
"""

import json
import logging
import datetime
import chromadb
from typing import List, Optional

from charon.config.paths import CONCIERGE_MEMORY_DIR

logger = logging.getLogger("Charon.Concierge.Memory")

MEMORY_EXTRACTION_PROMPT = """You are Charon's background memory processor.
Your job is to analyze the user's input and extract any long-term facts, preferences, rules, or entities.
Ignore transient statements (e.g., "I'm tired", "Run the script now", "Hello").
Focus on permanent or semi-permanent state (e.g., "I prefer dark mode", "My main project is called Apollo", "Don't interrupt me on Tuesdays").

Format your response strictly as a JSON list of strings. If no long-term facts are found, return an empty list: []
Example Output: ["User prefers dark mode", "User's primary project is Apollo"]
"""

class SemanticMemory:
    """Manages long-term extraction and retrieval of user state."""

    def __init__(self, llm_client, model_name: str, chroma_client: Optional[chromadb.ClientAPI] = None):
        self.client = llm_client
        self.model_name = model_name

        try:
            # Use the shared client if provided, otherwise instantiate directly
            self.chroma_client = chroma_client or chromadb.PersistentClient(path=str(CONCIERGE_MEMORY_DIR))
            self.user_db = self.chroma_client.get_or_create_collection(name="user_memory")
            logger.info("Semantic User Memory connected.")
        except Exception as e:
            logger.error(f"Failed to connect to Semantic Memory DB: {e}")
            self.user_db = None

    async def extract_and_store(self, user_input: str) -> None:
        """Silently extracts facts from user input and stores them as vectors."""
        if not self.user_db or not user_input.strip():
            return

        try:
            response = await self.client.generate(
                model=self.model_name,
                system=MEMORY_EXTRACTION_PROMPT,
                prompt=f"User Input: {user_input}",
                options={"temperature": 0.1}
            )

            raw_text = response.get("response", "[]").strip()

            if raw_text.startswith("```json"):
                raw_text = raw_text[7:-3].strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:-3].strip()

            facts: List[str] = json.loads(raw_text)

            if not facts:
                return

            now = datetime.datetime.now()
            ids = [f"mem_{now.timestamp()}_{i}" for i in range(len(facts))]
            metadatas = [{"timestamp": now.isoformat(), "type": "user_fact"} for _ in facts]

            self.user_db.add(
                ids=ids,
                documents=facts,
                metadatas=metadatas
            )

            logger.debug(f"Extracted and stored {len(facts)} memory facts: {facts}")

        except json.JSONDecodeError:
            logger.debug(f"Memory extraction failed to parse JSON: {raw_text}")
        except Exception as e:
            logger.error(f"Memory extraction error: {e}")

    def get_relevant_memories(self, context_query: str, limit: int = 5) -> str:
        """
        Retrieves historical facts relevant to the current conversation.
        Returns a formatted string ready to be injected into Charon's system prompt.
        """
        if not self.user_db or not context_query.strip():
            return ""

        try:
            results = self.user_db.query(
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