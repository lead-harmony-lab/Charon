"""
charon/gateway/journal.py
System Version: v1.0.3 | File Revision: 1.0.3

Module: Gateway Task Journal
A persistent, thread-safe journaling and queuing tool for the API Gateway.
Replaces the legacy coordinator journal, serving as the memory ingest buffer for
FastAPI requests before they are dispatched to the execution core.
"""

import asyncio
import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel

from charon.core.state import StateManager, TaskStatus

logger = logging.getLogger("charon.gateway.journal")


class JournalEntry(BaseModel):
    """Strictly typed representation of an enqueued task or gatekeeper decision."""
    task_id: Optional[str] = None
    prompt: Optional[str] = ""
    client_id: Optional[str] = None
    target_role: Optional[str] = None
    agent_override: Optional[str] = None
    routing_hint: Optional[Dict[str, Any]] = None
    approval_id: Optional[str] = None
    decision: Optional[str] = None


class GatewayJournal:
    """
    Memory buffer and persistence bridge for incoming daemon tasks.
    Backed by SQLite (StateManager) for startup recovery.
    """

    def __init__(self, state_manager: StateManager) -> None:
        self.state_mgr = state_manager
        # Initialize as None. Bound lazily inside the active ASGI event loop.
        self._async_queue: Optional[asyncio.Queue[JournalEntry]] = None

    async def initialize(self, auto_recover_running: bool = False) -> int:
        """
        Binds the internal queue to the active event loop and initiates state recovery.
        Must be called from within the application lifespan context manager.
        """
        self._async_queue = asyncio.Queue()
        return await self.initialize_and_recover(auto_recover_running)

    async def initialize_and_recover(self, auto_recover_running: bool = False) -> int:
        """
        On daemon startup, recover pending tasks from the SQLite state DB.
        Interrupted RUNNING tasks are marked FAILED by default to prevent zombie task blockages.
        """
        if self._async_queue is None:
            self._async_queue = asyncio.Queue()

        try:
            unfinished = await self.state_mgr.get_unfinished_tasks()
        except Exception as e:
            logger.error(f"[Gateway Journal] Failed to fetch unfinished tasks during recovery: {e}")
            return 0

        recovered_count = 0

        for task in unfinished:
            try:
                task_id = self._extract_field(task, "task_id")
                raw_status = self._extract_field(task, "status")

                if not task_id:
                    logger.warning("[Gateway Journal] Skipping malformed journal record with missing 'task_id'.")
                    continue

                status_val = raw_status.value if hasattr(raw_status, "value") else str(raw_status)

                # State Reconciliation: Mark crashed RUNNING tasks as FAILED to unblock queue processing
                if status_val == TaskStatus.RUNNING.value:
                    if not auto_recover_running:
                        logger.warning(
                            f"[Gateway Journal] Marking stale interrupted task '{task_id}' as FAILED to prevent deadlock."
                        )
                        await self.state_mgr.update_status(task_id, TaskStatus.FAILED)
                        continue
                    else:
                        logger.warning(
                            f"[Gateway Journal] Re-queueing interrupted task '{task_id}' (RUNNING -> PENDING)."
                        )
                        await self.state_mgr.update_status(task_id, TaskStatus.PENDING)

                # Reconstruct entry for memory queue
                entry = JournalEntry(
                    task_id=task_id,
                    prompt=self._extract_field(task, "prompt", default=""),
                    client_id=self._extract_field(task, "client_id"),
                    target_role=self._extract_field(task, "target_role"),
                    agent_override=self._extract_field(task, "agent_override")
                )

                await self._async_queue.put(entry)
                recovered_count += 1

            except Exception as e:
                logger.error(f"[Gateway Journal] Failed to recover journal entry '{task_id}' during boot: {e}", exc_info=True)

        logger.info(f"[Gateway Journal] Recovery complete. Re-queued {recovered_count} active task(s).")
        return recovered_count

    async def record_and_enqueue(self, task_data: Dict[str, Any]) -> str:
        """
        Logs a new task into the SQLite state DB and pushes it to the active memory queue.
        """
        if self._async_queue is None:
            raise RuntimeError("GatewayJournal queue used before initialization.")

        task_id = task_data.get("task_id")
        prompt = task_data.get("prompt", "")
        client_id = task_data.get("client_id")
        target_role = task_data.get("target_role") or task_data.get("agent_override")
        approval_id = task_data.get("approval_id")

        if task_id and not approval_id:
            await self.state_mgr.create_task(
                task_id=task_id,
                prompt=prompt,
                client_id=client_id,
                agent_override=target_role,
            )

        entry = JournalEntry(**task_data)
        await self._async_queue.put(entry)

        logger.info(f"[Gateway Journal] Item enqueued. (Task ID: {task_id or approval_id}, Queue Depth: {self._async_queue.qsize()})")
        return task_id or approval_id or "unknown"

    async def get(self) -> JournalEntry:
        """Fetch the next pending task for the daemon loop."""
        if self._async_queue is None:
            raise RuntimeError("GatewayJournal queue used before initialization.")
        return await self._async_queue.get()

    def task_done(self) -> None:
        """Acknowledge item ingestion completion in the async queue."""
        if self._async_queue:
            self._async_queue.task_done()

    def qsize(self) -> int:
        """Return active queue depth for telemetry."""
        return self._async_queue.qsize() if self._async_queue else 0

    def clear(self) -> int:
        """Drain all pending memory queue items."""
        if not self._async_queue:
            return 0

        cleared = 0
        while not self._async_queue.empty():
            try:
                self._async_queue.get_nowait()
                self._async_queue.task_done()
                cleared += 1
            except asyncio.QueueEmpty:
                break
        return cleared

    @staticmethod
    def _extract_field(item: Any, key: str, default: Any = None) -> Any:
        """Safely extract field values across dicts, sqlite3.Row, or objects."""
        if isinstance(item, dict):
            return item.get(key, default)
        if hasattr(item, "__getitem__"):
            try:
                return item[key]
            except (KeyError, IndexError, TypeError):
                pass
        return getattr(item, key, default)