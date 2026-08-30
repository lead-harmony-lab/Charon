"""
charon/core/session.py
System Version: v0.6.0 | File Revision: 6.0.1

Module: Core session gateway for Charon.
Manages session memory and serves as the declarative ingest boundary for the Core Engine.
Fully backed by SQLite for Zero-Trust session recovery and execution auditing.
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional, TYPE_CHECKING

from charon.config.paths import STATE_DB_PATH
from charon.core.skills import SkillLibrarian
from charon.db.connection import get_connection  # <-- Imported centralized connection manager
from charon.utils.memory import ConversationBuffer

if TYPE_CHECKING:
    from charon.core.orchestration import OrchestrationEngine

logger = logging.getLogger("Charon.Core.Session")


class SessionGateway:
    """The front desk managing DB-backed session memory and ingest pass-through."""

    def __init__(
        self,
        engine: Optional["OrchestrationEngine"] = None,
        librarian: Optional[SkillLibrarian] = None,
        journal: Optional[Any] = None,
        client_id: str = "session_gateway"
    ):
        self.librarian = librarian or SkillLibrarian.get_instance()
        self.db_path = STATE_DB_PATH  # <-- Fixed: STATE_DB_PATH already includes the filename
        self.client_id = client_id
        self.journal = journal

        # Initialize and hydrate memory from SQLite
        self.memory = ConversationBuffer(max_turns=5)
        self._hydrate_memory()

        if engine is None:
            from charon.core.orchestration import OrchestrationEngine
            self.engine = OrchestrationEngine(librarian=self.librarian)
        else:
            self.engine = engine

    # ==========================================
    # MEMORY PERSISTENCE (ZERO-TRUST STATE)
    # ==========================================

    def _hydrate_memory(self) -> None:
        """Loads the most recent conversation history from the database on startup."""
        query = "SELECT memory_json FROM session_state WHERE client_id = ?;"
        try:
            # <-- Fixed: Using get_connection
            with get_connection(self.db_path) as conn:
                row = conn.execute(query, (self.client_id,)).fetchone()
                if row and row["memory_json"]:  # Dictionary access thanks to row_factory
                    history = json.loads(row["memory_json"])
                    if hasattr(self.memory, "history"):
                        self.memory.history = history
                    logger.info(f"Hydrated {len(history)} past turns for client: {self.client_id}")
        except Exception as e:
            logger.error(f"Failed to hydrate memory for {self.client_id}: {e}")

    def _persist_memory(self) -> None:
        """Flushes the current in-memory buffer to SQLite."""
        history = self.memory.get_history() if hasattr(self.memory, "get_history") else []
        query = """
            INSERT INTO session_state (client_id, memory_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(client_id) DO UPDATE SET 
                memory_json = excluded.memory_json,
                updated_at = CURRENT_TIMESTAMP;
        """
        # <-- Fixed: Using get_connection
        with get_connection(self.db_path) as conn:
            conn.execute(query, (self.client_id, json.dumps(history)))

    def record_turn(self, user_input: str, system_response: str) -> None:
        """Saves a turn to the buffer and immediately persists to DB."""
        if not system_response:
            return

        resp_str = str(system_response).strip()

        if hasattr(self.memory, "add_turn") and callable(getattr(self.memory, "add_turn")):
            self.memory.add_turn(user_input, resp_str)
        elif hasattr(self.memory, "append") and callable(getattr(self.memory, "append")):
            self.memory.append({"user": user_input, "assistant": resp_str})

        # Lock it into the database
        self._persist_memory()

    # ==========================================
    # TASK INGESTION
    # ==========================================

    def _initialize_task_in_db(self, task_id: str, prompt: str, context: list) -> None:
        """
        Directly writes the initial PENDING task state to the database,
        including a snapshot of the context to guarantee execution auditing.
        """
        query = """
            INSERT INTO task_state (
                task_id, client_id, prompt, status, current_step_index, context_json, created_at, updated_at
            )
            VALUES (?, ?, ?, 'PENDING', 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        """
        # <-- Fixed: Using get_connection
        with get_connection(self.db_path) as conn:
            conn.execute(query, (task_id, self.client_id, prompt, json.dumps(context)))

    async def submit_task(
        self,
        user_input: str,
        target_role: Optional[str] = None
    ) -> Any:
        """Ingests a task, establishes the state truth, and triggers execution."""
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        # Resolve roles and capture the current memory state
        resolved_role = self._resolve_role_id(target_role) if target_role else None
        current_context = self.memory.get_history() if hasattr(self.memory, "get_history") else []

        # 1. Establish the Source of Truth in SQLite
        try:
            self._initialize_task_in_db(task_id, user_input, current_context)
            logger.info(f"Task {task_id} ingested for client {self.client_id}")
        except Exception as e:
            logger.error(f"Failed to initialize task {task_id} in DB: {e}")
            raise RuntimeError(f"Task ingestion failed: {e}")

        # 2. Delegate execution entirely to the Coordinator Engine
        final_result = await self.engine.process_request(
            user_input=user_input,
            agent_override=resolved_role,
            task_id=task_id,
            context=current_context
        )

        # 3. Record and persist the turn
        self.record_turn(user_input, final_result)
        return final_result

    def _resolve_role_id(self, role_name: str) -> str:
        if hasattr(self.librarian, "resolve_agent_id_for_role"):
            resolved = self.librarian.resolve_agent_id_for_role(role_name)
            if resolved: return resolved
        if hasattr(self.librarian, "resolve_agent_id"):
            resolved = self.librarian.resolve_agent_id(role_name)
            if resolved: return resolved
        return role_name

    def get_role_manifest(self, role_name: str) -> Optional[Dict[str, Any]]:
        resolved_id = self._resolve_role_id(role_name)
        if hasattr(self.librarian, "get_agent_manifest"):
            return self.librarian.get_agent_manifest(resolved_id)
        return None