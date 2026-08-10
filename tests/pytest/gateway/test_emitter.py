from unittest.mock import AsyncMock, patch

import pytest

from charon.gateway.emitter import EventEmitter
from charon.gateway.models import WSEvent


@pytest.fixture
def emitter() -> EventEmitter:
    """Fixture providing a fresh EventEmitter instance."""
    return EventEmitter()


class TestEventEmitter:
    """Tests for the EventEmitter WebSocket helper utility."""

    def test_init(self, emitter: EventEmitter) -> None:
        """Verify initial default context attributes are None."""
        assert emitter.current_task_id is None
        assert emitter.current_client_id is None

    def test_set_context(self, emitter: EventEmitter) -> None:
        """Verify context updating for active task and client IDs."""
        emitter.set_context(task_id="task-123", client_id="client-456")
        assert emitter.current_task_id == "task-123"
        assert emitter.current_client_id == "client-456"

    @pytest.mark.asyncio
    async def test_emit_targeted_with_client_id(self, emitter: EventEmitter) -> None:
        """Verify event is sent directly to specific client when current_client_id is set."""
        emitter.set_context(task_id="task-100", client_id="client-789")
        event = WSEvent(event_type="status_change", task_id="task-100", data={})

        with patch("charon.gateway.emitter.manager") as mock_manager:
            mock_manager.send_to_client = AsyncMock()
            mock_manager.broadcast = AsyncMock()

            await emitter.emit_targeted(event)

            mock_manager.send_to_client.assert_called_once_with("client-789", event)
            mock_manager.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_targeted_without_client_id(self, emitter: EventEmitter) -> None:
        """Verify event is broadcast to all clients when current_client_id is None."""
        emitter.set_context(task_id="task-100", client_id=None)
        event = WSEvent(event_type="status_change", task_id="task-100", data={})

        with patch("charon.gateway.emitter.manager") as mock_manager:
            mock_manager.send_to_client = AsyncMock()
            mock_manager.broadcast = AsyncMock()

            await emitter.emit_targeted(event)

            mock_manager.broadcast.assert_called_once_with(event)
            mock_manager.send_to_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_stream(self, emitter: EventEmitter) -> None:
        """Verify emitting agent stream/log messages."""
        emitter.set_context(task_id="task-stream", client_id="client-1")

        with patch("charon.gateway.emitter.manager") as mock_manager:
            mock_manager.send_to_client = AsyncMock()

            await emitter.emit_stream("Processing build step 1...")

            mock_manager.send_to_client.assert_called_once()
            client_id, event = mock_manager.send_to_client.call_args[0]
            assert client_id == "client-1"
            assert isinstance(event, WSEvent)
            assert event.event_type == "agent_log"
            assert event.task_id == "task-stream"
            assert event.data == {"message": "Processing build step 1..."}

    @pytest.mark.asyncio
    async def test_emit_completed(self, emitter: EventEmitter) -> None:
        """Verify emitting task completion event."""
        emitter.set_context(task_id="task-complete", client_id="client-2")

        with patch("charon.gateway.emitter.manager") as mock_manager:
            mock_manager.send_to_client = AsyncMock()

            await emitter.emit_completed("Execution completed successfully.")

            mock_manager.send_to_client.assert_called_once()
            _, event = mock_manager.send_to_client.call_args[0]
            assert event.event_type == "task_complete"
            assert event.task_id == "task-complete"
            assert event.data == {"summary": "Execution completed successfully."}

    @pytest.mark.asyncio
    async def test_emit_concierge(self, emitter: EventEmitter) -> None:
        """Verify emitting concierge suggestion payload."""
        emitter.set_context(task_id="task-concierge", client_id="client-3")
        suggestion = {"action": "next_step", "prompt": "Deploy build?"}

        with patch("charon.gateway.emitter.manager") as mock_manager:
            mock_manager.send_to_client = AsyncMock()

            await emitter.emit_concierge(suggestion)

            mock_manager.send_to_client.assert_called_once()
            _, event = mock_manager.send_to_client.call_args[0]
            assert event.event_type == "concierge_suggestion"
            assert event.task_id == "task-concierge"
            assert event.data == suggestion

    @pytest.mark.asyncio
    async def test_emit_gatekeeper(self, emitter: EventEmitter) -> None:
        """Verify emitting gatekeeper intercept requests and generating formatted approval ID."""
        emitter.set_context(task_id="task-gk", client_id="client-4")

        with patch("charon.gateway.emitter.manager") as mock_manager:
            mock_manager.send_to_client = AsyncMock()

            approval_id = await emitter.emit_gatekeeper(
                manifest_message="High-risk system modification",
                action="execute_script",
            )

            # Approval ID format: "appr_" + 6 hex chars = 11 characters
            assert approval_id.startswith("appr_")
            assert len(approval_id) == 11

            mock_manager.send_to_client.assert_called_once()
            _, event = mock_manager.send_to_client.call_args[0]
            assert event.event_type == "gatekeeper_intercept"
            assert event.task_id == "task-gk"
            assert event.data == {
                "manifest": "High-risk system modification",
                "action": "execute_script",
                "approval_id": approval_id,
            }
