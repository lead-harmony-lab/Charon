"""
charon/core/agent_runner.py
System Version: v0.3.4 | File Revision: 1.1.0

Module: Generic, Stateless Agent Execution Harness.
Instantiates agent personas dynamically via role abstraction, hydra-loads tool specs
from the SkillLibrarian, and executes plugin.py tool calls adhering strictly to the
Janitorial Working Anchor.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from charon.config.settings import DEFAULT_HEAVY_MODEL
from charon.core.skills.librarian import SkillLibrarian

logger = logging.getLogger("Charon.Core.AgentRunner")


class AgentExecutionError(RuntimeError):
    """Raised when an agent execution step or tool checkout encounters an unrecoverable fault."""
    pass


class AgentRunner:
    """
    Stateless execution engine for dynamic agents.
    Accepts a System Role name, resolves persona/tools via SkillLibrarian,
    and executes LLM tool loops without hardcoded identities or prompts.
    """

    def __init__(
        self,
        role_name: str = "system_generalist",
        librarian: Optional[SkillLibrarian] = None,
        max_tool_turns: int = 5,
    ) -> None:
        self.role_name: str = role_name
        self.librarian: SkillLibrarian = librarian or SkillLibrarian.get_instance()
        self.max_tool_turns: int = max_tool_turns

        # 1. Resolve agent_id dynamically via role abstraction
        self.agent_id: str = self.librarian.resolve_role(self.role_name)

        # 2. Fetch presentation display name for decoupled logging
        self.display_name: str = self.librarian.get_display_name_for_role(self.role_name)

        logger.info(
            f"[AGENT_RUNNER] Initialized runner for role '{self.role_name}' "
            f"(Resolved ID: '{self.agent_id}' | Display: '{self.display_name}')"
        )

    @property
    def system_prompt(self) -> str:
        """Database-Driven Prompting: Pulls system prompt dynamically strictly from SQLite."""
        prompt = self.librarian.get_system_prompt_for_role(self.role_name)
        if not prompt:
            logger.warning(
                f"[AGENT_RUNNER] No system prompt found in DB for role '{self.role_name}'."
            )
        return prompt

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Hydrates OpenAI/Ollama tool JSON specifications mapped to this agent in DB."""
        return self.librarian.get_agent_tool_schemas(self.agent_id)

    def execute_task(
        self,
        task_prompt: str,
        llm_client: Any,
        model_name: Optional[str] = None,
        blackboard_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes an agent task cycle:
        1. Formulates LLM context (System Prompt + Blackboard Context + Tools)
        2. Dispatches prompt to LLM
        3. Intercepts tool calls and executes matching plugin.py handlers
        4. Returns final response and telemetry settlement
        """
        active_model = model_name or DEFAULT_HEAVY_MODEL
        context = blackboard_context or {}
        tools = self.get_tool_schemas()
        sys_prompt = self.system_prompt

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": sys_prompt},
            {
                "role": "user",
                "content": f"Context: {json.dumps(context)}\n\nTask: {task_prompt}",
            },
        ]

        logger.info(
            f"[{self.display_name}] Executing task on model '{active_model}' with {len(tools)} loaded tools..."
        )

        turn_count = 0
        while turn_count < self.max_tool_turns:
            turn_count += 1

            # Dispatch turn to LLM Client (Expected interface: Ollama or OpenAI compatible client)
            try:
                response = llm_client.chat(
                    model=active_model,
                    messages=messages,
                    tools=tools if tools else None,
                )
            except Exception as e:
                logger.error(f"[{self.display_name}] LLM invocation failed: {e}")
                raise AgentExecutionError(f"LLM communication error: {e}")

            message = response.get("message", {})
            tool_calls = message.get("tool_calls", [])

            # Case A: LLM produced a final text answer (No tool calls)
            if not tool_calls:
                final_content = message.get("content", "")
                logger.info(f"[{self.display_name}] Task completed successfully.")
                return {
                    "status": "success",
                    "role_name": self.role_name,
                    "agent_id": self.agent_id,
                    "display_name": self.display_name,
                    "model_used": active_model,
                    "output": final_content,
                    "turns_taken": turn_count,
                }

            # Case B: LLM issued function tool calls
            messages.append(message)  # Append assistant tool intent turn

            for tool_call in tool_calls:
                function_info = tool_call.get("function", {})
                action_name = function_info.get("name")
                raw_args = function_info.get("arguments", {})

                params = (
                    json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                )

                logger.info(
                    f"[{self.display_name}] Intercepted tool call: '{action_name}'"
                )

                # Execute action via Skill Checkout
                tool_result = self._dispatch_skill_action(action_name, params)

                # Feed tool result back into message stream for LLM
                messages.append({
                    "role": "tool",
                    "name": action_name,
                    "content": json.dumps(tool_result),
                })

        raise AgentExecutionError(
            f"[{self.display_name}] Exceeded max tool execution turns ({self.max_tool_turns})."
        )

    def _dispatch_skill_action(
        self, action_name: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validates checkout permissions and invokes plugin.execute_action()."""
        handler = self.librarian.check_out_skill(action_name, self.agent_id)

        if not handler:
            error_msg = (
                f"Checkout failed: Role '{self.role_name}' ({self.agent_id}) "
                f"is not authorized or missing plugin file for action '{action_name}'."
            )
            logger.error(f"[{self.display_name}] {error_msg}")
            return {"status": "error", "message": error_msg}

        try:
            # Invoke plugin entrypoint
            if callable(handler):
                result = handler(self.agent_id, params)
            elif hasattr(handler, "execute"):
                result = handler.execute(params)
            else:
                raise TypeError(f"Skill handler for '{action_name}' is not callable.")

            return result if isinstance(result, dict) else {"status": "success", "result": result}

        except Exception as e:
            logger.error(
                f"[{self.display_name}] Execution exception in plugin action '{action_name}': {e}"
            )
            return {"status": "error", "message": str(e)}