"""
charon/core/skills/indexer.py
System Version: v0.6.3 | File Revision: 7.0.0

Module: Dynamic discovery, skill promotion, route syncing, and database re-indexing mixin.
Maintains clean separation between immutable code identifiers (skill_id) and prompt contracts (action_name).
All direct SQL execution extracted to repository layer.
Integrates CBAC Schema V2 permission indexing and quarantine status preservation.
Enforces strict fail-fast role resolution against database registry.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from charon.config.paths import DYNAMIC_SKILLS_DIR
from charon.core.skills.base import BaseSkill
from charon.core.skills.models import SkillManifest
from charon.core.skills.roles import RoleResolutionError

logger = logging.getLogger("Charon.Core.Skills.Indexer")


class SkillIndexerMixin:
    """Disk discovery, dynamic promotion, route syncing, and database re-indexing methods."""

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
        """Scans search_paths and optional extra paths for manifest files."""
        manifests: List[Path] = []
        all_paths = list(self.search_paths)
        if extra_paths:
            all_paths.extend(extra_paths)

        for search_path in all_paths:
            expanded = search_path.expanduser().resolve()
            if expanded.exists() and expanded.is_dir():
                manifests.extend(expanded.rglob("manifest.json"))

        unique_manifests = list({m.resolve(): m for m in manifests}.values())
        return unique_manifests

    def _promote_skill_to_dynamic(self, source_manifest_path: Path) -> Path:
        """Copies staged skill directory into skills_registry/dynamic/<skill_id>/"""
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

    def reindex_skills(
        self, extra_paths: Optional[List[Path]] = None, auto_promote: bool = False
    ) -> None:
        """
        Unified pipeline for skill indexing and role-based route synchronization.
        Establishes skill_registry entries and maps agent capability FKs via agent_skill_map.
        Saves CBAC Schema V2 required permissions and preserves active quarantine states.
        Fails fast if any manifest references an invalid role or agent not present in SQLite.
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
            if hasattr(self.route_repo, "ensure_schema"):
                self.route_repo.ensure_schema()
            if (
                hasattr(self, "permission_repo")
                and self.permission_repo is not None
                and hasattr(self.permission_repo, "ensure_schema")
            ):
                self.permission_repo.ensure_schema()

            # Clear existing agent-skill mappings via repository abstraction
            self.repo.clear_all_agent_skill_mappings()

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

            # Pass 1: Index skills into skill_registry and populate agent_skill_map
            for manifest_path in processed_manifests:
                try:
                    raw_text = manifest_path.read_text(encoding="utf-8")
                    raw_json = json.loads(raw_text)
                    manifest = SkillManifest.model_validate_json(raw_text)
                    entry_file = manifest_path.parent / "plugin.py"

                    if not entry_file.exists():
                        logger.warning(
                            f"[LIBRARIAN] Plugin implementation file missing at '{entry_file}' for manifest '{manifest.skill_id}'."
                        )
                        continue

                    allowed_agents_list = getattr(manifest, "allowed_agents", []) or raw_json.get(
                        "allowed_agents", []
                    )
                    if isinstance(allowed_agents_list, str):
                        allowed_agents_list = [allowed_agents_list]

                    is_global = 1 if ("*" in allowed_agents_list or getattr(manifest, "is_global", False)) else 0
                    total_actions = len(manifest.supported_actions)

                    # CBAC Schema V2 fields
                    status = getattr(manifest, "status", "ACTIVE") or raw_json.get("status", "ACTIVE")
                    quarantine_reason = getattr(manifest, "quarantine_reason", None) or raw_json.get("quarantine_reason", None)
                    required_permissions = getattr(manifest, "required_permissions", []) or raw_json.get("required_permissions", [])

                    for action_name, action_def in manifest.supported_actions.items():
                        # Derive unique primary key skill_id per action contract entry
                        if total_actions > 1 and not manifest.skill_id.endswith(f"_{action_name}"):
                            action_skill_id = f"{manifest.skill_id}_{action_name}"
                        else:
                            action_skill_id = manifest.skill_id

                        if isinstance(action_def, dict):
                            desc = action_def.get(
                                "description",
                                manifest.description or f"Executes '{action_name}'",
                            )
                            handler_name = action_def.get("handler") or action_def.get("handler_name", f"handle_{action_name}")
                            params = action_def.get("parameters", {})
                        else:
                            desc = manifest.action_descriptions.get(
                                action_name,
                                manifest.description or f"Executes '{action_name}'",
                            )
                            handler_name = str(action_def)
                            params = manifest.action_parameters.get(action_name, {})

                        # Upsert skill contract record through SkillRepository
                        self.repo.upsert_skill(
                            skill_id=action_skill_id,
                            action_name=action_name,
                            version=manifest.version,
                            category=manifest.category,
                            description=desc,
                            parameters=params,
                            system_requirements=manifest.system_requirements,
                            consumed_artifacts=manifest.consumed_artifacts,
                            produced_artifacts=manifest.produced_artifacts,
                            entry_file_path=str(entry_file.resolve()),
                            handler_name=handler_name,
                            is_global=is_global,
                            status=status,
                            quarantine_reason=quarantine_reason,
                            required_permissions=required_permissions,
                        )

                        # Link active agents to agent_skill_map using (agent_id, skill_id)
                        if is_global:
                            active_agents = self.agent_repo.get_active_agent_ids()
                            for agent_id in active_agents:
                                self.repo.link_agent_to_skill(agent_id, action_skill_id)
                        else:
                            for raw_agent_id in allowed_agents_list:
                                if raw_agent_id == "*":
                                    continue
                                # Strict DB lookup: Fails immediately if raw_agent_id/role is unmapped in SQLite
                                canonical_id = self.resolve_agent_id_for_role(raw_agent_id)
                                self.repo.link_agent_to_skill(canonical_id, action_skill_id)

                except RoleResolutionError as rre:
                    logger.error(f"[LIBRARIAN] Role Resolution Error indexing manifest {manifest_path}: {rre}")
                    raise
                except Exception as e:
                    logger.warning(
                        f"[LIBRARIAN] Failed to index manifest {manifest_path}: {e}",
                        exc_info=True,
                    )

            # Pass 2: Sync route_registry via RouteRepository
            self.route_repo.sync_dynamic_routes()

            # Pass 3: Invalidate and reload in-memory manifest cache
            if hasattr(self, "reload_all_manifests"):
                self.reload_all_manifests()

            logger.info("[LIBRARIAN] Skill reindexing and routing sync complete.")
        except Exception as e:
            logger.error(f"[LIBRARIAN] Reindexing pipeline failed: {e}", exc_info=True)
            raise