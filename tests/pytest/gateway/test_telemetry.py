import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from charon.gateway.models import WSEvent
from charon.gateway.telemetry import TelemetryReporter


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_callbacks():
    """Provides mock providers for queue depth, status, and task ID."""
    return {
        "queue_provider": MagicMock(return_value=42),
        "gatekeeper_status_provider": MagicMock(return_value=False),
        "task_provider": MagicMock(return_value="task-999"),
    }


@pytest.fixture
def reporter(mock_callbacks):
    """Initializes TelemetryReporter with mocked dependencies."""
    with patch("charon.gateway.telemetry.ollama.AsyncClient"):
        reporter = TelemetryReporter(
            queue_provider=mock_callbacks["queue_provider"],
            gatekeeper_status_provider=mock_callbacks["gatekeeper_status_provider"],
            task_provider=mock_callbacks["task_provider"],
        )
        yield reporter


# ============================================================================
# Unit Tests: verify_engine
# ============================================================================

@pytest.mark.asyncio
async def test_verify_engine_success(reporter):
    """Verify engine returns True on successful ping."""
    reporter.ollama_client.list = AsyncMock(return_value=[])

    result = await reporter.verify_engine(retries=3, delay=0.01)

    assert result is True
    assert reporter.ollama_client.list.call_count == 1


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_verify_engine_failure_retry(mock_sleep, reporter):
    """Verify engine retries up to max attempts on failure and returns False."""
    reporter.ollama_client.list = AsyncMock(side_effect=Exception("Connection refused"))

    result = await reporter.verify_engine(retries=3, delay=1.0)

    assert result is False
    assert reporter.ollama_client.list.call_count == 3
    assert mock_sleep.call_count == 2  # Sleeps between attempts


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_verify_engine_recovers_on_retry(mock_sleep, reporter):
    """Verify engine returns True if a retry attempt succeeds."""
    reporter.ollama_client.list = AsyncMock(
        side_effect=[Exception("Transient error"), []]
    )

    result = await reporter.verify_engine(retries=3, delay=1.0)

    assert result is True
    assert reporter.ollama_client.list.call_count == 2
    assert mock_sleep.call_count == 1


# ============================================================================
# Unit Tests: start_loop
# ============================================================================

@pytest.mark.asyncio
@patch("charon.gateway.telemetry.manager")
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_start_loop_broadcasts_telemetry(mock_sleep, mock_manager, reporter, mock_callbacks):
    """Verify start_loop collects providers' data and broadcasts a telemetry report."""
    mock_manager.active_connections = [1, 2, 3]
    mock_manager.broadcast = AsyncMock()

    # Run for 1 iteration, then trigger loop exit via CancelledError
    reporter.verify_engine = AsyncMock(side_effect=[True, asyncio.CancelledError()])

    # start_loop catches CancelledError internally and exits gracefully
    await reporter.start_loop(interval=10.0)

    assert mock_manager.broadcast.call_count == 1
    event: WSEvent = mock_manager.broadcast.call_args[0][0]

    assert event.event_type == "overseer_report"
    assert event.task_id == "task-999"
    assert event.data == {
        "engine_online": True,
        "queue_depth": 42,
        "active_clients": 3,
        "awaiting_gatekeeper": False,
        "current_task": "task-999",
    }


@pytest.mark.asyncio
@patch("charon.gateway.telemetry.manager")
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_start_loop_idle_task_fallback(mock_sleep, mock_manager, reporter):
    """Verify telemetry defaults 'current_task' to 'Idle' when task_provider returns None."""
    mock_manager.active_connections = []
    mock_manager.broadcast = AsyncMock()
    reporter.get_current_task = MagicMock(return_value=None)

    reporter.verify_engine = AsyncMock(side_effect=[True, asyncio.CancelledError()])

    await reporter.start_loop(interval=10.0)

    event: WSEvent = mock_manager.broadcast.call_args[0][0]
    assert event.task_id is None
    assert event.data["current_task"] == "Idle"


@pytest.mark.asyncio
@patch("charon.gateway.telemetry.manager")
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_start_loop_engine_disconnected_alert(mock_sleep, mock_manager, reporter):
    """Verify CRITICAL system alert is broadcast when engine state changes from online to offline."""
    mock_manager.active_connections = []
    mock_manager.broadcast = AsyncMock()

    reporter.last_engine_state = True
    reporter.verify_engine = AsyncMock(side_effect=[False, asyncio.CancelledError()])

    await reporter.start_loop(interval=1.0)

    # 1 critical alert + 1 telemetry report
    assert mock_manager.broadcast.call_count == 2

    alert_event: WSEvent = mock_manager.broadcast.call_args_list[0][0][0]
    assert alert_event.event_type == "system_alert"
    assert alert_event.data["severity"] == "CRITICAL"
    assert alert_event.data["title"] == "Engine Disconnected"
    assert reporter.last_engine_state is False


@pytest.mark.asyncio
@patch("charon.gateway.telemetry.manager")
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_start_loop_engine_restored_alert(mock_sleep, mock_manager, reporter):
    """Verify INFO system alert is broadcast when engine state recovers from offline to online."""
    mock_manager.active_connections = []
    mock_manager.broadcast = AsyncMock()

    reporter.last_engine_state = False
    reporter.verify_engine = AsyncMock(side_effect=[True, asyncio.CancelledError()])

    await reporter.start_loop(interval=1.0)

    # 1 restoration alert + 1 telemetry report
    assert mock_manager.broadcast.call_count == 2

    alert_event: WSEvent = mock_manager.broadcast.call_args_list[0][0][0]
    assert alert_event.event_type == "system_alert"
    assert alert_event.data["severity"] == "INFO"
    assert alert_event.data["title"] == "Engine Restored"
    assert reporter.last_engine_state is True


@pytest.mark.asyncio
@patch("charon.gateway.telemetry.manager")
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_start_loop_handles_inner_exception(mock_sleep, mock_manager, reporter):
    """Verify exceptions inside the telemetry loop are caught and logged without crashing the loop."""
    mock_manager.active_connections = []
    # Throw an exception on 1st broadcast, succeed on 2nd
    mock_manager.broadcast = AsyncMock(side_effect=[Exception("WebSocket write failed"), None])

    reporter.verify_engine = AsyncMock(
        side_effect=[True, True, asyncio.CancelledError()]
    )

    await reporter.start_loop(interval=1.0)

    # Broadcast was attempted twice despite the exception in iteration 1
    assert mock_manager.broadcast.call_count == 2
