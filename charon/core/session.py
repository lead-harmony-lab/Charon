"""
charon/core/session.py
System Version: v0.4.1 | File Revision: 4.1.0

Module: Core session gateway for Charon.
Manages session memory and serves as the declarative ingest boundary for the Core Engine.
Adheres to the Work Contract paradigm by delegating routing and capability evaluation
to the downstream Engine and SkillLibrarian.
"""

import logging
import uuid
from typing import Any, Dict, Optional, TYPE_CHECKING

from charon.core.coordinator.journal import CoordinatorJournal, JournalEntry
from charon.core.skills import SkillLibrarian
from charon.utils.memory import ConversationBuffer

if TYPE_CHECKING:
    from charon.core.engine import OrchestrationEngine

logger = logging.getLogger("Charon.Core.Session")


class SessionGateway:
    """The front desk managing session memory and ingest pass-through to execution chains."""

    def __init__(
        self,
        engine: Optional["OrchestrationEngine"] = None,
        journal: Optional[CoordinatorJournal] = None,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.librarian = librarian or SkillLibrarian.get_instance()
        self.journal = journal or CoordinatorJournal()
        self.memory = ConversationBuffer(max_turns=5)

        if engine is None:
            # Lazy import to break the circular dependency at runtime
            from charon.core.engine import OrchestrationEngine
            self.engine = OrchestrationEngine(
                librarian=self.librarian,
            )
        else:
            self.engine = engine

    def _resolve_role_id(self, role_name: str) -> str:
        """Resolves a system role name to a dynamic database ID via SkillLibrarian."""
        if hasattr(self.librarian, "resolve_agent_id_for_role"):
            resolved = self.librarian.resolve_agent_id_for_role(role_name)
            if resolved:
                return resolved
        if hasattr(self.librarian, "resolve_agent_id"):
            resolved = self.librarian.resolve_agent_id(role_name)
            if resolved:
                return resolved
        return role_name

    def record_turn(self, user_input: str, system_response: str) -> None:
        """Saves a completed interaction turn into short-term conversation history memory."""
        if not system_response:
            return

        resp_str = str(system_response).strip()

        if hasattr(self.memory, "add_turn") and callable(getattr(self.memory, "add_turn")):
            self.memory.add_turn(user_input, resp_str)
        elif hasattr(self.memory, "append") and callable(getattr(self.memory, "append")):
            self.memory.append({"user": user_input, "assistant": resp_str})
        else:
            logger.warning("ConversationBuffer lacks add_turn/append method. Turn not recorded.")

    async def submit_task(
        self,
        user_input: str,
        target_role: Optional[str] = None,
        client_id: Optional[str] = "session_gateway"
    ) -> Any:
        """
        Ingests a high-level user objective, enqueues it via the CoordinatorJournal,
        and kicks off the Engine execution loop.
        """
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        # 1. Create a strictly typed payload for the Journal
        entry = JournalEntry(
            task_id=task_id,
            prompt=user_input,
            target_role=self._resolve_role_id(target_role) if target_role else None,
            client_id=client_id,
            context_history=self.memory.get_history() if hasattr(self.memory, "get_history") else []
        )

        # 2. Enqueue the declarative task
        await self.journal.enqueue(entry)
        logger.info(f"Task ingested and journaled: {task_id}")

        # 3. Delegate execution entirely to the Coordinator Engine
        final_result = await self.engine.process_request(
            user_input=user_input,
            agent_override=target_role,
            task_id=task_id
        )

        # 4. Record the turn for future context
        self.record_turn(user_input, final_result)
        return final_result

    def get_role_manifest(self, role_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the high-level capability manifest for a system role.
        """
        resolved_id = self._resolve_role_id(role_name)
        if hasattr(self.librarian, "get_agent_manifest"):
            return self.librarian.get_agent_manifest(resolved_id)
        return None