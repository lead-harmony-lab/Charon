"""
charon/cli/librarian/validators/cbac.py
System Version: v0.2.1 | File Revision: 1.1.0

Module: JSON schema validator for Capability-Based Access Control (CBAC) WorkContracts.
Handles validation of JSON payloads and files against system governance constraints.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import jsonschema

CBAC_CONTRACT_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "CBACWorkContract",
    "description": "Governance schema for Layer 5 CBAC WorkContract policy specifications.",
    "type": "object",
    "required": [
        "contract_id",
        "contract_name",
        "agent_id",
        "skill_id",
    ],
    "properties": {
        "contract_id": {
            "type": "string",
            "pattern": "^[a-zA-Z0-9_-]{3,64}$",
            "description": "Unique identifier slug for the policy contract.",
        },
        "contract_name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128,
            "description": "Human-readable label for the governance policy.",
        },
        "agent_id": {
            "type": "string",
            "pattern": "^[a-zA-Z0-9_*-]{1,64}$",
            "description": "Bound agent ID or wildcard ('*') for fleet-wide policy.",
        },
        "skill_id": {
            "type": "string",
            "pattern": "^[a-zA-Z0-9_*-]{1,64}$",
            "description": "Bound skill ID or wildcard ('*') for universal application.",
        },
        "scope_limits": {
            "type": "object",
            "properties": {
                "allowed_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Explicit list of allowed action slugs.",
                },
                "allowed_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "FileSystem path patterns accessible by this policy.",
                },
                "max_file_size_mb": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Maximum allowed file read/write size in MB.",
                },
                "network_egress": {
                    "type": "boolean",
                    "description": "Flag controlling external network access capabilities.",
                },
            },
            "additionalProperties": True,
        },
        "rate_limit_rpm": {
            "type": ["integer", "null"],
            "minimum": 0,
            "description": "Maximum allowed execution calls per minute.",
        },
        "token_boundary": {
            "type": ["integer", "null"],
            "minimum": 0,
            "description": "Upper token limit allowed per session or window.",
        },
        "is_active": {
            "type": "boolean",
            "default": True,
            "description": "Activation state of the contract policy.",
        },
    },
    "additionalProperties": False,
}


def validate_cbac_policy(payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validates a dictionary payload against the CBAC WorkContract JSON schema.

    Returns:
        Tuple[bool, List[str]]: (is_valid, list_of_formatted_error_messages)
    """
    validator = jsonschema.Draft7Validator(CBAC_CONTRACT_SCHEMA)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)

    if not errors:
        return True, []

    error_messages = []
    for err in errors:
        path = ".".join(str(p) for p in err.path) if err.path else "root"
        error_messages.append(f"Field '{path}': {err.message}")

    return False, error_messages


def validate_contract_schema(file_path: Union[str, Path]) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Loads and validates a CBAC contract JSON file from disk.

    Returns:
        Tuple[bool, List[str], Dict[str, Any]]: (is_valid, error_list, parsed_data)
    """
    target = Path(file_path)
    if not target.exists():
        return False, [f"File not found: '{target}'"], {}

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON syntax: {e}"], {}
    except Exception as e:
        return False, [f"File read error: {e}"], {}

    if not isinstance(data, dict):
        return False, ["Root JSON value must be an object/dictionary"], {}

    is_valid, errors = validate_cbac_policy(data)
    return is_valid, errors, data


def validate_cbac_contract(contract: Union[Dict[str, Any], str, Path]) -> Tuple[bool, List[str]]:
    """Flexibly validates a CBAC contract from either a dictionary payload or file path.

    Returns:
        Tuple[bool, List[str]]: (is_valid, list_of_formatted_error_messages)
    """
    if isinstance(contract, (str, Path)):
        is_valid, errors, _ = validate_contract_schema(contract)
        return is_valid, errors
    elif isinstance(contract, dict):
        return validate_cbac_policy(contract)
    return False, [f"Invalid contract input type: expected dict, str, or Path, got {type(contract).__name__}"]