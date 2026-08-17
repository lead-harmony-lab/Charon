"""
System Version: v2.1.0 | File Revision: 2.5.0

Module: Dynamic discovery, skill promotion, database re-indexing,
declarative configuration sync, and stale mapping purge mixin.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from charon.config.paths import (
    AGENT_REGISTRY_JSON,
    AGENT_SKILL_MAP_JSON,
    DYNAMIC_SKILLS_DIR,
    PERMISSION_GROUPS_JSON,
    PERMISSION_REGISTRY_JSON,
    REGISTRY_DIR,
    ROLE_PERMISSION_GROUPS_JSON,
    SKILL_REGISTRY_JSON,
    SYSTEM_ACTIONS_JSON,
    SYSTEM_ROLES_JSON,
)
from charon.core.skills.base import BaseSkill
from charon.core.skills.models import SkillManifest

logger = logging.getLogger(__name__)


class SkillIndexerMixin:
    """Disk discovery, dynamic promotion, declarative config syncing, and transactional re-indexing."""

    def register_skill(self, skill: BaseSkill) -> None:
        """Registers an in-memory skill instance keyed by its prompt action contract."""
        self._skills[skill.action_name] = skill
        logger.info(
            f"[LIBRARIAN] In-memory skill '{skill.action_name}' (ID: {skill.skill_id}) registered."
        )

    def verify_system_requirements(self, requirements: List[str]) -> bool:
        """Validates shell dependencies against host environment PATH."""
        return all(shutil.which(req) is not None for req in requirements)

    def _get_registry_dir(self) -> Path:
        """Resolves config/registry directory with standard path fallback."""
        try:
            return REGISTRY_DIR
        except Exception:
            return DYNAMIC_SKILLS_DIR.parents[2] / "config" / "registry"

    def _discover_manifests(self, extra_paths: Optional[List[Path]] = None) -> List[Path]:
        """Scans search_paths and optional extra paths for manifest files (flat structure)."""
        manifests: List[Path] = []
        all_paths = list(self.search_paths)
        if extra_paths:
            all_paths.extend(extra_paths)

        for search_path in all_paths:
            expanded = search_path.expanduser().resolve()
            if expanded.exists() and expanded.is_dir():
                for skill_dir in expanded.iterdir():
                    if skill_dir.is_dir():
                        manifest_file = skill_dir / "manifest.json"
                        if manifest_file.exists():
                            manifests.append(manifest_file)

        return list({m.resolve(): m for m in manifests}.values())

    def _promote_skill_to_dynamic(self, source_manifest_path: Path) -> Path:
        """Validates manifest package metadata before copying staged skill directory into DYNAMIC_SKILLS_DIR."""
        source_dir = source_manifest_path.parent
        raw_text = source_manifest_path.read_text(encoding="utf-8")
        manifest_data = json.loads(raw_text)
        package_id = manifest_data.get("package", manifest_data.get("skill_id", source_dir.name))

        # Security check prior to disk copy
        if manifest_data.get("package") and source_dir.name != manifest_data["package"]:
            if "/staged/" in source_manifest_path.as_posix() or "/storage/staged/" in source_manifest_path.as_posix():
                logger.warning(
                    f"[LIBRARIAN] Staged package directory '{source_dir.name}' will be normalized to '{package_id}'"
                )
            else:
                raise ValueError(
                    f"SECURITY REJECTION: Directory '{source_dir.name}' does not match manifest package '{package_id}'"
                )

        target_dir = (DYNAMIC_SKILLS_DIR / package_id).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        if source_dir.resolve() != target_dir:
            for item in source_dir.glob("*"):
                if item.is_file():
                    shutil.copy2(item, target_dir / item.name)
                elif item.is_dir():
                    shutil.copytree(item, target_dir / item.name, dirs_exist_ok=True)
            logger.info(
                f"[LIBRARIAN] Promoted skill package '{package_id}' from {source_dir} -> {target_dir}"
            )

        return target_dir / "manifest.json"

    def _load_declarative_configs(self) -> Tuple[List[Tuple[str, List[Dict[str, Any]]]], Set[str], Dict[str, Dict[str, Set[str]]]]:
        """
        Phase 1 Helper: Pre-loads all registry JSON files outside transaction boundaries.
        Returns:
            - dag_records: Ordered list of (repo_method_name, list_of_clean_records)
            - declarative_skill_ids: Set of skill_ids registered in skill_registry.json
            - reservation_graph: In-memory mapping reserved_key -> action_name -> set(allowed_targets)
        """
        dag_sequence = [
            (PERMISSION_GROUPS_JSON, "sync_permission_groups"),
            (PERMISSION_REGISTRY_JSON, "sync_permission_registry"),
            (AGENT_REGISTRY_JSON, "sync_agent_registry"),
            (SYSTEM_ROLES_JSON, "sync_system_roles"),
            (ROLE_PERMISSION_GROUPS_JSON, "sync_role_permission_groups"),
            (AGENT_SKILL_MAP_JSON, "sync_agent_skill_map"),
            (SYSTEM_ACTIONS_JSON, "sync_system_actions"),
            (SKILL_REGISTRY_JSON, "sync_skill_registry"),
        ]

        dag_records: List[Tuple[str, List[Dict[str, Any]]]] = []
        raw_parsed_files: Dict[Path, List[Dict[str, Any]]] = {}

        for file_path, repo_method in dag_sequence:
            if not file_path.exists():
                logger.warning(f"[LIBRARIAN] Registry file missing: '{file_path}'. Skipping stage.")
                continue

            try:
                raw_data = json.loads(file_path.read_text(encoding="utf-8"))
                clean_records = [
                    {k: v for k, v in record.items() if not k.startswith("_")}
                    for record in raw_data
                ]
                dag_records.append((repo_method, clean_records))
                raw_parsed_files[file_path] = clean_records
            except Exception as e:
                logger.error(f"[LIBRARIAN] Error parsing registry file '{file_path.name}': {e}", exc_info=True)
                raise

        # Build reservation graph and preserve declarative skill IDs
        reservation_graph: Dict[str, Dict[str, Set[str]]] = {}
        declarative_skill_ids: Set[str] = set()

        sys_actions = raw_parsed_files.get(SYSTEM_ACTIONS_JSON, [])
        skill_registry = raw_parsed_files.get(SKILL_REGISTRY_JSON, [])

        for item in sys_actions:
            res_key = item.get("reserved_key", "GLOBAL")
            act_name = item.get("action_name")
            if act_name:
                reservation_graph.setdefault(res_key, {}).setdefault(act_name, set())

        for item in skill_registry:
            act_name = item.get("action_name")
            res_key = item.get("reserved_key", "GLOBAL")
            pkg = item.get("target_package")
            s_id = item.get("skill_id")

            if s_id:
                declarative_skill_ids.add(s_id)

            if act_name:
                action_map = reservation_graph.setdefault(res_key, {}).setdefault(act_name, set())
                if pkg:
                    action_map.add(pkg)
                if s_id:
                    action_map.add(s_id)

        return dag_records, declarative_skill_ids, reservation_graph

    def purge_stale_mappings(self, active_skill_ids: Set[str]) -> Dict[str, int]:
        """Identifies and removes stale skill entries and mappings across database tables."""
        logger.info("[LIBRARIAN] Initiating stale mapping purge cycle...")
        purged_stats = {"purged_skills": 0, "purged_role_mappings": 0}

        try:
            if hasattr(self.repo, "purge_unindexed_skills"):
                purged_stats["purged_skills"] = self.repo.purge_unindexed_skills(active_skill_ids)
            elif hasattr(self.repo, "purge_stale_skills"):
                purged_stats["purged_skills"] = self.repo.purge_stale_skills(active_skill_ids)

            if hasattr(self.repo, "purge_orphaned_agent_skill_mappings"):
                purged_stats["purged_role_mappings"] = (
                    self.repo.purge_orphaned_agent_skill_mappings()
                )

            logger.info(f"[LIBRARIAN] Stale purge complete. Stats: {purged_stats}")
        except Exception as e:
            logger.error(f"[LIBRARIAN] Failed during stale mapping purge: {e}", exc_info=True)

        return purged_stats

    def reindex_skills(
        self,
        extra_paths: Optional[List[Path]] = None,
        auto_promote: bool = False,
        purge_stale: bool = True,
    ) -> None:
        """Unified 3-phase transactional pipeline for skill indexing and declarative config sync."""
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("[LIBRARIAN] Executing 3-phase transactional reindexing pipeline...")

        if hasattr(self.repo, "ensure_schema"):
            self.repo.ensure_schema()
        if hasattr(self.agent_repo, "ensure_schema"):
            self.agent_repo.ensure_schema()

        # =========================================================================
        # PHASE 1: INGEST & BUILD IN-MEMORY GRAPH (File I/O phase)
        # =========================================================================
        dag_records, declarative_skill_ids, reservation_graph = self._load_declarative_configs()
        raw_manifest_paths = self._discover_manifests(extra_paths=extra_paths)

        valid_manifest_objs: List[Tuple[SkillManifest, Path]] = []
        for m_path in raw_manifest_paths:
            try:
                target_path = self._promote_skill_to_dynamic(m_path) if auto_promote else m_path
                raw_text = target_path.read_text(encoding="utf-8")
                manifest = SkillManifest.model_validate_json(raw_text)

                if target_path.parent.name != manifest.package:
                    logger.critical(
                        f"[LIBRARIAN] SECURITY REJECTION: Directory '{target_path.parent.name}' "
                        f"does not match package '{manifest.package}'."
                    )
                    continue

                valid_manifest_objs.append((manifest, target_path))
            except Exception as e:
                logger.error(f"[LIBRARIAN] Failed to process manifest at '{m_path}': {e}")

        # =========================================================================
        # PHASE 2: STATE DIFFING & COLLISION DETECTION
        # =========================================================================
        reconciled_skills: List[Tuple[SkillManifest, Path]] = []
        # Union discovered dynamic skill IDs with declarative config skill IDs
        discovered_skill_ids: Set[str] = set(declarative_skill_ids)

        for manifest, target_path in valid_manifest_objs:
            package_valid = True
            for action in manifest.actions:
                for res_key, action_map in reservation_graph.items():
                    if action.action_name in action_map:
                        allowed_targets = action_map[action.action_name]
                        if allowed_targets and (
                            manifest.package not in allowed_targets
                            and action.skill_id not in allowed_targets
                        ):
                            logger.critical(
                                f"[LIBRARIAN] CLAIM COLLISION: '{manifest.package}' / '{action.skill_id}' "
                                f"attempted to claim reserved action '{action.action_name}'."
                            )
                            package_valid = False
                            break

            if package_valid:
                reconciled_skills.append((manifest, target_path))
                for action in manifest.actions:
                    discovered_skill_ids.add(action.skill_id)

        # =========================================================================
        # PHASE 3: TRANSACTIONAL SAFE UPSERTS (Database Operations Only)
        # =========================================================================
        transaction_cm = (
            self.repo.transaction_immediate()
            if hasattr(self.repo, "transaction_immediate")
            else self.repo.transaction()
        )

        with transaction_cm:
            # Step A: Apply pre-loaded declarative definitions in DAG order
            for repo_method, clean_records in dag_records:
                if hasattr(self.repo, repo_method):
                    getattr(self.repo, repo_method)(clean_records)
                elif hasattr(self, repo_method):
                    getattr(self, repo_method)(clean_records)

            # Step B: Upsert validated dynamic skill records and sync permissions
            for manifest, target_path in reconciled_skills:
                entry_file = target_path.parent / "plugin.py"
                if not entry_file.exists():
                    logger.warning(f"[LIBRARIAN] Implementation missing at '{entry_file}'. Skipping.")
                    continue

                is_global = 1 if getattr(manifest, "is_global", False) else 0
                manifest_path_str = target_path.as_posix()
                status = "STAGED" if ("/storage/staged/" in manifest_path_str or "/staged/" in manifest_path_str) else manifest.status

                for action in manifest.actions:
                    final_sys_reqs = action.system_requirements or manifest.system_requirements
                    final_permissions = action.required_permissions or manifest.required_permissions
                    final_consumed = action.consumed_artifacts or manifest.consumed_artifacts
                    final_produced = action.produced_artifacts or manifest.produced_artifacts

                    self.repo.upsert_skill(
                        skill_id=action.skill_id,
                        action_name=action.action_name,
                        version=manifest.version,
                        category=manifest.category,
                        description=action.description,
                        parameters=action.parameters,
                        system_requirements=final_sys_reqs,
                        consumed_artifacts=final_consumed,
                        produced_artifacts=final_produced,
                        entry_file_path=str(entry_file.resolve()),
                        handler_name=action.handler_name,
                        is_global=is_global,
                        status=status,
                        quarantine_reason=manifest.quarantine_reason,
                        required_permissions=final_permissions,
                        skill_type=manifest.skill_type,
                    )

                    if hasattr(self.repo, "bind_skill_permissions"):
                        self.repo.bind_skill_permissions(action.skill_id, final_permissions)

            # Step C: Purge unindexed stale orphans within transaction boundary
            if purge_stale:
                self.purge_stale_mappings(discovered_skill_ids)

        if hasattr(self, "reload_all_manifests"):
            self.reload_all_manifests()

        logger.info("[LIBRARIAN] 3-phase transactional reconciliation pipeline complete.")