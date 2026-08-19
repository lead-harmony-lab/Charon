"""
charon/concierge/scheduler.py
System Version: v2.4.0

Module: Temporal Task Scheduler
Provides Charon with a non-blocking internal clock to manage background telemetry,
heuristic reflections (sleep cycles), and user-requested time-delayed tasks.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Callable, Coroutine, Any, Dict, Optional

logger = logging.getLogger("Charon.Concierge.Scheduler")

class ScheduledTask:
    """Represents a single temporal task."""
    def __init__(
        self,
        func: Callable[..., Coroutine[Any, Any, Any]],
        run_at: datetime,
        is_recurring: bool = False,
        interval_seconds: Optional[int] = None,
        *args,
        **kwargs
    ):
        self.id = str(uuid.uuid4())
        self.func = func
        self.run_at = run_at
        self.is_recurring = is_recurring
        self.interval_seconds = interval_seconds
        self.args = args
        self.kwargs = kwargs

class ConciergeScheduler:
    """Asynchronous background scheduler for daemon operations."""

    def __init__(self):
        self.tasks: Dict[str, ScheduledTask] = {}
        self._is_running = False
        self._task_runner: Optional[asyncio.Task] = None

    def start(self):
        """Ignites the internal clock."""
        if not self._is_running:
            self._is_running = True
            self._task_runner = asyncio.create_task(self._tick())
            logger.info("Concierge Temporal Scheduler initialized and ticking.")

    def stop(self):
        """Halts the internal clock."""
        self._is_running = False
        if self._task_runner:
            self._task_runner.cancel()
            logger.info("Concierge Temporal Scheduler halted.")

    def schedule_at(self, run_at: datetime, func: Callable, *args, **kwargs) -> str:
        """Schedules a one-off task for a specific future time."""
        task = ScheduledTask(func, run_at, False, None, *args, **kwargs)
        self.tasks[task.id] = task
        logger.debug(f"Task {task.id} scheduled for {run_at.isoformat()}")
        return task.id

    def schedule_interval(self, interval_seconds: int, func: Callable, *args, **kwargs) -> str:
        """Schedules a recurring background task (e.g., telemetry heartbeat)."""
        run_at = datetime.now() + timedelta(seconds=interval_seconds)
        task = ScheduledTask(func, run_at, True, interval_seconds, *args, **kwargs)
        self.tasks[task.id] = task
        logger.debug(f"Recurring task {task.id} scheduled every {interval_seconds}s")
        return task.id

    def cancel_task(self, task_id: str):
        """Removes a task from the queue."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            logger.debug(f"Task {task_id} cancelled.")

    async def _tick(self):
        """The core clock loop. Evaluates and fires tasks."""
        while self._is_running:
            now = datetime.now()
            tasks_to_run = []

            # Identify tasks whose time has come
            for task_id, task in list(self.tasks.items()):
                if now >= task.run_at:
                    tasks_to_run.append(task)
                    if task.is_recurring and task.interval_seconds:
                        task.run_at = now + timedelta(seconds=task.interval_seconds)
                    else:
                        del self.tasks[task_id]

            # Execute tasks concurrently without blocking the clock
            for task in tasks_to_run:
                asyncio.create_task(self._execute_task(task))

            # Sleep briefly to prevent CPU thrashing
            await asyncio.sleep(1)

    async def _execute_task(self, task: ScheduledTask):
        """Wraps task execution in error handling."""
        try:
            if asyncio.iscoroutinefunction(task.func):
                await task.func(*task.args, **task.kwargs)
            else:
                # If a synchronous function is passed, run it in a thread to avoid blocking the async loop
                await asyncio.to_thread(task.func, *task.args, **task.kwargs)
        except Exception as e:
            logger.error(f"Error executing scheduled task {task.id}: {e}")