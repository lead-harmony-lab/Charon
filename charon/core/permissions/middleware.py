"""
charon/core/permissions/middleware.py
System Version: v2.1.0 | File Revision: 1.0.0

Module: CBAC Permission Validation Middleware
Enforces Capability-Based Access Control (CBAC) during skill execution.
Validates system role entitlements, skill quarantine status, and dynamic scope boundaries.
"""

import fnmatch
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class PermissionDeniedError(Exception):
    """Raised when an agent role lacks necessary permissions or a skill is quarantined."""
    pass


class CBACPermissionMiddleware:
    """Middleware enforcing role capability checks and scope matching prior to skill execution."""

    def __init__(self, repo: Any):
        self.repo = repo

    def validate_execution(
        self,
        role_name: str,
        skill_id: str,
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Validates whether an agent role is authorized to execute a target skill.

        Raises:
            PermissionDeniedError: If the skill is quarantined, requested permissions exceed
                                   role capabilities, or scope patterns fail matching.
        """
        # 1. Inspect skill status (reject QUARANTINED skills immediately)
        skill_meta = self.repo.get_skill_by_id(skill_id)
        if not skill_meta:
            raise PermissionDeniedError(f"Skill '{skill_id}' not found in registry.")

        if skill_meta.get("status") == "QUARANTINED":
            reason = skill_meta.get("quarantine_reason", "Trigger safety violation")
            raise PermissionDeniedError(
                f"Execution rejected: Skill '{skill_id}' is QUARANTINED ({reason})."
            )

        # 2. Fetch required skill permissions
        required_perms = self.repo.get_skill_permissions(skill_id)
        if not required_perms:
            return  # No permissions requested by skill

        # 3. Retrieve allowed permissions assigned to the role via role_permission_groups
        role_perms = self.repo.get_role_permissions(role_name)
        role_perm_map = {p["perm_id"]: p.get("scope_pattern", "*") for p in role_perms}

        # 4. Check capability assignment & scope boundary matching
        target_scope = (execution_context or {}).get("target_scope")

        for req in required_perms:
            perm_id = req if isinstance(req, str) else req.get("perm_id")

            if perm_id not in role_perm_map:
                raise PermissionDeniedError(
                    f"Access Denied: Role '{role_name}' lacks capability '{perm_id}' "
                    f"required by skill '{skill_id}'."
                )

            # Match pattern if explicit scope target provided in context
            allowed_pattern = role_perm_map[perm_id]
            if target_scope and not fnmatch.fnmatch(target_scope, allowed_pattern):
                raise PermissionDeniedError(
                    f"Scope Violation: Role '{role_name}' pattern '{allowed_pattern}' "
                    f"denies access to target scope '{target_scope}' for permission '{perm_id}'."
                )

        logger.debug(f"[CBAC] Role '{role_name}' successfully authorized for skill '{skill_id}'.")

    def wrap_execution(self, func: Callable) -> Callable:
        """Decorator wrapper for skill runner invocation handlers."""
        def wrapper(role_name: str, skill_id: str, *args: Any, **kwargs: Any) -> Any:
            self.validate_execution(role_name, skill_id, kwargs.get("execution_context"))
            return func(role_name, skill_id, *args, **kwargs)
        return wrapper