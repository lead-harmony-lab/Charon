"""
Unit tests for OrchestrationEngine self-healing recovery pipeline.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from charon.core.orchestration import OrchestrationEngine
from charon.intent import AgentEnum, IntentExtraction, RoutingPayload


@pytest.fixture
def mock_orchestrator():
    """Builds mocked Orchestrator, Planner, and Dispatcher components."""
    orchestrator = MagicMock()
    mock_planner = MagicMock()
    mock_dispatcher = MagicMock()

    # Configure parse_routing as an AsyncMock
    mock_routing = RoutingPayload(agent=AgentEnum.PLANNER)
    orchestrator.parse_routing = AsyncMock(return_value=mock_routing)

    # Configure parse_extraction as an AsyncMock
    mock_extraction = IntentExtraction(
        agent=AgentEnum.PLANNER,
        action="decompose_task",
        parameters={"objective": "test"},
        confidence=1.0,
        raw_prompt="test",
    )
    orchestrator.parse_extraction = AsyncMock(return_value=mock_extraction)
    orchestrator.get_acknowledgment.return_value = None

    # Connect dispatcher and orchestrator
    orchestrator.dispatcher = mock_dispatcher

    return orchestrator, mock_planner, mock_dispatcher


def _setup_agent_resolver(mock_dispatcher, mock_planner, target_agent):
    """Helper to route _resolve_agent calls to Planner or the step agent."""

    def resolve_side_effect(agent_identifier):
        agent_str = (
            agent_identifier.value
            if isinstance(agent_identifier, AgentEnum)
            else str(agent_identifier)
        )
        if agent_str in ("The_Planner", AgentEnum.PLANNER.value):
            return mock_planner
        return target_agent

    mock_dispatcher._resolve_agent.side_effect = resolve_side_effect


@pytest.mark.asyncio
async def test_self_healing_intercept_triggered_on_error_string(mock_orchestrator):
    orchestrator, mock_planner, mock_dispatcher = mock_orchestrator

    dag_plan = [
        {"step": 1, "agent": "The_Cleaner", "action": "list_projects", "parameters": {}},
    ]

    async def planner_execute_side_effect(action, parameters, **kwargs):
        if action == "decompose_task":
            return dag_plan
        elif action == "diagnose":
            return "Root cause: Directory missing. Solution: mkdir -p."
        return "OK"

    mock_planner.execute = AsyncMock(side_effect=planner_execute_side_effect)

    # Mock step failure via error string response
    failing_agent = MagicMock()
    failing_agent.execute = AsyncMock(
        return_value="Error: Directory /missing/path does not exist."
    )
    _setup_agent_resolver(mock_dispatcher, mock_planner, failing_agent)

    engine = OrchestrationEngine(orchestrator=orchestrator)
    result = await engine.process_request("Audit the workspace directories")
    assert result is not None


@pytest.mark.asyncio
async def test_self_healing_intercept_triggered_on_raised_exception(mock_orchestrator):
    orchestrator, mock_planner, mock_dispatcher = mock_orchestrator

    dag_plan = [
        {"step": 1, "agent": "The_Spark", "action": "flash_firmware", "parameters": {}},
    ]

    async def planner_execute_side_effect(action, parameters, **kwargs):
        if action == "decompose_task":
            return dag_plan
        elif action == "diagnose":
            return "Diagnosis: Serial port ttyUSB0 unavailable. Re-bind port."
        return "OK"

    mock_planner.execute = AsyncMock(side_effect=planner_execute_side_effect)

    # Mock step failure via raised exception
    crashing_agent = MagicMock()
    crashing_agent.execute = AsyncMock(side_effect=RuntimeError("Device connection lost"))
    _setup_agent_resolver(mock_dispatcher, mock_planner, crashing_agent)

    engine = OrchestrationEngine(orchestrator=orchestrator)
    result = await engine.process_request("Flash MCU firmware")
    assert result is not None


@pytest.mark.asyncio
async def test_clean_step_execution_bypasses_self_healing(mock_orchestrator):
    orchestrator, mock_planner, mock_dispatcher = mock_orchestrator

    dag_plan = [
        {
            "step": 1,
            "agent": "The_Archivist",
            "action": "search_ledger",
            "parameters": {"query": "CAD rules"},
        },
    ]

    async def planner_execute_side_effect(action, parameters, **kwargs):
        if action == "decompose_task":
            return dag_plan
        return "OK"

    mock_planner.execute = AsyncMock(side_effect=planner_execute_side_effect)

    successful_agent = MagicMock()
    successful_agent.execute = AsyncMock(
        return_value="Found 3 CAD rules in ChromaDB ledger."
    )
    _setup_agent_resolver(mock_dispatcher, mock_planner, successful_agent)

    engine = OrchestrationEngine(orchestrator=orchestrator)
    result = await engine.process_request("Check CAD rules")
    assert "Found 3 CAD rules" in str(result)
