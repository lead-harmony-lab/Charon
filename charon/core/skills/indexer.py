"""
charon/core/skills/indexer.py
System Version: v2.0.0

Module: Dynamic discovery, skill promotion, database re-indexing,
and stale mapping purge mixin.
Enforces the V2 Declarative Action Schema, explicitly rejecting AST synthesis
and implicit routing.
Implements strict namespace collision mitigation via system_actions.json reservations.
Maintains clean separation between immutable code identifiers (skill_id) and Work Contracts.
All direct SQL execution extracted to repository layer.
Integrates CBAC Schema V2 permission indexing and quarantine status preservation.
Enforces strict fail-fast role resolution against database registry.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from charon.config.paths import DYNAMIC_SKILLS_DIR
from charon.core.skills.base import BaseSkill
from charon.core.skills.models import SkillManifest
from charon.core.skills.roles import RoleResolutionError

# Automatically resolves to 'charon.core.skills.indexer'
logger = logging.getLogger(__name__)


class SkillIndexerMixin:
    """Disk discovery, dynamic promotion, and database re-indexing methods."""

    def register_skill(self, skill: BaseSkill) -> None:
        """Registers an in-memory skill instance keyed by its prompt action contract."""
        self._skills[skill.action_name] = skill
        logger.info(
            f"[LIBRARIAN] In-memory skill '{skill.action_name}' (ID: {skill.skill_id}) registered."
        )

    def verify_system_requirements(self, requirements: List[str]) -> bool:
        """Validates shell dependencies against host environment PATH."""
        return all(shutil.which(req) is not None for req in requirements)

    def _discover_manifests(self, extra_paths: Optional[List[Path]] = None) -> List[Path]:
        """Scans search_paths and optional extra paths for manifest files (flat structure)."""
        manifests: List[Path] = []
        all_paths = list(self.search_paths)
        if extra_paths:
            all_paths.extend(extra_paths)

        for search_path in all_paths:
            expanded = search_path.expanduser().resolve()
            if expanded.exists() and expanded.is_dir():
                # Enforce flat structure: only look exactly one level deep
                for skill_dir in expanded.iterdir():
                    if skill_dir.is_dir():
                        manifest_file = skill_dir / "manifest.json"
                        if manifest_file.exists():
                            manifests.append(manifest_file)

        unique_manifests = list({m.resolve(): m for m in manifests}.values())
        return unique_manifests

    def _promote_skill_to_dynamic(self, source_manifest_path: Path) -> Path:
        """Copies staged skill directory into storage/dynamic/<skill_id>/"""
        source_dir = source_manifest_path.parent
        raw_text = source_manifest_path.read_text(encoding="utf-8")
        manifest_data = json.loads(raw_text)
        skill_id = manifest_data.get("skill_id", source_dir.name)

        target_dir = (DYNAMIC_SKILLS_DIR / skill_id).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        if source_dir.resolve() != target_dir:
            for item in source_dir.glob("*"):
                if item.is_file():
                    shutil.copy2(item, target_dir / item.name)
                elif item.is_dir():
                    shutil.copytree(item, target_dir / item.name, dirs_exist_ok=True)
            logger.info(
                f"[LIBRARIAN] Promoted skill '{skill_id}' from {source_dir} -> {target_dir}"
            )

        return target_dir / "manifest.json"

    def _load_system_reservations(self) -> Dict[str, str]:
        """
        Loads system_actions.json to map reserved action names to authorized skill_ids.
        Returns a dictionary of { "action_name": "reserved_skill_id" }.
        """
        try:
            from charon.config.paths import CONFIG_DIR
            definitions_dir = CONFIG_DIR / "definitions"
        except ImportError:
            # Fallback based on DYNAMIC_SKILLS_DIR
            definitions_dir = DYNAMIC_SKILLS_DIR.parents[2] / "config" / "definitions"

        sys_actions_file = definitions_dir / "system_actions.json"
        reservations = {}

        if sys_actions_file.exists():
            try:
                data = json.loads(sys_actions_file.read_text(encoding="utf-8"))
                for item in data:
                    reservations[item["action_name"]] = item["reserved_key"]
            except Exception as e:
                logger.error(f"[LIBRARIAN] Failed to parse system_actions.json: {e}")
        else:
            logger.warning("[LIBRARIAN] system_actions.json not found. Namespace protection degraded.")

        return reservations

    def purge_stale_mappings(self, active_skill_ids: Set[str]) -> Dict[str, int]:
        """
        Identifies and removes stale skill entries and mappings across SQLite tables.
        Removes:
        1. skill_registry rows for missing plugin files/manifests not present in active_skill_ids.
        2. agent_skill_map rows pointing to non-existent skills or inactive roles.
        """
        logger.info("[LIBRARIAN] Initiating stale mapping purge cycle...")
        purged_stats = {
            "purged_skills": 0,
            "purged_role_mappings": 0,
        }

        try:
            if hasattr(self.repo, "purge_unindexed_skills"):
                purged_stats["purged_skills"] = self.repo.purge_unindexed_skills(active_skill_ids)
            elif hasattr(self.repo, "purge_stale_skills"):
                purged_stats["purged_skills"] = self.repo.purge_stale_skills(active_skill_ids)

            if hasattr(self.repo, "purge_orphaned_agent_skill_mappings"):
                purged_stats["purged_role_mappings"] = (
                    self.repo.purge_orphaned_agent_skill_mappings()
                )

            logger.info(
                f"[LIBRARIAN] Stale purge complete. Stats: {purged_stats}"
            )
        except Exception as e:
            logger.error(f"[LIBRARIAN] Failed during stale mapping purge: {e}", exc_info=True)

        return purged_stats

    def reindex_skills(
        self,
        extra_paths: Optional[List[Path]] = None,
        auto_promote: bool = False,
        purge_stale: bool = True,
    ) -> None:
        """
        Unified V2 pipeline for skill indexing and optional stale purging.
        Reads strict declarative action arrays from manifest.json and loads them
        directly into the database without AST evaluation or guessing.
        """
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("[LIBRARIAN] Executing skill reindexing pipeline...")

        try:
            # Ensure schema state across repositories safely
            if hasattr(self.repo, "ensure_schema"):
                self.repo.ensure_schema()
            if hasattr(self.agent_repo, "ensure_schema"):
                self.agent_repo.ensure_schema()
            if (
                hasattr(self, "permission_repo")
                and self.permission_repo is not None
                and hasattr(self.permission_repo, "ensure_schema")
            ):
                self.permission_repo.ensure_schema()

            # Load Namespace Reservations
            reserved_actions = self._load_system_reservations()

            raw_manifests = self._discover_manifests(extra_paths=extra_paths)
            logger.info(f"[LIBRARIAN] Discovered {len(raw_manifests)} manifest(s).")

            processed_manifests: List[Path] = []
            for m_path in raw_manifests:
                try:
                    target_m_path = (
                        self._promote_skill_to_dynamic(m_path) if auto_promote else m_path
                    )
                    if target_m_path not in processed_manifests:
                        processed_manifests.append(target_m_path)
                except Exception as e:
                    logger.error(
                        f"[LIBRARIAN] Failed to process manifest {m_path}: {e}"
                    )

            discovered_skill_ids: Set[str] = set()

            # Pass 1: Index skills into skill_registry strictly from V2 Manifest declarations
            for manifest_path in processed_manifests:
                try:
                    raw_text = manifest_path.read_text(encoding="utf-8")
                    manifest = SkillManifest.model_validate_json(raw_text)
                    entry_file = manifest_path.parent / "plugin.py"

                    # --- 1. Flat Directory Validation Check ---
                    skill_folder_name = manifest_path.parent.name
                    if skill_folder_name != manifest.skill_id:
                        logger.critical(
                            f"[LIBRARIAN] SECURITY/NAMESPACE REJECTION: Directory name '{skill_folder_name}' "
                            f"does not match declared skill_id '{manifest.skill_id}' in manifest. "
                            f"Skipping index."
                        )
                        continue

                    if not entry_file.exists():
                        logger.warning(
                            f"[LIBRARIAN] Plugin implementation missing at '{entry_file}' for '{manifest.skill_id}'."
                        )
                        continue

                    # Fallback to empty list if nothing provided; coercion handled by Pydantic
                    allowed_roles_list = manifest.allowed_agents
                    is_global = 1 if "*" in allowed_roles_list else 0

                    # --- Path-aware status check ---
                    manifest_path_str = manifest_path.as_posix()
                    if "/storage/staged/" in manifest_path_str or "/staged/" in manifest_path_str:
                        status = "STAGED"
                    else:
                        status = manifest.status

                    discovered_skill_ids.add(manifest.skill_id)

                    # Iterate over explicit discrete capabilities
                    for action in manifest.actions:

                        # 2. Namespace Collision Mitigation
                        if action.action_name in reserved_actions:
                            authorized_skill = reserved_actions[action.action_name]
                            if manifest.skill_id != authorized_skill:
                                logger.critical(
                                    f"[LIBRARIAN] NAMESPACE COLLISION: Skill '{manifest.skill_id}' "
                                    f"attempted to claim reserved action '{action.action_name}'. "
                                    f"Authorized owner is '{authorized_skill}'. Skipping action."
                                )
                                continue

                        # 3. Convention Enforcement
                        if manifest.skill_type == "system" and not action.action_name.startswith("sys_"):
                            logger.warning(
                                f"[LIBRARIAN] Naming violation: System action '{action.action_name}' "
                                f"in skill '{manifest.skill_id}' should start with 'sys_'."
                            )

                        # Determine final required permissions and artifacts (fallback to skill-level if action-level is empty)
                        final_permissions = action.required_permissions or manifest.required_permissions
                        final_consumed = action.consumed_artifacts or manifest.consumed_artifacts
                        final_produced = action.produced_artifacts or manifest.produced_artifacts

                        # 4. Database Upsert (SSOT)
                        self.repo.upsert_skill(
                            skill_id=manifest.skill_id,
                            action_name=action.action_name,
                            version=manifest.version,
                            category=manifest.category,
                            description=action.description,
                            parameters=action.parameters,
                            system_requirements=manifest.system_requirements,
                            consumed_artifacts=final_consumed,
                            produced_artifacts=final_produced,
                            entry_file_path=str(entry_file.resolve()),
                            handler_name=action.handler_name,
                            is_global=is_global,
                            status=status,
                            quarantine_reason=manifest.quarantine_reason,
                            required_permissions=final_permissions,
                            skill_type=manifest.skill_type
                        )

                    # Link roles additively
                    if is_global:
                        active_roles = self.agent_repo.get_active_agent_ids()
                        for role_id in active_roles:
                            self.repo.link_agent_to_skill(role_id, manifest.skill_id)
                    else:
                        for raw_role_id in allowed_roles_list:
                            if raw_role_id == "*":
                                continue
                            canonical_id = self.resolve_agent_id_for_role(raw_role_id)
                            self.repo.link_agent_to_skill(canonical_id, manifest.skill_id)

                except RoleResolutionError as rre:
                    logger.error(f"[LIBRARIAN] Role Resolution Error indexing manifest {manifest_path}: {rre}")
                    raise
                except Exception as e:
                    logger.warning(
                        f"[LIBRARIAN] Failed to index manifest {manifest_path}: {e}",
                        exc_info=True,
                    )

            # Pass 2: Purge stale mappings if requested
            if purge_stale:
                self.purge_stale_mappings(discovered_skill_ids)

            # Pass 3: Invalidate and reload in-memory manifest cache
            if hasattr(self, "reload_all_manifests"):
                self.reload_all_manifests()

            logger.info("[LIBRARIAN] Skill reindexing complete.")
        except Exception as e:
            logger.error(f"[LIBRARIAN] Reindexing pipeline failed: {e}", exc_info=True)
            raise