#!/usr/bin/env python3
import datetime
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
OUTPUT_DIR = ROOT / "notebook_sources"
OUTPUT_DIR.mkdir(exist_ok=True)

# Domain targets mapping files, directories, and globs
DOMAINS = {
    "01_Specs_and_Architecture": [
        "*.md",  # Root markdown files (README, CONTEXT, PLANNING, etc.)
        "pyproject.toml",
        "docs"  # All docs/ subdirectories (design, planning, architecture)
    ],
    "02_Core_Engine_and_State": [
        "charon/core"
    ],
    "03_Gateway_CLI_and_IPC": [
        "charon/daemon.py",
        "charon/sdk.py",
        "charon/skill_forge_cli.py",
        "charon/exceptions.py",
        "charon/__version__.py",
        "charon/gateway",
        "charon/cli",
        "charon/telemetry"
    ],
    "04a_Agents_Cognition": [
        "charon/agents/base.py",
        "charon/agents/planner",
        "charon/agents/engineer",
        "charon/agents/generalist",
        "charon/agents/overseer"
    ],
    "04b_Agents_Hardware_CAD": [
        "charon/agents/spark",
        "charon/agents/machinist",
        "charon/agents/steward"
    ],
    "04c_Agents_Operations": [
        "charon/agents/archivist",
        "charon/agents/quartermaster",
        "charon/agents/scout",
        "charon/agents/cleaner"
    ],
    "05_Tools_Config_and_Intent": [
        "charon/tools",
        "charon/intent",
        "charon/config",
        "charon/utils",
        "charon/nodes",
        "scripts"
    ],
    "06_PartVault_Integration": [
        "~/Projects/Tools/PartVault"  # Standalone external application repository
    ]
}

ALLOWED_EXTENSIONS = {".py", ".md", ".yml", ".yaml", ".toml"}
EXCLUDE_DIRS = {
    "__pycache__", ".git", ".venv", ".idea", "htmlcov",
    ".pytest_cache", "notebook_sources", "logs", "memory",
    ".charon_test_artifacts", "node_modules", "dist", "build"
}


def get_metadata():
    """Fetches git commit, branch, and version string for bundle headers."""
    meta = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "commit": "unknown",
        "branch": "unknown",
        "version": "unknown"
    }

    try:
        meta["commit"] = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT).decode().strip()
        meta["branch"] = subprocess.check_output(["git", "symbolic-ref", "--short", "HEAD"], cwd=ROOT).decode().strip()
    except Exception:
        pass

    pyproject = ROOT / "pyproject.toml"
    if pyproject.exists():
        match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', pyproject.read_text(encoding="utf-8"))
        if match:
            meta["version"] = match.group(1)

    return meta


def collect_files(target_str):
    """Resolves local, absolute, wildcard, or external home-directory (~/) paths."""
    collected = set()
    raw_path = Path(target_str).expanduser()

    # Handle wildcards (e.g. *.md)
    if "*" in target_str:
        search_root = raw_path.parent if raw_path.is_absolute() else (ROOT / raw_path).parent
        pattern = raw_path.name
        if search_root.exists():
            for p in search_root.glob(pattern):
                if p.is_file() and p.suffix in ALLOWED_EXTENSIONS:
                    collected.add(p)
        return collected

    target_path = raw_path if raw_path.is_absolute() else (ROOT / target_str).resolve()

    if not target_path.exists():
        print(f"  [Warning] Path not found: {target_str} (resolved to {target_path})")
        return collected

    if target_path.is_file():
        if target_path.suffix in ALLOWED_EXTENSIONS:
            return {target_path}
        return collected

    # Recurse through target directory
    for root, dirs, filenames in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for f in filenames:
            file_path = Path(root) / f
            if file_path.suffix in ALLOWED_EXTENSIONS and not f.startswith("."):
                collected.add(file_path)

    return collected


def get_language_tag(suffix):
    """Maps file extensions to Markdown code block language identifiers."""
    if suffix == ".py":
        return "python"
    elif suffix in {".yml", ".yaml"}:
        return "yaml"
    elif suffix == ".toml":
        return "toml"
    return "markdown"


def main():
    print("🚀 Bundling Charon codebase & PartVault integration into NotebookLM sources...")
    meta = get_metadata()
    processed_files = set()

    for domain_name, targets in DOMAINS.items():
        outfile = OUTPUT_DIR / f"{domain_name}.md"
        print(f"\nProcessing domain: {domain_name}")

        domain_files = set()
        for target in targets:
            domain_files.update(collect_files(target))

        new_files = sorted(domain_files - processed_files)
        file_count = 0

        with open(outfile, "w", encoding="utf-8") as out:
            out.write(f"# Subsystem Domain Context: {domain_name}\n")
            out.write(f"> **Generated:** {meta['timestamp']}  \n")
            out.write(f"> **Charon Core Version:** v{meta['version']}  \n")
            out.write(f"> **Git Branch:** `{meta['branch']}` | **Commit:** `{meta['commit']}`\n\n")
            out.write("---\n\n")

            for file_path in new_files:
                try:
                    content = file_path.read_text(encoding="utf-8")

                    # Display path relative to ROOT if internal, else display absolute path
                    try:
                        display_path = file_path.relative_to(ROOT)
                    except ValueError:
                        display_path = file_path

                    out.write(f"## Target File: `{display_path}`\n\n")

                    lang = get_language_tag(file_path.suffix)
                    out.write(f"```{lang}\n{content}\n```\n\n")
                    out.write("─" * 80 + "\n\n")

                    file_count += 1
                    processed_files.add(file_path)
                except Exception as e:
                    print(f"  Failed reading {file_path}: {e}")

        print(f"  Created {outfile.name} ({file_count} files included)")

    # Repository-wide catch-all for any missed local Charon files
    all_repo_files = set()
    for root, dirs, filenames in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for f in filenames:
            file_path = Path(root) / f
            if file_path.suffix in ALLOWED_EXTENSIONS and not f.startswith("."):
                all_repo_files.add(file_path)

    uncategorized = sorted(all_repo_files - processed_files)
    if uncategorized:
        print(f"\n⚠️ Found {len(uncategorized)} unassigned files! Bundling into 99_Uncategorized.md...")
        outfile = OUTPUT_DIR / "99_Uncategorized.md"
        with open(outfile, "w", encoding="utf-8") as out:
            out.write(f"# Subsystem Domain Context: 99_Uncategorized\n")
            out.write(f"> **Commit:** `{meta['commit']}` | **Version:** v{meta['version']}\n\n---\n\n")
            for file_path in uncategorized:
                content = file_path.read_text(encoding="utf-8")
                lang = get_language_tag(file_path.suffix)
                out.write(
                    f"## Target File: `{file_path.relative_to(ROOT)}`\n\n```{lang}\n{content}\n```\n\n" + "─" * 80 + "\n\n")
                processed_files.add(file_path)

    print(f"\n✨ Done! Source bundles saved to: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
