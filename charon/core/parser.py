"""
charon/core/parser.py
System Version: v0.2.0 | File Revision: 2.4.0

Module: Pass 1 (Triage Routing) and Pass 2 (Schema Extraction) intent parser
with Tiered Fallback Recovery, Manifest-Driven Routing, and Dynamic Skill Bus Interception.
Refactored to completely remove hardcoded skill strings and enforce Database/Librarian
as the sole source of truth for actions and fallback roles.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import ollama
from pydantic import BaseModel, ValidationError, create_model

from charon.core.prompts import CHARON_ROUTING_PROMPT, EXTRACTION_SYSTEM_PROMPT
from charon.core.utils import clean_json_string, get_schema_json
from charon.core.skills import SkillLibrarian
from charon.intent.routing import RoutingPayload
from charon.intent.manifests import get_triage_agent_descriptions, get_agent_manifest
from charon.utils.memory import ConversationBuffer

logger = logging.getLogger("Charon.Parser")


def _extract_ollama_response_text(response: Any) -> str:
    """Extract raw response string from either dict or Pydantic response objects."""
    if isinstance(response, dict):
        return response.get("response", "{}")
    return getattr(response, "response", "{}")


class IntentParser:
    """Handles LLM-driven classification (routing) and payload parameter extraction with tiered fallback guarantees."""

    def __init__(
        self,
        ollama_client: ollama.AsyncClient,
        triage_model: str,
        heavy_model: str,
        memory: ConversationBuffer,
        librarian: Optional[SkillLibrarian] = None,
    ):
        self.ollama_client = ollama_client
        self.triage_model = triage_model
        self.heavy_model = heavy_model
        self.memory = memory
        self.librarian = librarian or SkillLibrarian.get_instance()

    def _get_fallback_agent(self, action_name: Optional[str] = None) -> str:
        """Dynamically resolves a fallback agent via librarian/database roles without hardcoded skill checks."""
        try:
            # If an explicit action was requested, attempt dynamic database resolution for that skill
            if action_name and hasattr(self.librarian, "resolve_agent_id_for_action"):
                resolved_action_agent = self.librarian.resolve_agent_id_for_action(action_name)
                if resolved_action_agent:
                    return resolved_action_agent

            # Attempt primary database fallback roles
            resolved_planner = self.librarian.resolve_agent_id_for_role("default_system_planner")
            if resolved_planner:
                return resolved_planner

            resolved_fallback = self.librarian.resolve_agent_id_for_role("system_fallback")
            if resolved_fallback:
                return resolved_fallback
        except Exception as e:
            logger.debug(f"Failed to fetch dynamic fallback role via Librarian: {e}")

        fatal_msg = (
            "CRITICAL ROUTING FAILURE: Could not resolve mandatory fallback system roles "
            "('system_fallback' or 'default_system_planner') from the database."
        )
        logger.critical(fatal_msg)
        raise RuntimeError(fatal_msg)

    def _get_active_agents_list(self) -> List[str]:
        """Retrieves a list of all active agent IDs via the SkillLibrarian."""
        try:
            if hasattr(self.librarian, "get_active_agent_ids"):
                return self.librarian.get_active_agent_ids()
        except Exception as e:
            logger.error(f"Failed to fetch active agents list from Librarian: {e}")
        return []

    def _get_schema_for_agent(self, agent_id: str) -> type[BaseModel]:
        """Dynamically retrieves or constructs the extraction payload schema for an agent."""
        try:
            if hasattr(self.librarian, "get_agent_schema") and callable(self.librarian.get_agent_schema):
                schema = self.librarian.get_agent_schema(agent_id)
                if schema:
                    return schema
        except Exception as e:
            logger.debug(f"Could not retrieve dynamic schema for {agent_id} from Librarian: {e}")

        # Defensive fallback schema construction
        return create_model(
            f"{agent_id}Payload",
            action=(str, ...),
            prompt=(str, ...),
            query=(Optional[str], None),
            objective=(Optional[str], None),
            problem=(Optional[str], None),
            target_device=(Optional[str], None),
            __base__=BaseModel
        )

    async def parse_routing(
        self,
        user_input: str,
        rejected_agents: Optional[List[str]] = None,
    ) -> Optional[RoutingPayload]:
        """Pass 1: Dynamic Skill interception, falling back to manifest-grounded classification."""

        # --- PHASE 1: DYNAMIC SKILL BUS FAST-PATH ---
        try:
            matched_skill = self.librarian.find_matching_action(user_input)

            if matched_skill:
                if isinstance(matched_skill, dict):
                    target_agent = matched_skill.get("primary_agent_id") or matched_skill.get("agent_id")
                    skill_name = matched_skill.get("action_name") or matched_skill.get("name")
                else:
                    target_agent = getattr(matched_skill, "primary_agent_id", None) or getattr(matched_skill, "agent_id", None)
                    skill_name = getattr(matched_skill, "action_name", None) or getattr(matched_skill, "name", None)

                if not target_agent:
                    target_agent = self._get_fallback_agent(action_name=skill_name)

                logger.info(f"Skill Bus Intercept: Fast-path routed '{skill_name}' to {target_agent}")
                return RoutingPayload(agent=target_agent)

        except RuntimeError:
            raise  # Bubble up hard runtime errors from missing DB roles
        except Exception as e:
            logger.warning(f"SkillLibrarian fast-path check failed: {e}. Falling back to standard LLM triage.")
        # --------------------------------------------

        # --- STANDARD CONVERSATIONAL/STATIC TRIAGE ---
        active_agents_list = self._get_active_agents_list()
        valid_agents = ", ".join([f'"{a}"' for a in active_agents_list])
        manifest_descriptions = get_triage_agent_descriptions()

        rejection_prompt = ""
        if rejected_agents:
            rejection_prompt = (
                f"\nCRITICAL CONSTRAINT: The following agents have REJECTED this task: "
                f"{', '.join(rejected_agents)}. DO NOT select them again.\n"
            )

        recent_history = self.memory.get_context_string() if hasattr(self.memory, "get_context_string") else ""
        history_context = (
            f"Recent Conversational Context:\n{recent_history}\n\n"
            if recent_history
            else ""
        )

        prompt = (
            f"You are the intent triage classifier for Charon. Examine the user query and select the best agent based on their capabilities:\n\n"
            f"### Available Agents & Manifests:\n{manifest_descriptions}\n\n"
            f"ROUTING RULES:\n"
            f"1. Select your planning/orchestration agent for multi-step sequences, unknown task paths, or file/document discovery.\n"
            f"2. Select your hardware specialist agent for hardware datasheets, electronics components, microcontrollers, or pinouts.\n"
            f"3. Select your baseline agent ONLY for simple, direct OS commands. DO NOT route desktop application launches or file viewing here.\n"
            f"4. For single-action domain requests, select the exact specialist matching the capabilities above.\n"
            f"5. Respond with a simple JSON object containing ONLY the 'agent' key.\n"
            f"Example format: {{\"agent\": \"{active_agents_list[0] if active_agents_list else 'Agent_Name'}\"}}\n\n"
            f"Allowed agent values: {valid_agents}\n{rejection_prompt}\n"
            f"{history_context}"
            f"User Command: {user_input}\n"
            f"JSON Output:"
        )

        try:
            response = await self.ollama_client.generate(
                model=self.triage_model,
                system=CHARON_ROUTING_PROMPT,
                prompt=prompt,
                format="json",
            )
            raw_response = _extract_ollama_response_text(response)
            clean_json = clean_json_string(raw_response)

            # Tier 1: Direct Pydantic Validation
            try:
                payload = RoutingPayload.model_validate_json(clean_json)
                logger.info(f"Triage routed task to: {payload.agent}")
                return payload
            except Exception as direct_err:
                logger.debug(f"Direct routing validation failed: {direct_err}. Attempting key alias extraction.")

            # Tier 2: Key Alias Unwrapping
            parsed_dict = json.loads(clean_json)
            agent_candidate = None
            for key in ("agent", "primary_agent", "target_agent", "selected_agent", "destination"):
                if key in parsed_dict and parsed_dict[key]:
                    agent_candidate = parsed_dict[key]
                    break

            if agent_candidate:
                logger.info(f"Triage recovered alias routing to: {agent_candidate}")
                return RoutingPayload(agent=agent_candidate)

            raise ValueError("No recognizable agent key found in triage payload.")

        except Exception as e:
            fallback_agent = self._get_fallback_agent()
            logger.error(f"Failed to parse routing intent: {e}. Defaulting to {fallback_agent}.")
            return RoutingPayload(agent=fallback_agent)

    async def parse_extraction(
        self,
        user_input: str,
        agent: str,
        ledger_context: str = "",
    ) -> BaseModel:
        """Pass 2: Extract parameters using agent-specific Pydantic intent with 3-tier recovery guarantees."""
        schema_class = self._get_schema_for_agent(agent)

        recent_history = self.memory.get_context_string() if hasattr(self.memory, "get_context_string") else ""
        schema_dump = json.dumps(get_schema_json(schema_class), indent=2)

        prompt = (
            f"System Ledger Context:\n{ledger_context}\n\n"
            f"Recent Conversational Context:\n{recent_history}\n\n"
            f"You must respond with a JSON object matching this schema:\n{schema_dump}\n\n"
            f"User Command: {user_input}\n"
            f"JSON Output:"
        )

        try:
            response = await self.ollama_client.generate(
                model=self.heavy_model,
                system=EXTRACTION_SYSTEM_PROMPT,
                prompt=prompt,
                format="json",
            )
            raw_response = _extract_ollama_response_text(response)
            clean_json = clean_json_string(raw_response)

            extraction = None

            # Tier 1: Direct JSON model validation
            try:
                extraction = schema_class.model_validate_json(clean_json)
            except Exception as t1_err:
                logger.debug(f"Tier 1 extraction validation failed for {agent}: {t1_err}")

            # Tier 2: Nested wrapper dict unwrapping & dictionary validation
            if extraction is None:
                try:
                    parsed_dict = json.loads(clean_json)
                    for wrapper_key in ("parameters", "payload", "result", "extracted_payload", "data"):
                        if wrapper_key in parsed_dict and isinstance(parsed_dict[wrapper_key], dict):
                            parsed_dict = parsed_dict[wrapper_key]
                            break

                    extraction = schema_class.model_validate(parsed_dict)
                    logger.info(f"Tier 2 recovery successfully unwrapped payload for {agent}")
                except Exception as t2_err:
                    logger.debug(f"Tier 2 dictionary validation failed for {agent}: {t2_err}")

            # Tier 3: Defensive Fallback
            if extraction is None:
                logger.warning(f"Pass 2 extraction failed for {agent}. Triggering defensive payload fallback.")
                extraction = self._build_fallback_payload(schema_class, agent, user_input)

            # Stage 2 Prompt Enrichment
            if hasattr(extraction, "prompt") or hasattr(extraction, "objective") or hasattr(extraction, "problem"):
                current_prompt = (
                    getattr(extraction, "prompt", None)
                    or getattr(extraction, "objective", None)
                    or getattr(extraction, "problem", None)
                    or user_input
                )
                if "Ledger records retrieved:" in ledger_context:
                    enriched = (
                        f"PRIMARY USER COMMAND (STRICT TARGET PATH MUST BE PRESERVED): {current_prompt}\n\n"
                        f"[SYSTEM LEDGER RULES & COMPLIANCE REQUIREMENTS]:\n"
                        f"Note: Use the rules below ONLY to identify required files, subdirectories, or standards. "
                        f"NEVER modify, truncate, or overwrite the target directory path specified in the PRIMARY USER COMMAND.\n"
                        f"{ledger_context}"
                    )
                    for attr in ("prompt", "objective", "problem"):
                        if hasattr(extraction, attr) and getattr(extraction, attr, None) is not None:
                            setattr(extraction, attr, enriched)

            return extraction

        except Exception as e:
            logger.warning(f"Unexpected exception during extraction for {agent}: {e}. Falling back.")
            return self._build_fallback_payload(schema_class, agent, user_input)

    def _build_fallback_payload(
        self,
        schema_class: type,
        agent_id: str,
        user_input: str,
    ) -> BaseModel:
        """Constructs a resilient default payload fetching the default action dynamically from the DB."""
        manifest = get_agent_manifest(agent_id)

        # 1. Check agent manifest default action
        default_action = manifest.default_action if manifest else None

        # 2. Query SkillLibrarian for default action registered in DB
        if not default_action and hasattr(self.librarian, "get_default_action_for_agent"):
            default_action = self.librarian.get_default_action_for_agent(agent_id)

        # 3. Query SkillLibrarian for any primary registered action in DB
        if not default_action and hasattr(self.librarian, "get_primary_action_for_agent"):
            default_action = self.librarian.get_primary_action_for_agent(agent_id)

        # Fail fast if DB contains no action mapping for this agent
        if not default_action:
            fatal_msg = (
                f"DATABASE INTEGRITY ERROR: Agent '{agent_id}' has no registered default action "
                f"or skills in the database. Cannot assemble fallback payload."
            )
            logger.critical(fatal_msg)
            raise RuntimeError(fatal_msg)

        fallback_data: Dict[str, Any] = {
            "action": default_action,
            "prompt": user_input,
            "query": user_input,
            "command": user_input,
            "problem": user_input,
            "objective": user_input,
            "expression": user_input,
            "target_device": user_input,
            "fact": user_input,
        }

        try:
            return schema_class.model_validate(fallback_data)
        except ValidationError:
            pass

        try:
            return schema_class.model_construct(**fallback_data)
        except Exception as err:
            logger.error(f"Critical schema construct failure for {agent_id}: {err}")
            return schema_class.model_construct(action=default_action, prompt=user_input)