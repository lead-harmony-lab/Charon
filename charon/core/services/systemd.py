"""
charon/services/systemd.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Core Systemd Service Manager Implementation.
Handles subprocess commands, JSON configuration persistence for registered units,
unit file content modification, batch queries, and uptime parsing.
"""

import asyncio
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("Charon.Services.Systemd")

UNIT_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_@.\-]+$")
ALLOWED_ACTIONS = {"start", "stop", "restart", "reload"}
SETTINGS_FILE = Path.home() / ".config" / "charon" / "registered_services.json"


def _ensure_settings_dir() -> None:
    """Ensures settings directory and initial file exist."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        default_units = [{"name": "charond.service", "scope": "user"}]
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_units, f, indent=2)


def get_registered_units() -> List[Dict[str, str]]:
    """Reads saved units of interest from the settings file."""
    _ensure_settings_dir()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as err:
        logger.error(f"Failed to read registered services settings: {err}")
        return []


def register_unit(name: str, scope: str = "user") -> List[Dict[str, str]]:
    """Registers a new service unit to the settings file."""
    if not UNIT_NAME_REGEX.match(name):
        raise ValueError(f"Invalid unit name format: '{name}'")

    scope = scope.lower()
    if scope not in ("user", "system"):
        raise ValueError(f"Invalid scope '{scope}'. Must be 'user' or 'system'.")

    units = get_registered_units()
    if not any(u["name"] == name for u in units):
        units.append({"name": name, "scope": scope})
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(units, f, indent=2)
    return units


def unregister_unit(name: str) -> List[Dict[str, str]]:
    """Removes a service unit from the settings file."""
    units = get_registered_units()
    units = [u for u in units if u["name"] != name]
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(units, f, indent=2)
    return units


async def _run_command(*args: str) -> str:
    """Executes a subprocess CLI command asynchronously and returns stdout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode().strip() or f"Process exited with code {proc.returncode}"
            raise RuntimeError(err_msg)
        return stdout.decode().strip()
    except FileNotFoundError:
        raise FileNotFoundError("systemctl executable not found on host operating system.")


def format_uptime(active_enter_timestamp: str) -> str:
    """Parses systemctl timestamp output into a compact uptime string."""
    if not active_enter_timestamp or active_enter_timestamp in ("n/a", "0", ""):
        return "Inactive"

    try:
        # Extract YYYY-MM-DD and HH:MM:SS components ignoring weekday and timezone tokens
        parts = active_enter_timestamp.split()
        date_part = None
        time_part = None

        for part in parts:
            if re.match(r"^\d{4}-\d{2}-\d{2}$", part):
                date_part = part
            elif re.match(r"^\d{2}:\d{2}:\d{2}$", part):
                time_part = part

        if date_part and time_part:
            dt_str = f"{date_part} {time_part}"
            # Systemctl outputs timestamps in local wall-clock time; parse as naive local datetime
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            delta = datetime.now() - dt

            total_seconds = int(delta.total_seconds())
            if total_seconds < 0:
                return "Just started"

            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours >= 24:
                days = hours // 24
                rem_hours = hours % 24
                return f"{days}d {rem_hours}h"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            return f"{seconds}s"
    except Exception as err:
        logger.debug(f"Failed to parse timestamp '{active_enter_timestamp}': {err}")

    return "Active"


def _parse_systemctl_show_output(raw_output: str) -> List[Dict[str, str]]:
    """Parses key-value stdout blocks from multi-unit systemctl show queries."""
    blocks: List[Dict[str, str]] = []
    current_block: Dict[str, str] = {}

    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            if current_block:
                blocks.append(current_block)
                current_block = {}
            continue

        if "=" in line:
            key, val = line.split("=", 1)
            if key == "Id" and "Id" in current_block:
                blocks.append(current_block)
                current_block = {}
            current_block[key] = val

    if current_block:
        blocks.append(current_block)

    return blocks


async def inspect_unit(name: str, scope: str = "user") -> Dict[str, Any]:
    """Queries systemctl show properties for a single unit."""
    cmd = ["systemctl"]
    if scope == "user":
        cmd.append("--user")
    cmd.extend([
        "show",
        name,
        "--property=Id,ActiveState,SubState,LoadState,Description,ActiveEnterTimestamp,FragmentPath"
    ])

    raw = await _run_command(*cmd)
    props: Dict[str, str] = {}
    for line in raw.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k] = v

    active_state = props.get("ActiveState", "inactive")
    is_active = active_state.lower() == "active"
    uptime_str = format_uptime(props.get("ActiveEnterTimestamp", "")) if is_active else "Stopped"

    return {
        "name": props.get("Id", name),
        "active": is_active,
        "subState": props.get("SubState", "dead"),
        "loadState": props.get("LoadState", "not-found"),
        "scope": scope,
        "description": props.get("Description", ""),
        "uptime": uptime_str,
        "fragmentPath": props.get("FragmentPath", ""),
    }


async def get_monitored_units_status() -> List[Dict[str, Any]]:
    """Retrieves status for all units registered in settings using scope-grouped batch queries."""
    registered = get_registered_units()
    if not registered:
        return []

    by_scope: Dict[str, List[str]] = {"user": [], "system": []}
    for entry in registered:
        scope = entry.get("scope", "user").lower()
        if scope not in by_scope:
            by_scope[scope] = []
        by_scope[scope].append(entry["name"])

    results: List[Dict[str, Any]] = []

    for scope, unit_names in by_scope.items():
        if not unit_names:
            continue

        cmd = ["systemctl"]
        if scope == "user":
            cmd.append("--user")
        cmd.extend([
            "show",
            *unit_names,
            "--property=Id,ActiveState,SubState,LoadState,Description,ActiveEnterTimestamp,FragmentPath"
        ])

        try:
            raw_output = await _run_command(*cmd)
            blocks = _parse_systemctl_show_output(raw_output)
            unit_map = {b.get("Id", ""): b for b in blocks if "Id" in b}

            for name in unit_names:
                props = unit_map.get(name) or next(
                    (b for b in blocks if b.get("Id", "").startswith(name)), {}
                )

                active_state = props.get("ActiveState", "inactive")
                is_active = active_state.lower() == "active"
                uptime_str = format_uptime(props.get("ActiveEnterTimestamp", "")) if is_active else "Stopped"

                results.append({
                    "name": props.get("Id", name),
                    "active": is_active,
                    "subState": props.get("SubState", "dead"),
                    "loadState": props.get("LoadState", "not-found"),
                    "scope": scope,
                    "description": props.get("Description", ""),
                    "uptime": uptime_str,
                    "fragmentPath": props.get("FragmentPath", ""),
                })
        except Exception as err:
            logger.warning(f"Failed batch inspection for scope '{scope}' units {unit_names}: {err}")
            for name in unit_names:
                results.append({
                    "name": name,
                    "active": False,
                    "subState": "unknown",
                    "loadState": "error",
                    "scope": scope,
                    "description": f"Failed to fetch status: {err}",
                    "uptime": "N/A",
                    "fragmentPath": "",
                })

    return results


async def control_unit(name: str, action: str, scope: str = "user") -> None:
    """Executes start, stop, restart, or reload operations."""
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"Invalid action '{action}'. Allowed: {ALLOWED_ACTIONS}")
    if not UNIT_NAME_REGEX.match(name):
        raise ValueError(f"Invalid unit name format: '{name}'")

    cmd = ["systemctl"]
    if scope == "user":
        cmd.append("--user")
    cmd.extend([action, name])
    await _run_command(*cmd)


async def get_unit_file_content(name: str, scope: str = "user") -> str:
    """Reads raw contents of a service unit file."""
    info = await inspect_unit(name, scope)
    path = info.get("fragmentPath")
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"Unit file path not found or unreadable for '{name}'.")

    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def update_unit_file_content(name: str, content: str, scope: str = "user") -> None:
    """Updates unit file content and issues daemon-reload."""
    info = await inspect_unit(name, scope)
    path = info.get("fragmentPath")
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"Unit file path not found for '{name}'. Cannot write file.")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    reload_cmd = ["systemctl"]
    if scope == "user":
        reload_cmd.append("--user")
    reload_cmd.append("daemon-reload")
    await _run_command(*reload_cmd)