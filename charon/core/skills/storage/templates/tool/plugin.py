"""
charon/core/skills/storage/staged/core.<domain>.<skill_name>/plugin.py
System Version: v0.2.1 | File Revision: 1.0.0

V2 Peripheral Tool Skill Plugin Template for Charon Capabilities.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("Charon.Skills.<SkillName>")


def sample_tool_action(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes primary tool logic within the workspace sandbox context.
    """
    target_path = params.get("target_path", "")
    cwd = params.get("cwd", ".")

    if not target_path:
        return {
            "is_success": False,
            "output": "Execution error: Missing required parameter 'target_path'.",
        }

    os.makedirs(cwd, exist_ok=True)
    temp_file_ref: Optional[str] = None

    try:
        # Perform work within specified target directory
        resolved_file = Path(cwd) / target_path
        temp_file_ref = str(resolved_file)

        # Example operation write/mutation
        resolved_file.write_text("Initialization artifact", encoding="utf-8")

        return {
            "is_success": True,
            "output": f"Successfully initialized artifact at '{resolved_file}'.",
            "artifact_path": str(resolved_file),
        }

    except Exception as e:
        logger.error(f"[<SkillName>] Action execution failed: {e}")
        return {
            "is_success": False,
            "output": f"Tool action failed with error: {str(e)}",
        }
    finally:
        # Guarded cleanup logic for transient variables
        if temp_file_ref and "transient" in temp_file_ref and os.path.exists(temp_file_ref):
            try:
                os.remove(temp_file_ref)
            except OSError:
                pass


def execute_action(
    action_name: str,
    parameters: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    agent_name: str = "",
    raw_prompt: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Standard V2 dispatch router.

    Accepts variadic kwargs and parameter aliases to guarantee compatibility 
    with BaseAgent.execute_sub_skill calls.
    """
    # Parameter normalization chokepoint
    resolved_params = parameters if parameters is not None else (params or {})

    if action_name == "sample_tool_action":
        return sample_tool_action(resolved_params)

    raise ValueError(
        f"Action '{action_name}' is not supported by skill 'core.<domain>.<skill_name>'."
    )