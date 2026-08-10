"""
charon/gateway/ticker/providers/task_tracker.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Task Tracker ticker provider with priority-weighted display frequency rules.
"""

import logging
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from charon.gateway.ticker.base import BaseTickerProvider, TickerSlide

logger = logging.getLogger("Charon.Gateway.TickerProvider.TaskTracker")


class TaskItem(BaseModel):
    """Schema representing a tracked task item."""

    id: str = Field(..., description="Unique task identifier.")
    title: str = Field(..., description="Short descriptive title of the task.")
    priority: Literal["high", "medium", "low"] = Field(
        default="low",
        description="Task priority level: 'high', 'medium', or 'low'."
    )
    pinned: bool = Field(
        default=True,
        description="Whether this task should be displayed on the ticker."
    )
    completed: bool = Field(
        default=False,
        description="Completion status of the task."
    )


class TaskTrackerTickerProvider(BaseTickerProvider):
    """
    Plug-and-play TickerProvider for task lists with frequency-weighted rules:
    - High Priority: Pinned and displayed with top frequency (~75% of priority slots).
    - Medium Priority: Pinned and displayed with lower frequency (~25% of priority slots).
    - Low Priority: Never individually pinned. Included in total task summary counts.
    """

    def __init__(self, db_client: Optional[Any] = None) -> None:
        super().__init__(provider_id="task_tracker", enabled=True)
        self.db_client = db_client
        self._tasks: Dict[str, TaskItem] = {}
        self._cycle_counter: int = 0
        self._high_index: int = 0
        self._med_index: int = 0

    def add_task(self, task: TaskItem) -> None:
        """Add or update a task item in the provider memory cache."""
        self._tasks[task.id] = task
        logger.debug(f"TaskTracker: Added/Updated task '{task.id}' [{task.priority.upper()}]")

    def complete_task(self, task_id: str) -> bool:
        """Mark a task as completed so it drops off active ticker rotation."""
        if task_id in self._tasks:
            self._tasks[task_id].completed = True
            logger.debug(f"TaskTracker: Marked task '{task_id}' as completed.")
            return True
        return False

    async def _fetch_active_tasks(self) -> List[TaskItem]:
        """
        Fetch incomplete tasks. Can be extended to query SQLite directly.
        """
        if self.db_client:
            # SQLite / DB extraction hook can be implemented here
            pass
        return [t for t in self._tasks.values() if not t.completed]

    async def get_slides(self) -> List[TickerSlide]:
        tasks = await self._fetch_active_tasks()
        if not tasks:
            return []

        # Filter by priority and pin status
        high_tasks = [t for t in tasks if t.priority == "high" and t.pinned]
        med_tasks = [t for t in tasks if t.priority == "medium" and t.pinned]
        low_tasks = [t for t in tasks if t.priority == "low"]

        slides: List[TickerSlide] = []
        self._cycle_counter += 1

        # ----------------------------------------------------------------------
        # Priority Weighted Frequency Allocation:
        # - 3 out of 4 cycles (75%): Yield High priority task (if available).
        # - 1 out of 4 cycles (25%): Interject Medium priority task (if available).
        # - Fallbacks ensure continuous display if only one category exists.
        # ----------------------------------------------------------------------
        selected_task: Optional[TaskItem] = None
        is_medium_turn = (self._cycle_counter % 4 == 0)

        if is_medium_turn and med_tasks:
            self._med_index %= len(med_tasks)
            selected_task = med_tasks[self._med_index]
            self._med_index = (self._med_index + 1) % len(med_tasks)
        elif high_tasks:
            self._high_index %= len(high_tasks)
            selected_task = high_tasks[self._high_index]
            self._high_index = (self._high_index + 1) % len(high_tasks)
        elif med_tasks:
            self._med_index %= len(med_tasks)
            selected_task = med_tasks[self._med_index]
            self._med_index = (self._med_index + 1) % len(med_tasks)

        # 1. Pinned Task Slide (High or Medium)
        if selected_task:
            is_high = selected_task.priority == "high"
            prefix = "🔥 [HIGH]" if is_high else "📌 [MED]"

            slides.append(
                TickerSlide(
                    provider_id=self.provider_id,
                    display_text=f"{prefix} {selected_task.title}",
                    priority=10 if is_high else 8,  # >0 triggers priority takeover in TickerEngine
                    duration_seconds=5,
                    data=selected_task.model_dump(),
                )
            )

        # 2. General Summary Task Slide (Standard round-robin rotation, priority=0)
        total_active = len(tasks)
        high_count = len([t for t in tasks if t.priority == "high"])
        med_count = len([t for t in tasks if t.priority == "medium"])
        low_count = len(low_tasks)

        slides.append(
            TickerSlide(
                provider_id=self.provider_id,
                display_text=f"📋 Tasks: {total_active} ({high_count}H / {med_count}M / {low_count}L)",
                priority=0,
                duration_seconds=5,
                data={
                    "total": total_active,
                    "high": high_count,
                    "medium": med_count,
                    "low": low_count,
                },
            )
        )

        return slides