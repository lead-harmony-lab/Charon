"""
charon/db/repositories/prompts.py
System Version: v0.1.0 | File Revision: 1.1.0

Repository for system prompt templates, role rosters, and extraction capability schemas.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.DB.Repositories.Prompts")


class PromptRepository:
    """Data access layer for system prompt templates, active role rosters, and skill extraction metadata."""

    def __init__(self, db_path: Union[str, Path] = STATE_DB_PATH):
        self.db_path = db_path

    def get_system_prompt_template(self, role_target: str) -> Optional[str]:
        """Retrieves system prompt for target role, falling back to default_system_generalist."""
        query = """
            SELECT ar.system_prompt 
            FROM system_roles sr
            JOIN agent_registry ar ON sr.agent_id = ar.agent_id
            WHERE (sr.role_name = ? OR sr.role_name = 'default_system_generalist')
              AND ar.is_active = 1
              AND ar.system_prompt IS NOT NULL
              AND ar.system_prompt != ''
            ORDER BY CASE WHEN sr.role_name = ? THEN 0 ELSE 1 END
            LIMIT 1
        """
        try:
            with get_connection(self.db_path, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute(query, (role_target, role_target))
                row = cursor.fetchone()
                if row and row["system_prompt"]:
                    return str(row["system_prompt"])
        except Exception as e:
            logger.warning(f"Failed to fetch prompt template for target '{role_target}': {e}")
        return None

    def get_active_role_roster(self) -> List[Dict[str, str]]:
        """Retrieves list of active system roles and their descriptions."""
        query = """
            SELECT sr.role_name, sr.description 
            FROM system_roles sr
            JOIN agent_registry ar ON sr.agent_id = ar.agent_id
            WHERE ar.is_active = 1
            ORDER BY sr.role_name
        """
        try:
            with get_connection(self.db_path, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                return [
                    {"role_name": row["role_name"], "description": row["description"] or ""}
                    for row in cursor.fetchall()
                ]
        except Exception as e:
            logger.warning(f"Failed to fetch role roster: {e}")
            return []

    def get_role_capabilities(self) -> List[Dict[str, Any]]:
        """
        Retrieves active skill schemas per system role.
        Uses UPPER(sk.status) = 'ACTIVE' to match the database schema.
        """
        query = """
            SELECT 
                sr.role_name,
                sk.action_name,
                sk.description,
                sk.parameters
            FROM system_roles sr
            JOIN agent_skill_map asm ON sr.agent_id = asm.agent_id
            JOIN skill_registry sk ON asm.skill_id = sk.skill_id
            JOIN agent_registry ar ON sr.agent_id = ar.agent_id
            WHERE UPPER(sk.status) = 'ACTIVE' AND ar.is_active = 1
            ORDER BY sr.role_name, sk.action_name
        """
        try:
            with get_connection(self.db_path, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.warning(f"Failed to fetch role capabilities: {e}")
            return []

    def get_default_action_for_identifier(self, identifier: str) -> Optional[str]:
        """Retrieves default_action for a given agent_id or role_name."""
        query = """
            SELECT ar.default_action 
            FROM agent_registry ar
            LEFT JOIN system_roles sr ON ar.agent_id = sr.agent_id
            WHERE ar.agent_id = ? OR sr.role_name = ?
            LIMIT 1
        """
        try:
            with get_connection(self.db_path, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute(query, (identifier, identifier))
                row = cursor.fetchone()
                if row and row["default_action"]:
                    return str(row["default_action"])
        except Exception as e:
            logger.warning(f"Failed to fetch default action for identifier '{identifier}': {e}")
        return None