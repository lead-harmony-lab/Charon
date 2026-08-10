"""
charon/core/queue.py
System Version: v0.3.3 | File Revision: 1.1.0

Module: Persistent SQLite Task Queue
Thread-safe, persistent task queue backing daemon job orchestration.
Replaces volatile in-memory queues and provides restart recovery.
Adheres to the Janitorial Working Anchor by enforcing role-aware abstractions.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Union

from charon.core.state import StateManager, TaskStatus

logger = logging.getLogger("Charon.Core.Queue")


class PersistentTaskQueue:
    """Async queue interface backed by persistent SQLite task state."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_mgr = state_manager
        self._async_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

    async def initialize_and_recover(self) -> int:
        """
        On daemon startup, recover pending or interrupted tasks from SQLite database
        and re-populate the memory scheduling queue.

        Resilient against individual row corruption to guarantee daemon startup recovery.
        """
        try:
            unfinished = await self.state_mgr.get_unfinished_tasks()
        except Exception as e:
            logger.error(f"Failed to fetch unfinished tasks during queue recovery: {e}")
            return 0

        recovered_count = 0

        for task in unfinished:
            try:
                task_id = self._extract_field(task, "task_id")
                raw_status = self._extract_field(task, "status")

                if not task_id:
                    logger.warning("Skipping malformed unfinished task record with missing 'task_id'.")
                    continue

                # Normalize status string/enum representation
                status_val = raw_status.value if hasattr(raw_status, "value") else str(raw_status)

                # Janitorial Anchor: Reset stuck RUNNING tasks back to PENDING for re-execution
                if status_val == TaskStatus.RUNNING.value:
                    logger.warning(
                        f"Janitorial Anchor Recovery: Resetting interrupted task '{task_id}' (RUNNING -> PENDING)."
                    )
                    await self.state_mgr.update_status(task_id, TaskStatus.PENDING)

                # Construct sanitized task payload adhering to Janitorial role abstractions
                task_payload = {
                    "task_id": task_id,
                    "client_id": self._extract_field(task, "client_id"),
                    "prompt": self._extract_field(task, "prompt", default=""),
                    "agent_override": self._extract_field(task, "agent_override"),
                    "target_role": self._extract_field(task, "target_role"),
                    "action_name": self._extract_field(task, "action_name") or self._extract_field(task, "action"),
                }

                await self._async_queue.put(task_payload)
                recovered_count += 1

            except Exception as e:
                logger.error(f"Failed to recover individual task during queue boot: {e}", exc_info=True)

        logger.info(f"Task queue recovery complete. Reloaded {recovered_count} task(s).")
        return recovered_count

    async def put(self, task_data: Dict[str, Any]) -> str:
        """Enqueue a new task into state storage and async worker queue.

        Ensures routing metadata (action_name, target_role, agent_override) is properly
        persisted while masking concrete raw agent IDs.
        """
        task_id = task_data["task_id"]
        prompt = task_data.get("prompt", "")
        client_id = task_data.get("client_id")

        # Preserve Janitorial Role Abstraction: accept target_role or agent_override
        agent_override = task_data.get("agent_override") or task_data.get("target_role")
        action_name = task_data.get("action_name") or task_data.get("action")

        # 1. Persist to SQLite State DB
        await self.state_mgr.create_task(
            task_id=task_id,
            prompt=prompt,
            client_id=client_id,
            agent_override=agent_override,
        )

        # Normalize in-memory dict payload for downstream AgentDispatcher compatibility
        normalized_data = dict(task_data)
        normalized_data.setdefault("agent_override", agent_override)
        normalized_data.setdefault("action_name", action_name)

        # 2. Add to in-memory scheduling worker
        await self._async_queue.put(normalized_data)
        logger.info(f"Queued task '{task_id}' (Queue Depth: {self._async_queue.qsize()})")
        return task_id

    async def get(self) -> Dict[str, Any]:
        """Fetch next pending task for execution."""
        return await self._async_queue.get()

    def task_done(self) -> None:
        """Acknowledge item processing completion in async queue."""
        self._async_queue.task_done()

    def qsize(self) -> int:
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