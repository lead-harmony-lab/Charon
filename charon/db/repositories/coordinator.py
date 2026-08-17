"""
charon/db/repositories/coordinator.py
System Version: v0.1.0 | File Revision: 1.0.0

Repository bridging the Coordinator Engine to the zero-trust SQLite state.
Handles task polling, Level 0 capability audits, Level 1 contract minting,
and zero-trust ephemeral key revocation (The Burn & Sweeper).
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from pathlib import Path

# Adjust import based on your actual config path structure
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

    def update_task_status(self, task_id: str, status: str, results_json: Optional[Dict] = None) -> None:
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
    def audit_level_0_permission(self, agent_id: str, skill_id: str) -> bool:
        """
        THE LAW: Validates capability via strict CBAC mapping.
        Verifies that the agent's assigned role belongs to a permission group
        that explicitly grants access to the requested skill.
        """
        query = """
            SELECT 1 
            FROM system_roles sr
            JOIN role_permission_groups rpg ON sr.role_name = rpg.role_name
            JOIN permission_registry pr ON rpg.group_id = pr.group_id
            JOIN skill_permissions sp ON pr.perm_id = sp.perm_id
            WHERE sr.agent_id = ? AND sp.skill_id = ?;
        """
        with get_connection(self.db_path, read_only=True) as conn:
            result = conn.execute(query, (agent_id, skill_id)).fetchone()
            return bool(result)

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
            result = conn.execute(query, (agent_id, skill_id)).fetchone()
            return bool(result)

    def mint_ephemeral_contract(
            self, task_id: str, agent_id: str, skill_id: str,
            rate_limit: int = 10, token_bound: int = 8000
    ) -> str:
        """
        THE CONTRACT: Mints a temporary key binding an agent to a tool for a specific task.
        """
        contract_id = f"cnt_{uuid.uuid4().hex[:12]}"
        contract_name = f"AutoMint_{agent_id}_{skill_id}"

        query = """
            INSERT INTO contract_policies (
                contract_id, contract_name, task_id, agent_id, skill_id, 
                rate_limit_rpm, token_boundary, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1);
        """
        with get_connection(self.db_path) as conn:
            conn.execute(query, (
                contract_id, contract_name, task_id, agent_id, skill_id,
                rate_limit, token_bound
            ))
            logger.info(f"Minted ephemeral contract {contract_id} for {agent_id} -> {skill_id}")
            return contract_id

    # ==========================================
    # 3. THE BURN & PRUNING ENGINE
    # ==========================================
    def burn_task_contracts(self, task_id: str) -> None:
        """
        THE BURN: Instantly revokes all keys associated with a task when it completes/fails.
        """
        query = "DELETE FROM contract_policies WHERE task_id = ?;"
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(query, (task_id,))
            if cursor.rowcount > 0:
                logger.info(f"Burned {cursor.rowcount} ephemeral contracts for task {task_id}.")

    def sweep_stale_tasks(self, days_old: int = 7) -> int:
        """
        THE SWEEPER: Deletes old tasks. Due to PRAGMA foreign_keys = ON,
        this automatically cascades and wipes out orphaned contract_policies.
        """
        query = "DELETE FROM task_state WHERE updated_at <= date('now', ?);"
        modifier = f"-{days_old} days"

        with get_connection(self.db_path) as conn:
            cursor = conn.execute(query, (modifier,))
            if cursor.rowcount > 0:
                logger.info(f"Sweeper purged {cursor.rowcount} stale tasks older than {days_old} days.")
            return cursor.rowcount