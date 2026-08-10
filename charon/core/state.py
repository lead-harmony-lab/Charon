"""
charon/core/state.py
System Version: v0.3.3 | File Revision: 1.4.0

Module: Persistent Task State Machine & Idle Ticker Feed Coordinator
Tracks task execution status, execution plans, step outputs, Gatekeeper approval state,
and idle notification ticker items across daemon restarts via DAL Repositories.
Adheres to the Janitorial Working Anchor by enforcing role-aware metadata & resilient state transitions.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import uuid

from charon.config.paths import STATE_DB_PATH
from charon.db.repositories import TaskRepository, TickerRepository

logger = logging.getLogger("Charon.Core.State")


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StateManager:
    """Thread-safe state machine wrapper coordinating persistence via DAL Repositories."""

    def __init__(self, db_path: Optional[Union[Path, str]] = None) -> None:
        # 1. Fallback to canonical STATE_DB_PATH if not provided
        target_path = Path(db_path) if db_path else STATE_DB_PATH

        # 2. Janitorial Guard: Protect against directory paths passed by callers
        if target_path.is_dir():
            logger.warning(
                f"StateManager received directory path '{target_path}'. "
                f"Auto-correcting to STATE_DB_PATH '{STATE_DB_PATH}'."
            )
            target_path = STATE_DB_PATH

        self.db_path = target_path
        self.task_repo = TaskRepository(self.db_path)
        self.ticker_repo = TickerRepository(self.db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize state tables via repositories."""
        try:
            self.task_repo.ensure_schema()
            self.ticker_repo.ensure_schema()
            logger.info(
                f"StateManager initialized with DAL repositories at: {self.db_path}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize state database schema at '{self.db_path}': {e}")
            raise

    # --------------------------------------------------------------------------
    # Task Management Methods
    # --------------------------------------------------------------------------

    async def create_task(
        self,
        task_id: str,
        prompt: str,
        client_id: Optional[str] = None,
        agent_override: Optional[str] = None,
        target_role: Optional[str] = None,
        action_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Insert new task entry into state ledger.

        Janitorial Working Anchor Compliance:
        - Normalizes role-based abstractions (`target_role` vs `agent_override`).
        - Captures `action_name` for dynamic route auditing.
        """
        # Preserve Janitorial Role Abstraction across parameter aliases
        effective_role = agent_override or target_role or kwargs.get("action")
        effective_action = action_name or kwargs.get("action_name") or kwargs.get("action")

        await asyncio.to_thread(
            self.task_repo.create_task,
            task_id=task_id,
            prompt=prompt,
            status=TaskStatus.PENDING.value,
            client_id=client_id,
            agent_override=effective_role,
        )

        return {
            "task_id": task_id,
            "status": TaskStatus.PENDING.value,
            "prompt": prompt,
            "client_id": client_id,
            "agent_override": effective_role,
            "target_role": target_role or effective_role,
            "action_name": effective_action,
        }

    async def update_status(
        self,
        task_id: str,
        status: Union[TaskStatus, str],
        error_message: Optional[str] = None,
        approval_id: Optional[str] = None,
    ) -> None:
        """Update task status and associated error or approval metadata safely."""
        status_val = status.value if isinstance(status, Enum) else str(status)

        await asyncio.to_thread(
            self.task_repo.update_status,
            task_id=task_id,
            status=status_val,
            error_message=error_message,
            approval_id=approval_id,
        )

    async def save_plan(
        self, task_id: str, plan_steps: List[Dict[str, Any]]
    ) -> None:
        """Persist generated orchestration execution plan with resilient JSON encoding."""
        try:
            plan_str = json.dumps(plan_steps, default=str)
        except Exception as e:
            logger.error(f"Failed to serialize plan steps for task '{task_id}': {e}")
            plan_str = json.dumps([{"error": "Serialization failed", "details": str(e)}])

        await asyncio.to_thread(
            self.task_repo.save_plan,
            task_id=task_id,
            plan_str=plan_str,
            total_steps=len(plan_steps),
        )

    async def update_step_progress(
        self,
        task_id: str,
        step_index: int,
        step_results: Dict[str, Any],
    ) -> None:
        """Update current step execution progress and store step output results."""
        try:
            results_str = json.dumps(step_results, default=str)
        except Exception as e:
            logger.error(f"Failed to serialize step results for task '{task_id}': {e}")
            results_str = json.dumps({"error": "Serialization failed", "details": str(e)})

        await asyncio.to_thread(
            self.task_repo.update_step_progress,
            task_id=task_id,
            step_index=step_index,
            results_str=results_str,
        )

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve task state dictionary by ID."""
        return await asyncio.to_thread(self.task_repo.get_task, task_id)

    async def get_unfinished_tasks(self) -> List[Dict[str, Any]]:
        """Fetch tasks interrupted during RUNNING or AWAITING_APPROVAL states for crash recovery."""
        target_statuses = [
            TaskStatus.PENDING.value,
            TaskStatus.RUNNING.value,
            TaskStatus.AWAITING_APPROVAL.value,
        ]
        return await asyncio.to_thread(
            self.task_repo.get_unfinished_tasks, target_statuses
        )

    # --------------------------------------------------------------------------
    # Idle Notification Ticker Methods
    # --------------------------------------------------------------------------

    async def add_ticker_item(
        self,
        message: str,
        category: str = "COMPLETED_TASK",
        ttl_minutes: int = 120,
    ) -> str:
        """Add a notification ticker item to be displayed in top bar during daemon idle state."""
        item_id = f"tick-{uuid.uuid4().hex[:6]}"
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=ttl_minutes)

        await asyncio.to_thread(
            self.ticker_repo.add_ticker_item,
            item_id=item_id,
            category=category,
            message=message,
            created_at_iso=now.isoformat(),
            expires_at_iso=expires.isoformat(),
        )
        logger.debug(
            f"Added idle ticker item [{item_id}]: '{message}' ({category})"
        )
        return item_id

    async def get_active_ticker_items(
        self, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Fetch undismissed and non-expired ticker items for heartbeat rotation."""
        now_iso = datetime.now(timezone.utc).isoformat()
        return await asyncio.to_thread(
            self.ticker_repo.get_active_ticker_items,
            now_iso=now_iso,
            limit=limit,
        )

    async def dismiss_ticker_item(self, item_id: str) -> None:
        """Dismiss a ticker item so it no longer appears in top bar rotations."""
        await asyncio.to_thread(self.ticker_repo.dismiss_ticker_item, item_id)