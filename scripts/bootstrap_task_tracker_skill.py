"""
scripts/bootstrap_task_tracker_skill.py
Programmatically constructs and promotes task_tracker_manage using Charon Librarian.
"""

import json
import logging
from pathlib import Path

from charon.cli.librarian.database import run_sync
from charon.cli.librarian.ingestion import run_create
from charon.cli.librarian.lifecycle import run_promote
from charon.cli.librarian.permissions import run_permission_change

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Charon.Librarian.Bootstrap")

SKILL_ID = "task_tracker_manage"

PLUGIN_CODE = '''"""
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


def execute_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if action_name == "add_task":
        return handle_add_task(params)
    elif action_name == "complete_task":
        return handle_complete_task(params)

    raise ValueError(f"Action '{action_name}' is not supported by skill 'task_tracker_manage'.")
'''


def bootstrap_skill():
    logger.info(f"1. Scaffolding skill '{SKILL_ID}' in Librarian staging...")
    run_create(skill_id=SKILL_ID, category="System")

    staged_dir = Path(f"charon/skills/staged/{SKILL_ID}")
    staged_dir.mkdir(parents=True, exist_ok=True)

    # Corrected Manifest with stage='Staged' explicit declaration
    manifest_data = {
        "skill_id": SKILL_ID,
        "version": "1.0.0",
        "description": "Allows Charon agents to manage top bar ticker tasks.",
        "category": "System",
        "author": "Charon Librarian",
        "stage": "Staged",
        "shelf_tags": ["tasks", "ticker", "gnome_ui"],
        "system_requirements": [],
        "supported_actions": {
            "add_task": "Add or pin a new task (title, priority, task_id) to the top bar ticker loop.",
            "complete_task": "Mark an existing task_id as completed to remove it from ticker rotation.",
        },
    }

    manifest_path = staged_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    # Write actual implementation code to plugin.py
    plugin_path = staged_dir / "plugin.py"
    with open(plugin_path, "w", encoding="utf-8") as f:
        f.write(PLUGIN_CODE)

    logger.info("2. Syncing updated manifest into SQLite...")
    run_sync()

    logger.info("3. Authorizing skill access for agent 'The_Engineer' and 'Generalist'...")
    run_permission_change(skill_id=SKILL_ID, agent_name="The_Engineer", action="grant")
    run_permission_change(skill_id=SKILL_ID, agent_name="Generalist", action="grant")

    logger.info("4. Promoting skill from staged quarantine -> dynamic production...")
    res = run_promote(skill_id=SKILL_ID)

    if res == 0:
        logger.info("✅ Skill 'task_tracker_manage' successfully installed, authorized, and promoted!")
    else:
        logger.error("❌ Promotion failed.")


if __name__ == "__main__":
    bootstrap_skill()