"""
charon/tools/code.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: tools/code.py
Module: Stateless utility functions for AST code auditing, workspace path extraction, and subshell sandbox execution.
"""

import ast
import asyncio
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from charon.config.paths import PROJECTS_DIR, resolve_project_path


def extract_target_directory(prompt: str) -> Optional[str]:
    """Dynamically resolves target workspace directories from explicit paths (POSIX & Windows),
    retrieved ledger rules, or relative project names within prompt text.
    """
    # Matches POSIX absolute paths (/foo/bar) and Windows paths (C:\foo\bar or C:/foo/bar)
    abs_matches = re.findall(
        r"(?:[a-zA-Z]:[\\/][\w.-]+(?:[\\/][\w.-]+)+|/(?:[\w.-]+(?:/[\w.-]+)+))",
        prompt,
    )
    abs_matches.sort(key=len, reverse=True)
    for match in abs_matches:
        path = Path(match)
        if path.is_dir():
            return str(path.resolve())
        elif path.parent.is_dir():
            return str(path.parent.resolve())

    base_dirs = []
    base_rule_matches = re.findall(
        r"(?:~/|/|[a-zA-Z]:[\\/])[a-zA-Z0-9_.-]+(?:[\\/][a-zA-Z0-9_.-]+)*",
        prompt,
    )
    for rule in base_rule_matches:
        expanded = Path(rule).expanduser()
        if expanded.is_dir():
            base_dirs.append(expanded)

    default_projects = PROJECTS_DIR
    if default_projects.is_dir() and default_projects not in base_dirs:
        base_dirs.append(default_projects)

    proj_match = re.search(
        r"(?:project|workspace|repo|bot)\s+([a-zA-Z0-9_.-]+)",
        prompt,
        re.IGNORECASE,
    )
    if proj_match:
        proj_name = proj_match.group(1).strip()
        try:
            resolved = resolve_project_path(proj_name)
            if resolved.is_dir():
                return str(resolved)
        except Exception:
            pass

        for base in base_dirs:
            candidate = base / proj_name
            if candidate.is_dir():
                return str(candidate.resolve())

    return None


def audit_written_artifacts(code: str, cwd: str) -> Tuple[bool, str]:
    """Parses code AST to detect file write calls via open() or Path.write_*()
    and verifies disk creation post-execution. Tracks simple variable assignments.
    """
    try:
        tree = ast.parse(code)
    except Exception as e:
        return False, f"AST Parse Error: {e}"

    created_files = []
    missing_files = []

    # Symbol tables for tracked variables
    str_vars: Dict[str, str] = {}
    path_vars: Dict[str, str] = {}

    for node in ast.walk(tree):
        # Track variable assignments: x = "file.txt" or p = Path("file.txt")
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                var_name = node.targets[0].id

                # Case 1: var = "filename.txt"
                if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str
                ):
                    str_vars[var_name] = node.value.value

                # Case 2: var = Path("filename.txt") or Path(var2)
                elif (
                    isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "Path"
                    and node.value.args
                ):
                    arg0 = node.value.args[0]
                    if isinstance(arg0, ast.Constant) and isinstance(
                        arg0.value, str
                    ):
                        path_vars[var_name] = arg0.value
                    elif isinstance(arg0, ast.Name) and arg0.id in str_vars:
                        path_vars[var_name] = str_vars[arg0.id]

        if not isinstance(node, ast.Call):
            continue

        func = node.func
        target_filename: Optional[str] = None
        is_write_mode = False

        # --- open(...) Calls ---
        if isinstance(func, ast.Name) and func.id == "open":
            if node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(
                    first_arg.value, str
                ):
                    target_filename = first_arg.value
                elif isinstance(first_arg, ast.Name) and first_arg.id in str_vars:
                    target_filename = str_vars[first_arg.id]

            mode = "r"
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            elif any(k.arg == "mode" for k in node.keywords):
                mode_kw = next(k for k in node.keywords if k.arg == "mode")
                if isinstance(mode_kw.value, ast.Constant):
                    mode = str(mode_kw.value.value)

            clean_mode = mode.translate(str.maketrans("", "", "rbt"))
            if clean_mode and any(m in clean_mode for m in ["w", "a", "x", "+"]):
                is_write_mode = True

        # --- Path methods (.write_text, .write_bytes, .open) ---
        elif isinstance(func, ast.Attribute) and func.attr in (
            "write_text",
            "write_bytes",
            "open",
        ):
            if func.attr in ("write_text", "write_bytes"):
                is_write_mode = True
            elif func.attr == "open":
                mode = "r"
                if node.args and isinstance(node.args[0], ast.Constant):
                    mode = str(node.args[0].value)
                elif any(k.arg == "mode" for k in node.keywords):
                    mode_kw = next(k for k in node.keywords if k.arg == "mode")
                    if isinstance(mode_kw.value, ast.Constant):
                        mode = str(mode_kw.value.value)

                clean_mode = mode.translate(str.maketrans("", "", "rbt"))
                if clean_mode and any(m in clean_mode for m in ["w", "a", "x", "+"]):
                    is_write_mode = True

            # Case A: Inline Path("out.txt").write_text(...)
            if (
                isinstance(func.value, ast.Call)
                and isinstance(func.value.func, ast.Name)
                and func.value.func.id == "Path"
            ):
                if (
                    func.value.args
                    and isinstance(func.value.args[0], ast.Constant)
                    and isinstance(func.value.args[0].value, str)
                ):
                    target_filename = func.value.args[0].value
                elif (
                    func.value.args
                    and isinstance(func.value.args[0], ast.Name)
                    and func.value.args[0].id in str_vars
                ):
                    target_filename = str_vars[func.value.args[0].id]

            # Case B: Variable path p.write_text(...) where p was assigned Path(...)
            elif isinstance(func.value, ast.Name) and func.value.id in path_vars:
                target_filename = path_vars[func.value.id]

        if is_write_mode and target_filename:
            target_path = Path(cwd) / target_filename
            if target_path.exists():
                created_files.append(str(target_path))
            else:
                missing_files.append(str(target_path))

    if missing_files:
        prefix = (
            f"{len(created_files)} file artifact(s) created. "
            if created_files
            else ""
        )
        return (
            False,
            f"{prefix}AST Disk Audit Warning: Script reported success, but expected output file(s) were missing on disk: {', '.join(missing_files)}",
        )

    audit_msg = (
        f"AST Disk Audit Verified: {len(created_files)} file artifact(s) created."
        if created_files
        else "AST Disk Audit Passed (No disk write calls detected)."
    )
    return True, audit_msg


async def run_script_in_subprocess(
    code: str,
    cwd: str,
    python_cmd: str = sys.executable,
    timeout: float = 30.0,
    stream_callback: Optional[Callable[[str], None]] = None,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[str, bool]:
    """Executes a code string in an isolated temporary Python subshell with strict execution timeout limits."""
    temp_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    )
    try:
        temp_file.write(code)
        temp_file.flush()
        temp_file.close()

        exec_kwargs: Dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
        }
        if os.path.exists(cwd):
            exec_kwargs["cwd"] = cwd

        if env is not None:
            exec_kwargs["env"] = env

        process = await asyncio.create_subprocess_exec(
            python_cmd, temp_file.name, **exec_kwargs
        )

        output_chunks: list[str] = []

        async def _read_stream(stream: Optional[asyncio.StreamReader]):
            if stream is None:
                return
            while True:
                line = await stream.readline()
                if not line:
                    break
                chunk = line.decode("utf-8", errors="replace")
                output_chunks.append(chunk)
                if stream_callback:
                    try:
                        stream_callback(chunk)
                    except Exception:
                        pass

        async def _run_and_read() -> int:
            stream_tasks = []
            if process.stdout is not None:
                stream_tasks.append(_read_stream(process.stdout))
            if process.stderr is not None and process.stderr != process.stdout:
                stream_tasks.append(_read_stream(process.stderr))

            if stream_tasks:
                await asyncio.gather(*stream_tasks)

            await process.wait()
            return process.returncode if process.returncode is not None else -1

        try:
            task = asyncio.create_task(_run_and_read())
            return_code = await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return (
                f"Execution TimeoutError: Process terminated after exceeding {timeout}s limit.",
                False,
            )

        full_output = "".join(output_chunks).strip()
        return full_output, (return_code == 0)

    except Exception as e:
        return f"Execution Error: {str(e)}", False
    finally:
        if os.path.exists(temp_file.name):
            try:
                os.remove(temp_file.name)
            except OSError:
                pass
