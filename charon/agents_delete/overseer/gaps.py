"""
charon/agents/overseer/gaps.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Skill gap detection, IPC daemon notification, and automated scaffolding.
"""

import asyncio
import json
import logging
import subprocess
from typing import Any, Dict

import httpx

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("charon.agents.overseer.gaps")

DAEMON_IPC_URL = "http://127.0.0.1:8000/api/v1/internal/events/gap-detected"


def sweep_and_resolve_gaps_sync() -> Dict[str, Any]:
    """Sweeps for open skill gaps, pings the daemon, and triggers charon-forge."""
    if not STATE_DB_PATH.exists():
        return {"status": "skipped", "reason": "charon_state.db not found"}

    resolved_count = 0
    failed_count = 0

    with get_connection(STATE_DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT gap_id, action_name, requesting_agent, context_json FROM skill_gaps WHERE status = 'open'"
        )
        open_gaps = cursor.fetchall()

        if not open_gaps:
            return {
                "status": "completed",
                "gaps_resolved": 0,
                "message": "No open gaps found.",
            }

        for gap in open_gaps:
            gap_id = gap["gap_id"]
            action_name = gap["action_name"]
            agent = gap["requesting_agent"]

            try:
                context = (
                    json.loads(gap["context_json"])
                    if gap["context_json"]
                    else {}
                )
            except json.JSONDecodeError:
                context = {}

            logger.warning(
                f"🚨 [OVERSEER] Open gap intercepted: '{action_name}' (ID: {gap_id})"
            )

            # 1. Notify Daemon via local IPC
            payload = {
                "gap_id": gap_id,
                "action_name": action_name,
                "requesting_agent": agent,
                "context": context,
            }
            try:
                httpx.post(DAEMON_IPC_URL, json=payload, timeout=2.0)
            except httpx.RequestError as e:
                logger.warning(
                    f"[OVERSEER] Daemon IPC unreachable (Daemon offline?): {e}"
                )

            # 2. Trigger automated Forge scaffolding
            inferred_skill_id = f"{action_name}_skill".replace("__", "_")
            try:
                subprocess.run(
                    [
                        "charon-forge",
                        "scaffold",
                        "--skill-id",
                        inferred_skill_id,
                        "--action",
                        action_name,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )

                # 3. Mark as in-progress
                cursor.execute(
                    "UPDATE skill_gaps SET status = 'in_progress' WHERE gap_id = ?",
                    (gap_id,),
                )
                resolved_count += 1
                logger.info(
                    f"✓ [OVERSEER] Gap #{gap_id} Scaffolded & marked 'in_progress'."
                )

            except subprocess.CalledProcessError as e:
                logger.error(
                    f"❌ [OVERSEER] Forge execution failed for {inferred_skill_id}: {e.stderr}"
                )
                failed_count += 1

    return {
        "status": "completed",
        "gaps_scaffolded": resolved_count,
        "gaps_failed": failed_count,
    }


async def resolve_skill_gaps() -> Dict[str, Any]:
    """Asynchronously sweeps and resolves open skill gaps."""
    return await asyncio.to_thread(sweep_and_resolve_gaps_sync)