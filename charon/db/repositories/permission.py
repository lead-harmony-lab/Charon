"""
charon/db/repositories/permission.py
System Version: v0.6.0 | File Revision: 2.2.0

Repository for Capability-Based Access Control (CBAC) and pre-execution safety gates.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from charon.db.connection import get_connection


@dataclass(frozen=True)
class AuthResult:
    is_authorized: bool
    status: str  # 'AUTHORIZED', 'SKILL_QUARANTINED', 'SKILL_DISABLED', 'PERMISSION_DENIED', 'SKILL_NOT_FOUND'
    missing_permissions: List[str]
    quarantine_reason: Optional[str] = None


class PermissionRepository:
    def __init__(self, db_path: Union[str, Path]):
        self.db_path = str(db_path)

    def ensure_schema(self) -> None:
        """Ensures CBAC permission tables exist in DB (no-op if schema managed centrally)."""
        pass

    def authorize_execution(self, role_name: str, skill_id: str) -> AuthResult:
        """Unified gatekeeper check: verifies skill status and role group permissions."""
        skill_query = "SELECT status, quarantine_reason FROM skill_registry WHERE skill_id = ?;"

        perm_check_query = """
            SELECT sp.perm_id 
            FROM skill_permissions sp
            JOIN permission_registry pr ON sp.perm_id = pr.perm_id
            WHERE sp.skill_id = ?
              AND pr.group_id NOT IN (
                SELECT group_id 
                FROM role_permission_groups 
                WHERE role_name = ?
              );
        """

        with get_connection(self.db_path, read_only=True, row_factory=True) as conn:
            cursor = conn.execute(skill_query, (skill_id,))
            skill = cursor.fetchone()

            if not skill:
                return AuthResult(False, "SKILL_NOT_FOUND", [])

            if skill["status"] != "ACTIVE":
                return AuthResult(
                    is_authorized=False,
                    status="SKILL_QUARANTINED" if skill["status"] == "QUARANTINED" else "SKILL_DISABLED",
                    missing_permissions=[],
                    quarantine_reason=skill["quarantine_reason"],
                )

            cursor = conn.execute(perm_check_query, (skill_id, role_name))
            missing = [str(row["perm_id"]) for row in cursor.fetchall()]

            if missing:
                return AuthResult(False, "PERMISSION_DENIED", missing)

            return AuthResult(True, "AUTHORIZED", [])

    def grant_group_to_role(self, role_name: str, group_id: str) -> bool:
        """Grants a permission group to a system role."""
        query = "INSERT OR IGNORE INTO role_permission_groups (role_name, group_id) VALUES (?, ?);"
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(query, (role_name, group_id))
            return cursor.rowcount > 0