"""
Plugin entrypoint module for task_tracker_manage.
Connects agent action invocations to the active TaskTrackerTickerProvider.
"""

import uuid
from typing import Any, Dict
from charon.gateway.ticker.engine import ticker_engine
from charon.gateway.ticker.providers.task_tracker import TaskTrackerTickerProvider, TaskItem


def _get_task_provider() -> TaskTrackerTickerProvider:
    """Retrieve or lazy-instantiate the task tracker provider from the TickerEngine."""
    provider = ticker_engine._providers.get("task_tracker")
    if not provider:
        provider = TaskTrackerTickerProvider()
        ticker_engine.register_provider(provider)
    return provider  # type: ignore


def handle_add_task(params: Dict[str, Any]) -> Dict[str, Any]:
    title = params.get("title")
    if not title:
        return {"status": "error", "message": "Missing required parameter 'title'."}

    priority = params.get("priority", "medium").lower()
    if priority not in ("high", "medium", "low"):
        priority = "medium"

    task_id = params.get("task_id") or f"task-{uuid.uuid4().hex[:6]}"

    provider = _get_task_provider()
    task = TaskItem(
        id=task_id,
        title=title,
        priority=priority,
        pinned=True,
        completed=False,
    )
    provider.add_task(task)

    return {
        "status": "success",
        "task_id": task_id,
        "message": f"Task '{title}' [{priority.upper()}] posted to top bar ticker.",
    }


def handle_complete_task(params: Dict[str, Any]) -> Dict[str, Any]:
    task_id = params.get("task_id")
    if not task_id:
        return {"status": "error", "message": "Missing required parameter 'task_id'."}

    provider = _get_task_provider()
    success = provider.complete_task(task_id)

    if success:
        return {
            "status": "success",
            "task_id": task_id,
            "message": f"Task '{task_id}' marked completed and removed from ticker.",
        }
    return {
        "status": "error",
        "message": f"Task '{task_id}' was not found in active ticker memory.",
    }


def handle_list_tasks(params: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve all active tasks from the ticker provider memory."""
    provider = _get_task_provider()

    # Access task collection safely
    if hasattr(provider, "get_active_tasks"):
        raw_tasks = provider.get_active_tasks()
    elif hasattr(provider, "tasks"):
        raw_tasks = list(provider.tasks.values()) if isinstance(provider.tasks, dict) else provider.tasks
    else:
        raw_tasks = []

    formatted_tasks = []
    for t in raw_tasks:
        if getattr(t, "completed", False):
            continue
        formatted_tasks.append({
            "id": getattr(t, "id", "unknown"),
            "title": getattr(t, "title", str(t)),
            "priority": getattr(t, "priority", "medium"),
            "pinned": getattr(t, "pinned", True),
        })

    return {
        "status": "success",
        "task_count": len(formatted_tasks),
        "tasks": formatted_tasks,
        "message": f"Found {len(formatted_tasks)} active task(s) in top bar ticker.",
    }


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if action_name == "add_task":
        return handle_add_task(params)
    elif action_name == "complete_task":
        return handle_complete_task(params)
    elif action_name == "list_tasks":
        return handle_list_tasks(params)

    raise ValueError(f"Action '{action_name}' is not supported by skill 'task_tracker_manage'.")