"""
charon/db/repositories/prompts.py
System Version: v0.8.0 | File Revision: 3.1.0

Repository for system prompt templates, role rosters, and extraction capability schemas.
Relies strictly on SQLite database queries aligned with system_roles (role_name) schema.
Zero fallback synthesis.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from charon.config.paths import STATE_DB_PATH
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.DB.Repositories.Prompts")


class PromptRepository:
    """Data access layer for system prompt templates, active role rosters, and skill extraction metadata."""

    def __init__(self, db_path: Union[str, Path] = STATE_DB_PATH):
        self.db_path = str(db_path)

    def get_system_prompt_template(self, role_target: str) -> Optional[str]:
        """
        Retrieves system prompt for target role_name, agent_id, or display_name.
        Fails fast and returns None if no prompt matches the target in the database.
        """
        if not role_target or not str(role_target).strip():
            return None

        clean_target = str(role_target).strip()
        query = """
            SELECT ar.system_prompt 
            FROM agent_registry ar
            LEFT JOIN system_roles sr ON ar.agent_id = sr.agent_id
            WHERE (
                LOWER(ar.agent_id) = LOWER(?)
                OR LOWER(ar.display_name) = LOWER(?)
                OR LOWER(sr.role_name) = LOWER(?)
            )
              AND ar.is_active = 1
              AND ar.system_prompt IS NOT NULL
              AND ar.system_prompt != ''
            LIMIT 1;
        """
        try:
            with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
                cursor = conn.execute(query, (clean_target, clean_target, clean_target))
                row = cursor.fetchone()
                if row and row["system_prompt"]:
                    return str(row["system_prompt"])
        except Exception as e:
            logger.error(
                f"[PromptRepository] Database query failed for prompt target '{clean_target}': {e}",
                exc_info=True,
            )
            raise

        logger.warning(
            f"[PromptRepository] Fail Fast: No system prompt found for target '{clean_target}'."
        )
        return None

    def get_active_role_roster(self) -> List[Dict[str, str]]:
        """Retrieves list of active system roles and their descriptions strictly from DB."""
        query = """
            SELECT sr.role_name, sr.description 
            FROM system_roles sr
            JOIN agent_registry ar ON sr.agent_id = ar.agent_id
            WHERE ar.is_active = 1
            ORDER BY sr.role_name ASC;
        """
        try:
            with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
                cursor = conn.execute(query)
                return [
                    {"role_name": row["role_name"], "description": row["description"] or ""}
                    for row in cursor.fetchall()
                ]
        except Exception as e:
            logger.error(f"[PromptRepository] Failed to fetch active role roster: {e}", exc_info=True)
            raise

    def get_role_capabilities(self) -> List[Dict[str, Any]]:
        """
        Retrieves active skill schemas per active agent/role.
        Deserializes JSON parameters strictly, logging errors on malformed payloads.
        """
        query = """
            SELECT DISTINCT
                ar.agent_id AS role_name,
                sk.action_name,
                sk.description,
                sk.parameters
            FROM agent_registry ar
            JOIN skill_registry sk ON (
                sk.is_global = 1 OR EXISTS (
                    SELECT 1 FROM agent_skill_map asm 
                    WHERE asm.skill_id = sk.skill_id 
                      AND (asm.agent_id = ar.agent_id OR asm.agent_id = '*')
                )
            )
            WHERE UPPER(sk.status) = 'ACTIVE' AND ar.is_active = 1
            ORDER BY ar.agent_id, sk.action_name;
        """
        try:
            with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
                cursor = conn.execute(query)
                results = []
                for row in cursor.fetchall():
                    item = dict(row)
                    params = item.get("parameters")
                    if isinstance(params, str) and params.strip():
                        try:
                            item["parameters"] = json.loads(params)
                        except json.JSONDecodeError as e:
                            logger.error(
                                f"[PromptRepository] Corrupt parameters JSON for skill '{item.get('action_name')}': {e}"
                            )
                            raise
                    elif params is None:
                        item["parameters"] = {}
                    results.append(item)
                return results
        except Exception as e:
            logger.error(f"[PromptRepository] Failed to fetch role capabilities: {e}", exc_info=True)
            raise

    def get_default_action_for_identifier(self, identifier: str) -> Optional[str]:
        """Retrieves default_action for a given agent_id, display_name, or role_name."""
        if not identifier or not str(identifier).strip():
            return None

        clean_id = str(identifier).strip()
        query = """
            SELECT ar.default_action 
            FROM agent_registry ar
            LEFT JOIN system_roles sr ON ar.agent_id = sr.agent_id
            WHERE (
                LOWER(ar.agent_id) = LOWER(?)
                OR LOWER(ar.display_name) = LOWER(?)
                OR LOWER(sr.role_name) = LOWER(?)
            )
            LIMIT 1;
        """
        try:
            with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
                cursor = conn.execute(query, (clean_id, clean_id, clean_id))
                row = cursor.fetchone()
                if row and row["default_action"]:
                    return str(row["default_action"])
        except Exception as e:
            logger.error(
                f"[PromptRepository] Failed to fetch default action for identifier '{clean_id}': {e}",
                exc_info=True,
            )
            raise

        return None