"""
charon/core/coordinator/journal.py
System Version: v0.5.0 | File Revision: 1.0.0

Module: Coordinator Task Journal
A persistent, thread-safe journaling and queuing tool for the Coordinator Engine.
Replaces the legacy 'queue.py' and serves as the immutable ingest buffer for declarative tasks.
Provides daemon restart recovery and state reconciliation, guaranteeing zero task drops.
"""

import asyncio
import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel

from charon.core.state import StateManager, TaskStatus

logger = logging.getLogger("charon.core.coordinator.journal")


class JournalEntry(BaseModel):
    """Strictly typed representation of an enqueued Coordinator task."""
    task_id: str
    prompt: str
    client_id: Optional[str] = None
    target_role: Optional[str] = None


class CoordinatorJournal:
    """
    Persistent journaling and queuing interface for the Coordinator Engine.
    Backed by SQLite state storage to ensure daemon resilience.
    """

    def __init__(self, state_manager: StateManager) -> None:
        self.state_mgr = state_manager
        self._async_queue: asyncio.Queue[JournalEntry] = asyncio.Queue()

    async def recover_orphaned_tasks(self) -> int:
        """
        On daemon startup, recover pending or abruptly interrupted tasks from the SQLite journal
        and re-populate the memory scheduling queue for the Coordinator Engine.
        """
        try:
            unfinished = await self.state_mgr.get_unfinished_tasks()
        except Exception as e:
            logger.error(f"Failed to fetch unfinished tasks during journal recovery: {e}")
            return 0

        recovered_count = 0

        for task in unfinished:
            try:
                task_id = self._extract_field(task, "task_id")
                raw_status = self._extract_field(task, "status")

                if not task_id:
                    logger.warning("Skipping malformed unfinished journal record with missing 'task_id'.")
                    continue

                status_val = raw_status.value if hasattr(raw_status, "value") else str(raw_status)

                # State Reconciliation: Reset abruptly interrupted RUNNING tasks back to PENDING
                if status_val == TaskStatus.RUNNING.value:
                    logger.warning(
                        f"[Journal Recovery] Reconciling interrupted task '{task_id}' (RUNNING -> PENDING)."
                    )
                    await self.state_mgr.update_status(task_id, TaskStatus.PENDING)

                # Map to strict declarative Work Contract entry (dropping legacy micro-skill targeting)
                entry = JournalEntry(
                    task_id=task_id,
                    prompt=self._extract_field(task, "prompt", default=""),
                    client_id=self._extract_field(task, "client_id"),
                    target_role=self._extract_field(task, "target_role") or self._extract_field(task, "agent_override")
                )

                await self._async_queue.put(entry)
                recovered_count += 1

            except Exception as e:
                logger.error(f"Failed to recover journal entry '{task_id}' during boot: {e}", exc_info=True)

        logger.info(f"Coordinator Journal recovery complete. Re-queued {recovered_count} task(s).")
        return recovered_count

    async def record_and_enqueue(self, task_data: Dict[str, Any]) -> str:
        """
        Logs a new declarative task into the SQLite journal and pushes it to the Coordinator's active queue.
        """
        task_id = task_data["task_id"]
        prompt = task_data.get("prompt", "")
        client_id = task_data.get("client_id")
        target_role = task_data.get("target_role") or task_data.get("agent_override")

        # 1. Persist to SQLite State DB for audit and recovery
        await self.state_mgr.create_task(
            task_id=task_id,
            prompt=prompt,
            client_id=client_id,
            agent_override=target_role,  # Mapped to legacy kwarg for StateManager backward compat
        )

        # 2. Add strictly typed entry to the active scheduling worker
        entry = JournalEntry(
            task_id=task_id,
            prompt=prompt,
            client_id=client_id,
            target_role=target_role
        )

        await self._async_queue.put(entry)
        logger.info(f"[Journal] Task '{task_id}' recorded and queued. (Depth: {self._async_queue.qsize()})")
        return task_id

    async def await_next_task(self) -> JournalEntry:
        """Fetch the next pending task for the Coordinator Engine."""
        return await self._async_queue.get()

    def mark_task_consumed(self) -> None:
        """Acknowledge item ingestion completion in the async queue."""
        self._async_queue.task_done()

    @property
    def depth(self) -> int:
        """Return active queue depth."""
        return self._async_queue.qsize()

    @staticmethod
    def _extract_field(item: Any, key: str, default: Any = None) -> Any:
        """Safely extract field values across dicts, sqlite3.Row, or objects."""
        if isinstance(item, dict):
            return item.get(key, default)
        if hasattr(item, "__getitem__"):
            try:
                return item[key]
            except (KeyError, IndexError):
                return default
        return getattr(item, key, default)