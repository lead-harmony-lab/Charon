"""
charon/core/skills/indexer.py
System Version: v0.6.3 | File Revision: 7.4.1

Module: Dynamic discovery, skill promotion, route syncing, database re-indexing,
and stale mapping purge mixin.
Maintains clean separation between immutable code identifiers (skill_id) and prompt contracts (action_name).
Enforces deterministic 3-node canonical naming convention (<category>_<context>_<verb>) for database action_name contracts.
Integrates AST-based plugin inspection to eliminate redundant/stuttering contract names.
All direct SQL execution extracted to repository layer.
Integrates CBAC Schema V2 permission indexing and quarantine status preservation.
Enforces strict fail-fast role resolution against database registry.
"""

import ast
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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

    def _extract_plugin_context(self, entry_file: Optional[Path]) -> List[str]:
        """
        Parses plugin.py via AST to extract candidate context tokens from function names,
        class names, and top-level definitions when manifest metadata is minimal.
        """
        if not entry_file or not entry_file.exists():
            return []

        tokens: List[str] = []
        try:
            source_code = entry_file.read_text(encoding="utf-8")
            tree = ast.parse(source_code)

            for node in ast.walk(tree):
                # Extract from function names (e.g., 'handle_specialist_output' -> ['specialist', 'output'])
                if isinstance(node, ast.FunctionDef):
                    fn_name = node.name.lower()
                    clean_fn = fn_name.replace("handle_", "").replace("execute_", "").replace("run_", "")
                    parts = [p for p in clean_fn.split("_") if p]
                    tokens.extend(parts)

                # Extract from class names (e.g., 'SpecialistSynthesizer' -> ['specialist', 'synthesizer'])
                elif isinstance(node, ast.ClassDef):
                    class_name = node.name
                    words = re.findall(r"[A-Z][a-z]*", class_name)
                    tokens.extend([w.lower() for w in words])

        except Exception as e:
            logger.debug(f"[LIBRARIAN] AST context extraction skipped for {entry_file}: {e}")

        # Filter out standard framework stop words
        stopwords = {
            "self", "args", "kwargs", "handle", "execute", "run", "plugin",
            "base", "skill", "action", "context", "process", "main", "helper"
        }
        return [t for t in tokens if t not in stopwords]

    def _derive_canonical_action_name(
        self,
        category: Optional[str],
        skill_id: str,
        raw_action: str,
        entry_file: Optional[Path] = None,
        shelf_tags: Optional[List[str]] = None,
    ) -> str:
        """
        Constructs a pristine 3-node canonical action_name (<cat>_<context>_<verb>).
        Uses token subtraction to prevent stuttering without relying on fragile AST parsing.
        """
        # 1. Category Node
        clean_cat = (category or "general").lower().strip().replace("-", "_").replace(" ", "_")
        cat_node = clean_cat.split("_")[0]

        # 2. Context Node (Extract from skill_id, subtracting the category word)
        clean_id = skill_id.lower().strip().replace("-", "_").replace(" ", "_").replace("skill_", "")
        context_parts = [p for p in clean_id.split("_") if p != cat_node]
        context_node = context_parts[0] if context_parts else "core"

        # 3. Verb Node (Extract from raw_action, subtracting category and context words)
        clean_action = raw_action.lower().strip().replace("-", "_").replace(" ", "_")
        action_parts = [p for p in clean_action.split("_") if p not in (cat_node, context_node)]
        verb_node = action_parts[0] if action_parts else "execute"

        # 4. Smart Anti-Stutter (Targeted linguistic checks, no blind suffixing)
        if verb_node == context_node or context_node == f"{verb_node}r" or context_node == f"{verb_node}er":
            verb_node = "execute"

        return f"{cat_node}_{context_node}_{verb_node}"

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

    def purge_stale_mappings(self, active_skill_ids: Set[str]) -> Dict[str, int]:
        """
        Identifies and removes stale skill entries and mappings across SQLite tables.

        Removes:
        1. skill_registry rows for missing plugin files/manifests not present in active_skill_ids.
        2. agent_skill_map rows pointing to non-existent skills or inactive agents.
        3. route_registry rows referencing unindexed skills.
        """
        logger.info("[LIBRARIAN] Initiating stale mapping purge cycle...")
        purged_stats = {
            "purged_skills": 0,
            "purged_agent_mappings": 0,
            "purged_routes": 0,
        }

        try:
            # 1. Delegate repository-level cleanup of orphaned skill records
            if hasattr(self.repo, "purge_unindexed_skills"):
                purged_stats["purged_skills"] = self.repo.purge_unindexed_skills(active_skill_ids)
            elif hasattr(self.repo, "purge_stale_skills"):
                purged_stats["purged_skills"] = self.repo.purge_stale_skills(active_skill_ids)

            # 2. Cleanup orphaned permission mappings in agent_skill_map
            if hasattr(self.repo, "purge_orphaned_agent_skill_mappings"):
                purged_stats["purged_agent_mappings"] = (
                    self.repo.purge_orphaned_agent_skill_mappings()
                )

            # 3. Cleanup dangling route entries in route_registry
            if hasattr(self.route_repo, "purge_stale_routes"):
                purged_stats["purged_routes"] = self.route_repo.purge_stale_routes()

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
        Unified pipeline for skill indexing, route synchronization, and optional stale purging.
        Establishes skill_registry entries and maps agent capability FKs via agent_skill_map.
        Transforms local manifest action verbs into deterministic 3-node canonical action names.
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

            # Pass 1: Index skills into skill_registry and dynamically append to agent_skill_map
            for manifest_path in processed_manifests:
                try:
                    raw_text = manifest_path.read_text(encoding="utf-8")
                    raw_json = json.loads(raw_text)
                    manifest = SkillManifest.model_validate_json(raw_text)
                    entry_file = manifest_path.parent / "plugin.py"

                    if not entry_file.exists():
                        logger.warning(
                            f"[LIBRARIAN] Plugin implementation missing at '{entry_file}' for '{manifest.skill_id}'."
                        )
                        continue

                    allowed_agents_list = getattr(manifest, "allowed_agents", []) or raw_json.get(
                        "allowed_agents", []
                    )
                    if isinstance(allowed_agents_list, str):
                        allowed_agents_list = [allowed_agents_list]

                    is_global = 1 if ("*" in allowed_agents_list or getattr(manifest, "is_global", False)) else 0
                    total_actions = len(manifest.supported_actions)

                    # --- Path-aware status check ---
                    manifest_path_str = manifest_path.as_posix()
                    if "/storage/staged/" in manifest_path_str or "/staged/" in manifest_path_str:
                        status = "STAGED"
                    else:
                        status = getattr(manifest, "status", "ACTIVE") or raw_json.get("status", "ACTIVE")

                    quarantine_reason = getattr(manifest, "quarantine_reason", None) or raw_json.get("quarantine_reason", None)
                    required_permissions = getattr(manifest, "required_permissions", []) or raw_json.get("required_permissions", [])
                    shelf_tags = getattr(manifest, "shelf_tags", []) or raw_json.get("shelf_tags", [])

                    for action_name, action_def in manifest.supported_actions.items():

                        # 1. Trust the manifest first. If it defines an action_name, use it.
                        manifest_action_name = getattr(manifest, "action_name", None) or raw_json.get("action_name")

                        if manifest_action_name:
                            canonical_action_name = manifest_action_name
                        else:
                            # 2. Legacy Fallback: Only derive if the manifest is an older alpha format
                            logger.info(f"[LIBRARIAN] Upgrading legacy action name for '{manifest.skill_id}'")
                            canonical_action_name = self._derive_canonical_action_name(
                                category=manifest.category,
                                skill_id=manifest.skill_id,
                                raw_action=action_name,
                                entry_file=entry_file,
                                shelf_tags=shelf_tags,
                            )

                        # Strictly respect the immutable code identifier from the manifest
                        action_skill_id = manifest.skill_id

                        # Synthesize the handler name from the established action name
                        canonical_parts = canonical_action_name.split("_")
                        if len(canonical_parts) >= 3:
                            context_node = canonical_parts[1]
                            verb_node = canonical_parts[2]
                            standardized_handler_name = f"handle_{context_node}_{verb_node}"
                        else:
                            # Fallback for non-standard names
                            standardized_handler_name = f"handle_{canonical_action_name}"

                        discovered_skill_ids.add(action_skill_id)
                        discovered_skill_ids.add(manifest.skill_id)

                        if isinstance(action_def, dict):
                            desc = action_def.get(
                                "description",
                                manifest.description or f"Executes '{action_name}'",
                            )
                            params = action_def.get("parameters", {})
                        else:
                            desc = manifest.action_descriptions.get(
                                action_name,
                                manifest.description or f"Executes '{action_name}'",
                            )
                            params = manifest.action_parameters.get(action_name, {})

                        # Upsert skill contract record using derived 3-node action_name and synthesized handler
                        self.repo.upsert_skill(
                            skill_id=action_skill_id,
                            action_name=canonical_action_name,
                            version=manifest.version,
                            category=manifest.category,
                            description=desc,
                            parameters=params,
                            system_requirements=manifest.system_requirements,
                            consumed_artifacts=manifest.consumed_artifacts,
                            produced_artifacts=manifest.produced_artifacts,
                            entry_file_path=str(entry_file.resolve()),
                            handler_name=standardized_handler_name,
                            is_global=is_global,
                            status=status,
                            quarantine_reason=quarantine_reason,
                            required_permissions=required_permissions,
                        )

                        # Link agents additively
                        if is_global:
                            active_agents = self.agent_repo.get_active_agent_ids()
                            for agent_id in active_agents:
                                self.repo.link_agent_to_skill(agent_id, action_skill_id)
                        else:
                            for raw_agent_id in allowed_agents_list:
                                if raw_agent_id == "*":
                                    continue
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

            # Pass 2: Purge stale mappings if requested
            if purge_stale:
                self.purge_stale_mappings(discovered_skill_ids)

            # Pass 3: Sync route_registry via RouteRepository
            self.route_repo.sync_dynamic_routes()

            # Pass 4: Invalidate and reload in-memory manifest cache
            if hasattr(self, "reload_all_manifests"):
                self.reload_all_manifests()

            logger.info("[LIBRARIAN] Skill reindexing and routing sync complete.")
        except Exception as e:
            logger.error(f"[LIBRARIAN] Reindexing pipeline failed: {e}", exc_info=True)
            raise