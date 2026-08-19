"""
charon/gateway/routes/skills.py
System Version: v3.0.0

Module: Skill Gap Registry and Human-in-the-Loop Gemini skill forging endpoints.
"""

import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

logger = logging.getLogger("Charon.Gateway.Routes.Skills")

router = APIRouter(prefix="/v1/skills", tags=["Skill Registry & Forge"])


class SkillRegisterRequest(BaseModel):
    """Payload for registering manually verified skill code generated via Gemini Chat."""
    skill_name: str = Field(..., description="Name of the skill class/module (e.g. dynamic_csv_exporter)")
    action_name: str = Field(..., description="Action name handled by skill (e.g. export_csv_report)")
    code: str = Field(..., description="Python source code implementation for the skill")
    description: str = Field(default="", description="Optional description of skill capabilities")


@router.get("/gaps")
async def get_skill_gaps(request: Request):
    """Returns frequency metrics for tracked diagnostic gaps."""
    registry = getattr(request.app.state, "gap_registry", None)
    if not registry:
        return {"status": "success", "metrics": {}}

    metrics = registry.get_gap_metrics() if hasattr(registry, "get_gap_metrics") else {}
    return {
        "status": "success",
        "metrics": metrics,
    }


@router.get("/blueprints")
async def get_pending_blueprints(request: Request):
    """Returns all queued SkillBlueprint artifacts ready for manual review/forging."""
    registry = getattr(request.app.state, "gap_registry", None)
    if not registry or not hasattr(registry, "list_pending_blueprints"):
        return {"status": "success", "count": 0, "blueprints": []}

    blueprints = registry.list_pending_blueprints()
    dumped = []
    for bp in blueprints:
        if hasattr(bp, "model_dump"):
            dumped.append(bp.model_dump())
        elif hasattr(bp, "dict"):
            dumped.append(bp.dict())
        elif isinstance(bp, dict):
            dumped.append(bp)

    return {
        "status": "success",
        "count": len(dumped),
        "blueprints": dumped,
    }


@router.get("/blueprints/{action_name}/prompt")
async def get_gemini_prompt_for_blueprint(action_name: str, request: Request):
    """
    Formats a SkillBlueprint into a structured Gemini Chat prompt ready to copy-paste.
    Designed for dev environments without direct LLM API keys.
    """
    registry = getattr(request.app.state, "gap_registry", None)
    if not registry or not hasattr(registry, "get_blueprint"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Skill Gap Registry unavailable.",
        )

    blueprint = registry.get_blueprint(action_name)
    if not blueprint:
        raise HTTPException(
            status_code=404,
            detail=f"No pending SkillBlueprint found for action '{action_name}'.",
        )

    consumed = ", ".join(blueprint.consumed_artifacts) if getattr(blueprint, "consumed_artifacts", None) else "None"
    produced = ", ".join(blueprint.produced_artifacts) if getattr(blueprint, "produced_artifacts", None) else "None"
    code_draft = getattr(blueprint, "code_draft", None) or "# No dynamic draft recorded."

    ticks = "```"
    formatted_prompt = (
        "You are an expert Python engineer crafting a dynamic skill for the Charon AI Agent Ecosystem.\n\n"
        f"### Target Action Name:\n`{blueprint.action_name}`\n\n"
        "### Skill Blueprint Specifications:\n"
        f"* **Suggested Skill Class Name:** `{getattr(blueprint, 'suggested_skill_name', 'DynamicSkill')}`\n"
        f"* **Description:** {getattr(blueprint, 'description', '')}\n"
        f"* **Consumed Context Inputs:** {consumed}\n"
        f"* **Produced Output Artifacts:** {produced}\n"
        f"* **Sample Dynamic Call:** `{getattr(blueprint, 'sample_call', '')}`\n\n"
        "### Initial Working Code Prototype:\n"
        f"{ticks}python\n{code_draft}\n{ticks}\n\n"
        "### Implementation Requirements:\n"
        "1. Write a clean, complete, and production-ready Python skill module.\n"
        "2. Provide standard input/output validation.\n"
        "3. Ensure it runs statelessly and handles execution exceptions gracefully.\n"
        "4. Return ONLY valid Python code enclosed in a ```python markdown code block."
    )

    return {
        "status": "success",
        "action_name": action_name,
        "copy_paste_prompt": formatted_prompt,
    }


@router.delete("/gaps/{action_name}")
async def reset_skill_gap(action_name: str, request: Request):
    """Resets the failure counter and removes pending blueprint for an action."""
    registry = getattr(request.app.state, "gap_registry", None)
    if registry and hasattr(registry, "reset_gap_counter"):
        registry.reset_gap_counter(action_name)
    return {
        "status": "success",
        "message": f"Gap counter and pending blueprint reset for action '{action_name}'.",
    }


@router.post("/register")
async def register_manual_skill(skill_req: SkillRegisterRequest, request: Request):
    """
    Accepts Python code generated via Gemini Chat, saves it to disk in charon/skills/dynamic/,
    triggers a live scan in SkillLibrarian, and resets the gap counter in SkillGapRegistry.
    """
    registry = getattr(request.app.state, "gap_registry", None)
    if registry and hasattr(registry, "reset_gap_counter"):
        registry.reset_gap_counter(skill_req.action_name)

    skills_dir = Path("charon/skills/dynamic")
    skills_dir.mkdir(parents=True, exist_ok=True)

    file_path = skills_dir / f"{skill_req.skill_name.lower()}.py"
    file_path.write_text(skill_req.code, encoding="utf-8")

    engine = getattr(request.app.state, "engine", None)
    if engine and hasattr(engine, "librarian") and engine.librarian:
        try:
            if hasattr(engine.librarian, "scan_and_register_dynamic_skills"):
                engine.librarian.scan_and_register_dynamic_skills()
        except Exception as err:
            logger.warning(f"Live librarian reload notification skipped: {err}")

    logger.info(f"[Gateway] Skill '{skill_req.skill_name}' successfully ingested into {file_path}.")
    return {
        "status": "success",
        "action_name": skill_req.action_name,
        "skill_name": skill_req.skill_name,
        "saved_path": str(file_path),
        "message": f"Skill '{skill_req.skill_name}' successfully ingested, written to {file_path}, and registered.",
    }