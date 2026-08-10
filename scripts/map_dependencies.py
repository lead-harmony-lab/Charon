#!/usr/bin/env python3
import ast
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.resolve()
CHARON_DIR = ROOT_DIR / "charon"


def get_imports_from_file(filepath: Path) -> set[str]:
    """Parses a Python file using AST to extract internal `charon` imports."""
    imports = set()
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("charon"):
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("charon"):
                imports.add(node.module)

    return imports


def module_path_to_relative(mod_str: str) -> str:
    """Converts a module string (e.g. charon.core.engine) to relative path format."""
    return mod_str.replace(".", "/") + ".py"


def main():
    graph = defaultdict(set)
    all_files = list(CHARON_DIR.rglob("*.py"))

    # Map file relative path -> internal imported modules
    for filepath in all_files:
        rel_path = str(filepath.relative_to(ROOT_DIR))
        imported_mods = get_imports_from_file(filepath)

        for mod in imported_mods:
            # Map module back to relative file path if it exists
            target_rel = module_path_to_relative(mod)
            if (ROOT_DIR / target_rel).exists():
                graph[rel_path].add(target_rel)
            else:
                # Check if it's a directory package (__init__.py)
                dir_target = mod.replace(".", "/") + "/__init__.py"
                if (ROOT_DIR / dir_target).exists():
                    graph[rel_path].add(dir_target)

    print("=" * 60)
    print("CHARON CODEBASE DEPENDENCY MAP")
    print("=" * 60)

    for source, targets in sorted(graph.items()):
        if targets:
            print(f"\n📄 {source}")
            for t in sorted(targets):
                print(f"   └──> {t}")

    # Circular Dependency Check
    print("\n" + "=" * 60)
    print("CIRCULAR DEPENDENCY CHECK")
    print("=" * 60)
    circular_found = False
    for source, targets in graph.items():
        for target in targets:
            if source in graph.get(target, set()):
                print(f"⚠️ CIRCULAR DEPENDENCY: {source} <---> {target}")
                circular_found = True

    if not circular_found:
        print("✅ No direct circular dependencies detected across charon/")

    # Generate Mermaid Diagram
    print("\n" + "=" * 60)
    print("MERMAID.JS DIAGRAM (Copy into Markdown viewer or PyCharm Preview)")
    print("=" * 60)
    print("```mermaid")
    print("graph TD")
    for source, targets in sorted(graph.items()):
        src_clean = source.replace("charon/", "").replace(".py", "").replace("/", "_")
        for target in sorted(targets):
            tgt_clean = (
                target.replace("charon/", "").replace(".py", "").replace("/", "_")
            )
            print(f"    {src_clean} --> {tgt_clean}")
    print("```\n")


if __name__ == "__main__":
    main()
