#!/usr/bin/env python3
"""
scripts/bump_version.py — Automated SemVer bumper, header syncer, and Git tagger.
"""

import argparse
from pathlib import Path
import re
import subprocess
import sys

from scripts.standardize_headers import main as sync_headers

VERSION_FILE = Path(__file__).resolve().parents[1] / "charon" / "__version__.py"


def parse_version(v_str: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", v_str.strip())
    if not match:
        raise ValueError(f"Invalid SemVer string: '{v_str}'")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_version(part: str) -> str:
    content = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        raise RuntimeError("Could not find __version__ in charon/__version__.py")

    current_str = match.group(1)
    major, minor, patch = parse_version(current_str)

    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "patch":
        patch += 1

    new_version = f"{major}.{minor}.{patch}"
    new_content = re.sub(
        r'__version__\s*=\s*["\']([^"\']+)["\']',
        f'__version__ = "{new_version}"',
        content,
    )
    VERSION_FILE.write_text(new_content, encoding="utf-8")
    return new_version


def main():
    parser = argparse.ArgumentParser(description="Bump Charon SemVer, sync file headers, and optionally Git tag.")
    parser.add_argument("part", choices=["major", "minor", "patch"], help="Part of SemVer to bump")
    parser.add_argument("--tag", action="store_true", help="Automatically commit change and create git tag")
    args = parser.parse_args()

    try:
        new_v = bump_version(args.part)
        print(f"Successfully bumped project version to v{new_v}")

        # Sync headers across codebase
        sync_headers()

        if args.tag:
            repo_root = VERSION_FILE.parents[1]
            subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
            subprocess.run(["git", "commit", "-m", f"chore(release): bump version to v{new_v}"], cwd=repo_root, check=True)
            subprocess.run(["git", "tag", "-a", f"v{new_v}", "-m", f"Release v{new_v}"], cwd=repo_root, check=True)
            print(f"Created Git commit and tag: v{new_v}")

    except Exception as e:
        print(f"Error bumping version: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
