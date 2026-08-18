"""
charon/db/repositories/coordinator.py
System Version: v0.2.1 | File Revision: 1.2.1

Repository bridging the Coordinator Engine to the zero-trust SQLite state.
Handles task polling, Level 0 capability audits, Level 1 contract minting,
and zero-trust ephemeral key revocation (The Burn & Sweeper).
"""

import json
import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from charon.db.connection import get_connection

logger = logging.getLogger(__name__)


class CoordinatorStateRepository:
    """
    Manages the physical database interactions for the Coordinator Engine.
    Executes all queries within transactional context managers.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path

    # ==========================================
    # 1. TASK INGESTION & PLANNING
    # ==========================================
    def get_pending_tasks(self) -> List[sqlite3.Row]:
        """Polls for tasks that require planning or execution."""
        query = """
            SELECT task_id, prompt, status, plan_json, current_step_index 
            FROM task_state 
            WHERE status IN ('PENDING', 'PLANNING', 'RUNNING')
            ORDER BY created_at ASC;
        """
        with get_connection(self.db_path, read_only=True) as conn:
            return conn.execute(query).fetchall()

    def update_task_plan(self, task_id: str, plan_json: Dict[str, Any]) -> None:
        """Saves the Planner's DAG blueprint and advances the task status."""
        query = """
            UPDATE task_state 
            SET plan_json = ?, status = 'RUNNING', updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?;
        """
        with get_connection(self.db_path) as conn:
            conn.execute(query, (json.dumps(plan_json), task_id))

    def update_task_status(
        self, task_id: str, status: str, results_json: Optional[Dict[str, Any]] = None
    ) -> None:
        """Updates terminal states and stores final results."""
        query = """
            UPDATE task_state 
            SET status = ?, results_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?;
        """
        results_str = json.dumps(results_json) if results_json else None
        with get_connection(self.db_path) as conn:
            conn.execute(query, (status, results_str, task_id))

    # ==========================================
    # 2. THE KEY MAKER (ZERO-TRUST MINTING)
    # ==========================================
    def audit_level_0_permission_strict(self, agent_id: str, skill_id: str) -> bool:
        """
        THE LAW (STRICT): Verifies base physical capability AND legal role authority.
        """
        query = """
            SELECT 1 
            FROM agent_skill_map asm
            JOIN system_roles sr ON asm.agent_id = sr.agent_id
            JOIN role_permission_groups rpg ON sr.role_name = rpg.role_name
            JOIN permission_registry pr ON rpg.group_id = pr.group_id
            JOIN skill_permissions sp ON pr.perm_id = sp.perm_id
            WHERE asm.agent_id = ? 
              AND asm.skill_id = ? 
              AND sp.skill_id = ?;
        """
        with get_connection(self.db_path, read_only=True) as conn:
            # Bind skill_id twice to fulfill both asm.skill_id and sp.skill_id placeholders
            result = conn.execute(query, (agent_id, skill_id, skill_id)).fetchone()
            return bool(result)

    def mint_ephemeral_contract(
        self,
        task_id: str,
        agent_id: str,
        skill_id: str,
        authorized_tools: Optional[List[str]] = None,
        rate_limit: int = 10,
        token_bound: int = 8000,
    ) -> str:
        """
        THE CONTRACT: Mints a temporary key binding an agent to a tool for a specific task.
        """
        contract_id = f"cnt_{uuid.uuid4().hex[:12]}"
        contract_name = f"AutoMint_{agent_id}_{skill_id}"

        scope_limits_json = json.dumps({
            "authorized_tools": authorized_tools or []
        })

        query = """
            INSERT INTO contract_policies (
                contract_id, contract_name, task_id, agent_id, skill_id, 
                scope_limits, rate_limit_rpm, token_boundary, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1);
        """

        with get_connection(self.db_path) as conn:
            conn.execute(
                query,
                (
                    contract_id,
                    contract_name,
                    task_id,
                    agent_id,
                    skill_id,
                    scope_limits_json,
                    rate_limit,
                    token_bound,
                ),
            )
            logger.info(f"Minted ephemeral contract {contract_id} for {agent_id} -> {skill_id}")
            return contract_id

    # ==========================================
    # 3. THE BURN & PRUNING ENGINE
    # ==========================================
    def burn_task_contracts(self, task_id: str) -> int:
        """
        THE BURN: Instantly revokes all keys associated with a task when it completes/fails.
        Returns the count of revoked contract policies.
        """
        query = "DELETE FROM contract_policies WHERE task_id = ?;"
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(query, (task_id,))
            revoked_count = cursor.rowcount
            if revoked_count > 0:
                logger.info(f"Burned {revoked_count} ephemeral contracts for task {task_id}.")
            return revoked_count

    def sweep_stale_tasks(self, days_old: int = 7) -> List[str]:
        """
        THE SWEEPER: Identifies and deletes terminal/stale task records updated prior to threshold.
        Due to PRAGMA foreign_keys = ON, cascading deletes wipe orphaned contract_policies.
        Also scrubs orphaned conversation contexts from session_state.

        Returns:
            List[str]: Identifiers of purged tasks so orchestrators can execute
                       matching filesystem workspace cleanups.
        """
        time_modifier = f"-{days_old} days"

        # 1. Sweep stale tasks
        select_tasks = """
            SELECT task_id FROM task_state 
            WHERE status IN ('COMPLETED', 'FAILED', 'REJECTED', 'CANCELLED')
              AND updated_at <= date('now', ?);
        """
        delete_tasks = """
            DELETE FROM task_state 
            WHERE status IN ('COMPLETED', 'FAILED', 'REJECTED', 'CANCELLED')
              AND updated_at <= date('now', ?);
        """

        # 2. Sweep stale sessions
        delete_sessions = """
            DELETE FROM session_state 
            WHERE updated_at <= date('now', ?);
        """

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # Execute Task Sweep
            cursor.execute(select_tasks, (time_modifier,))
            swept_task_ids = [row[0] for row in cursor.fetchall()]

            if swept_task_ids:
                cursor.execute(delete_tasks, (time_modifier,))
                logger.info(
                    f"[SWEEPER] Purged {len(swept_task_ids)} stale tasks older than {days_old} days from state DB."
                )

            # Execute Session Sweep
            try:
                cursor.execute(delete_sessions, (time_modifier,))
                swept_sessions_count = cursor.rowcount
                if swept_sessions_count > 0:
                    logger.info(
                        f"[SWEEPER] Purged {swept_sessions_count} orphaned client sessions older than {days_old} days."
                    )
            except sqlite3.OperationalError as e:
                # Failsafe in case sweep runs before the table is migrated
                logger.warning(f"[SWEEPER] Skipped session sweep (table might be missing): {e}")

            return swept_task_ids