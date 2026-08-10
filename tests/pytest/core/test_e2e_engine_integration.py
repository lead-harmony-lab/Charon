"""
test_e2e_engine_integration.py — Integration test for OrchestrationEngine.
Validates end-to-end multi-step DAG execution, variable substitution ($STEP_X_OUTPUT),
and self-healing diagnostic recovery across chained agent executions.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from charon.core.engine import OrchestrationEngine
from charon.intent import AgentEnum, RoutingPayload


@pytest.mark.asyncio
async def test_full_dag_execution_with_self_healing_recovery():
    """Simulates a multi-step DAG plan where Step 1 fails, triggers self-healing,
    and Step 2 consumes the repaired context via variable substitution.
    """
    mock_orchestrator = MagicMock()

    # Step 1: Force routing to Planner to trigger plan decomposition
    mock_orchestrator.parse_routing = AsyncMock(
        return_value=RoutingPayload(
            agent=AgentEnum.PLANNER,
            confidence=0.98,
            needs_decomposition=True,
        )
    )
    mock_orchestrator.get_acknowledgment = MagicMock(return_value="Initiating tactical sequence...")
    mock_orchestrator.record_turn = MagicMock()

    # Mock Planner responses
    mock_planner = MagicMock()
    dag_plan = [
        {
            "step": 1,
            "agent": "The_Cleaner",
            "action": "list_projects",
            "parameters": {"base_path": "/tmp/invalid_workspace"},
        },
        {
            "step": 2,
            "agent": "The_Generalist",
            "action": "synthesize",
            "parameters": {"context": "$STEP_1_OUTPUT"},
        },
    ]

    async def planner_execute_mock(action, parameters, **kwargs):
        if action == "decompose_task":
            return dag_plan
        elif action == "diagnose":
            return "Diagnosis: Target workspace missing. Recommendation: Automatically created /tmp/invalid_workspace."
        return "Planner Execution OK"

    mock_planner.execute = AsyncMock(side_effect=planner_execute_mock)

    # Mock Cleaner agent (Step 1 fails)
    mock_cleaner = MagicMock()
    mock_cleaner.execute = AsyncMock(
        return_value="[Runtime Error]: Directory /tmp/invalid_workspace does not exist."
    )

    # Mock Generalist agent (Step 2 receives recovered Step 1 context)
    mock_generalist = MagicMock()
    mock_generalist.execute = AsyncMock(
        side_effect=lambda action, parameters, **kwargs: f"Synthesized Report based on: {parameters.get('context')}"
    )

    # Mock Dispatcher resolution
    mock_dispatcher = MagicMock()
    mock_dispatcher.planner = mock_planner

    def resolve_agent(name):
        if name == "The_Cleaner":
            return mock_cleaner
        if name == "The_Generalist":
            return mock_generalist
        return mock_planner

    mock_dispatcher._resolve_agent.side_effect = resolve_agent
    mock_orchestrator.dispatcher = mock_dispatcher

    # Initialize engine and execute request
    engine = OrchestrationEngine(orchestrator=mock_orchestrator)
    request_prompt = "Audit workspace directories and generate status report"

    result = await engine.process_request(request_prompt)

    # --- Assertions ---
    # 1. Step 1 hit error and self-healing intercept attached diagnosis
    assert "Step 1 Output (The_Cleaner)" in result
    assert "[Self-Healing Recovery Intercept]:" in result
    assert "Diagnosis: Target workspace missing" in result

    # 2. Step 2 received the enriched error + recovery output from Step 1 via $STEP_1_OUTPUT
    assert "Step 2 Output (The_Generalist)" in result
    assert "Synthesized Report based on:" in result
    assert "[Self-Healing Recovery Intercept]" in result

    # 3. Verify conversation history recorded the turn
    mock_orchestrator.record_turn.assert_called_once()
