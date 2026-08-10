import argparse
import re
from pathlib import Path

def parse_and_restore(sources_dir: Path, dry_run: bool = True):
    if not sources_dir.exists():
        print(f"❌ Error: Directory '{sources_dir}' not found.")
        return

    md_files = sorted(list(sources_dir.glob("*.md")))
    if not md_files:
        print(f"❌ No .md files found in '{sources_dir}'.")
        return

    print(f"🔍 Found {len(md_files)} markdown bundle(s) in '{sources_dir}'.")
    if dry_run:
        print("⚠️  DRY RUN MODE ENABLED — No files will be created or modified on disk.\n")
    else:
        print("🚀 LIVE RESTORE MODE — Recovering missing files...\n")

    # Regex matches: ## Target File: `filepath` followed by ```lang ... ```
    pattern = re.compile(
        r"## Target File:\s*[`'\"]?(?P<filepath>[^`'\"]+?)[`'\"]?\s*\n+"
        r"```[a-zA-Z0-9_-]*\n"
        r"(?P<code>.*?)"
        r"\n```",
        re.MULTILINE | re.DOTALL
    )

    restored_count = 0
    skipped_count = 0

    for md_file in md_files:
        print(f"--- Scanning {md_file.name} ---")
        text = md_file.read_text(encoding="utf-8", errors="ignore")

        matches = list(pattern.finditer(text))
        if not matches:
            print("  (No target files matched in this bundle)")
            continue

        for match in matches:
            rel_path = match.group("filepath").strip()
            code = match.group("code")
            target_file = Path(rel_path)

            # 🔒 HARD SAFEGUARD: Never touch a file that exists on disk
            if target_file.exists():
                print(f"  [PRESERVED] Existing file protected: {target_file}")
                skipped_count += 1
                continue

            if dry_run:
                print(f"  [WOULD RESTORE] Missing file: {target_file}")
            else:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(code + "\n", encoding="utf-8")
                print(f"  [RESTORED] Recreated missing file: {target_file}")

            restored_count += 1

    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"  • Existing files protected (skipped): {skipped_count}")
    if dry_run:
        print(f"  • Missing files identified for restore: {restored_count}")
        print("\n💡 To write missing files to disk, run with `--live`:")
        print("   python restore_missing_sources.py --live")
    else:
        print(f"  • Missing files successfully restored: {restored_count}")
    print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Safely restore missing Charon files from notebook bundles.")
    parser.add_argument("--live", action="store_true", help="Execute live restoration (default is dry-run)")
    parser.add_argument("--dir", default="notebook_sources", help="Path to notebook sources directory")
    args = parser.parse_args()

    parse_and_restore(Path(args.dir), dry_run=not args.live)