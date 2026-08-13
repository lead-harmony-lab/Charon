#!/usr/bin/env python3
"""
scripts/inject_legacy_agent_permissions.py

Scans legacy agent directories in `charon/agents_delete/<agent_id>/staging/skills/`
to map skill folder names to allowed agents, then injects these permission bindings
directly into the `manifest.json` files within dynamic skill storage.

Defaults to CLI Dry-Run mode. Pass `--live` to apply changes.
"""

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("charon.scripts.inject_permissions")

# Dynamically resolve CHARON_ROOT based on script location
current_dir = Path(__file__).resolve().parent
CHARON_ROOT = current_dir
while CHARON_ROOT.name.lower() != "charon" and CHARON_ROOT.parent != CHARON_ROOT:
    CHARON_ROOT = CHARON_ROOT.parent

if CHARON_ROOT.name.lower() != "charon":
    CHARON_ROOT = Path("~/Projects/Tools/Charon").expanduser()

LEGACY_AGENTS_DIR = CHARON_ROOT / "charon" / "agents_delete"

# Dynamic skill storage paths
PKG_DYNAMIC_SKILLS_DIR = CHARON_ROOT / "charon" / "cli" / "librarian" / "storage" / "dynamic"
DYNAMIC_SKILLS_DIR = Path("~/.local/share/charon/storage/dynamic").expanduser()


def scan_legacy_agent_skills() -> Dict[str, Set[str]]:
    """
    Scans charon/agents_delete/<agent_id>/staging/skills/
    Returns a mapping of skill_folder_name -> set of agent_ids.
    """
    skill_to_agents: Dict[str, Set[str]] = defaultdict(set)

    if not LEGACY_AGENTS_DIR.exists():
        logger.error(f"❌ Legacy agents directory not found at: {LEGACY_AGENTS_DIR}")
        return skill_to_agents

    for agent_dir in sorted(LEGACY_AGENTS_DIR.iterdir()):
        if not agent_dir.is_dir():
            continue

        agent_id = agent_dir.name  # Agent ID from directory name
        skills_dir = agent_dir / "staging" / "skills"

        if not skills_dir.exists():
            continue

        for skill_folder in skills_dir.iterdir():
            if skill_folder.is_dir():
                skill_to_agents[skill_folder.name].add(agent_id)

    return skill_to_agents


def inject_permissions_into_manifests(dry_run: bool = True) -> None:
    """Scans dynamic storage directories and injects allowed_agents into manifest.json files."""
    mode_header = "🔍 [DRY RUN MODE - NO FILES WILL BE WRITTEN]" if dry_run else "⚡ [LIVE RUN - MODIFYING MANIFESTS]"
    print("\n" + "=" * 75)
    logger.info(mode_header)
    print("=" * 75)

    skill_agent_map = scan_legacy_agent_skills()

    if not skill_agent_map:
        logger.warning("⚠️ No legacy skill mappings discovered.")
        return

    logger.info(f"ℹ️ Discovered legacy mappings for {len(skill_agent_map)} skill folder(s).")

    search_roots = [PKG_DYNAMIC_SKILLS_DIR, DYNAMIC_SKILLS_DIR]
    updated_count = 0
    unmatched_skills = set(skill_agent_map.keys())

    for root in search_roots:
        if not root or not root.exists():
            continue

        for manifest_path in root.rglob("manifest.json"):
            folder_name = manifest_path.parent.name

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"⚠️ Failed to read manifest at {manifest_path}: {e}")
                continue

            skill_id = data.get("skill_id", folder_name)
            norm_id = skill_id.lower().replace("sk_", "")

            # Match against folder name, explicit skill_id, or normalized skill_id
            target_agents = (
                skill_agent_map.get(folder_name, set())
                | skill_agent_map.get(skill_id, set())
                | skill_agent_map.get(norm_id, set())
            )

            if not target_agents:
                continue

            # Remove matches from unmatched list
            unmatched_skills.discard(folder_name)
            unmatched_skills.discard(skill_id)
            unmatched_skills.discard(norm_id)

            existing_agents = set(data.get("allowed_agents", []))
            merged_agents = sorted(list(existing_agents | target_agents))

            # Only flag if there are changes to be made
            if merged_agents != data.get("allowed_agents"):
                updated_count += 1
                if dry_run:
                    logger.info(
                        f" 🔍 [WOULD UPDATE] '{skill_id}' ({folder_name}):\n"
                        f"     Current  : {data.get('allowed_agents', [])}\n"
                        f"     Proposed : {merged_agents}\n"
                        f"     File     : {manifest_path}\n"
                    )
                else:
                    data["allowed_agents"] = merged_agents
                    try:
                        with open(manifest_path, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2)
                        logger.info(
                            f" ✅ Injected agents {merged_agents} -> '{skill_id}' ({folder_name})"
                        )
                    except Exception as e:
                        logger.error(f"❌ Failed to save manifest at {manifest_path}: {e}")

    print("\n" + "=" * 75)
    summary_action = "would be updated" if dry_run else "were updated"
    logger.info(f"🎉 Process Complete: {updated_count} manifest file(s) {summary_action}.")
    if unmatched_skills:
        logger.warning(
            f"⚠️ Legacy Skills without a matching manifest in dynamic storage ({len(unmatched_skills)}):\n"
            f"   {sorted(list(unmatched_skills))}"
        )
    print("=" * 75 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Inject legacy agent permissions into dynamic skill manifests."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Apply changes to disk. Defaults to dry-run mode if omitted.",
    )
    args = parser.parse_args()

    inject_permissions_into_manifests(dry_run=not args.live)