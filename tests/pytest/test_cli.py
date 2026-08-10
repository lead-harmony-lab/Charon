"""Unit tests for the Charon CLI client (charon/cli.py)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import websockets
import websockets.exceptions

from charon.cli import (
    CharonClient,
    CharonSpinner,
    async_main,
    main,
    render_response,
    teletype_print,
)


# ============================================================================
# 1. Visual Effects & Spinner Tests
# ============================================================================

class TestCharonSpinner:

    def test_spinner_lifecycle(self):
        """Test starting and stopping the terminal spinner thread."""
        spinner = CharonSpinner(message="Testing...")
        assert not spinner.running

        spinner.stop()

        spinner.start("Custom message")
        assert spinner.running
        assert spinner.message == "Custom message"

        spinner.start()
        assert spinner.running

        spinner.stop()
        assert not spinner.running

    def test_spin_loop_runs_and_cleans_up(self):
        """Test spin execution loop output and cleanup."""
        spinner = CharonSpinner(message="Spin Test")
        spinner.running = True

        with patch("sys.stdout.write") as mock_write, patch("time.sleep"):
            def stop_spinner(*args, **kwargs):
                spinner.running = False

            mock_write.side_effect = stop_spinner
            spinner.spin()
            assert mock_write.called


class TestUtilityFunctions:

    def test_teletype_print(self):
        """Test character-by-character teletype rendering."""
        text = "Hi"
        with patch("sys.stdout.write") as mock_write, patch("time.sleep") as mock_sleep:
            teletype_print(text, delay=0.001)
            assert mock_write.call_count == len(text) + 1
            assert mock_sleep.call_count == len(text)

    def test_render_response_plain_text(self):
        """Plain strings without special markdown characters should trigger teletype printing."""
        with patch("charon.cli.teletype_print") as mock_teletype:
            render_response("Simple text response")
            mock_teletype.assert_called_once_with("Simple text response")

    def test_render_response_markdown(self):
        """Structured text with newlines or markdown should render via Rich Markdown."""
        with patch("charon.cli.console.print") as mock_console:
            render_response("Header:\n* Item 1\n* Item 2")
            assert mock_console.call_count == 2


# ============================================================================
# 2. CharonClient REST & WebSocket Tests
# ============================================================================

class TestCharonClient:

    @pytest.fixture
    def client(self):
        return CharonClient(base_url="http://localhost:8000", api_key="test_key")

    def test_headers_and_initialization(self, client):
        assert client.base_url == "http://localhost:8000"
        assert client.ws_url == "ws://localhost:8000/v1/ws"
        assert client.headers == {"X-API-Key": "test_key"}
        assert client.client_id.startswith("cli_")

    @pytest.mark.asyncio
    async def test_ping_daemon_success(self, client):
        """ping_daemon returns True when REST API responds 200 OK."""
        mock_response = MagicMock(status_code=200)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            assert await client.ping_daemon() is True

    @pytest.mark.asyncio
    async def test_ping_daemon_failure(self, client):
        """ping_daemon returns False on HTTP error or exception."""
        mock_response = MagicMock(status_code=500)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            assert await client.ping_daemon() is False

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.RequestError("Down")):
            assert await client.ping_daemon() is False

    @pytest.mark.asyncio
    async def test_submit_and_stream_task_creation_failure(self, client):
        """Task submission returns False when endpoint returns non-200."""
        mock_ws = AsyncMock()
        mock_ws_connect = AsyncMock()
        mock_ws_connect.__aenter__.return_value = mock_ws

        mock_post_resp = MagicMock(status_code=400, text="Bad Prompt")

        with patch("websockets.connect", return_value=mock_ws_connect), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp):
            session = MagicMock()
            result = await client.submit_and_stream("test prompt", session)
            assert result is False

    @pytest.mark.asyncio
    async def test_submit_and_stream_full_event_flow(self, client):
        """Covers full streaming loop execution for primary event handlers."""
        task_id = "task_123"

        events = [
            json.dumps({"event_type": "agent_log", "task_id": "other_task", "data": {"message": "ignore"}}),

            # CLOSES 177->179: First chunk stops the spinner, second chunk runs while spinner is already stopped.
            json.dumps({"event_type": "task_stream", "task_id": task_id, "data": {"message": "Chunk 1"}}),
            json.dumps({"event_type": "task_stream", "task_id": task_id, "data": {"message": "Chunk 2"}}),

            json.dumps({"event_type": "gatekeeper_intercept", "task_id": task_id, "data": {
                "approval_id": "app_99",
                "action": "Delete database",
                "manifest": "DANGER"
            }}),
            json.dumps({"event_type": "system_alert", "task_id": task_id, "data": {"severity": "CRITICAL", "title": "Alert", "message": "High temp"}}),
            json.dumps({"event_type": "task_complete", "task_id": task_id, "data": {"summary": "Completed successfully."}}),
        ]

        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = events
        mock_ws_connect = AsyncMock()
        mock_ws_connect.__aenter__.return_value = mock_ws

        mock_post_resp = MagicMock(status_code=200)
        mock_post_resp.json.return_value = {"task_id": task_id}

        session = AsyncMock()
        session.prompt_async.return_value = "proceed"

        with patch("websockets.connect", return_value=mock_ws_connect), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp):
            result = await client.submit_and_stream("Run maintenance", session)
            assert result is True

    @pytest.mark.asyncio
    async def test_concierge_with_active_spinner_and_no_manifest(self, client):
        """Covers concierge_suggestion when spinner.running == True."""
        task_id = "task_active_spinner"
        events = [
            json.dumps({"event_type": "concierge_suggestion", "task_id": task_id, "data": {"suggestion": "Verify configuration"}}),
            json.dumps({"event_type": "gatekeeper_intercept", "task_id": task_id, "data": {
                "approval_id": "app_100",
                "action": "Format partition",
                "manifest": ""
            }}),
            json.dumps({"event_type": "task_complete", "task_id": task_id, "data": {"summary": ""}}),
        ]
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = events
        mock_ws_connect = AsyncMock()
        mock_ws_connect.__aenter__.return_value = mock_ws
        mock_post_resp = MagicMock(status_code=200)
        mock_post_resp.json.return_value = {"task_id": task_id}
        session = AsyncMock()
        session.prompt_async.return_value = "cancel"

        with patch("websockets.connect", return_value=mock_ws_connect), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp):
            client.spinner.running = True
            result = await client.submit_and_stream("Format drive", session)
            assert result is True

    @pytest.mark.asyncio
    async def test_concierge_with_stopped_spinner(self, client):
        """Triggers concierge_suggestion when spinner is already False."""
        task_id = "task_stopped_spinner"
        events = [
            json.dumps({"event_type": "task_stream", "task_id": task_id, "data": {"message": "Chunk"}}),
            json.dumps({"event_type": "concierge_suggestion", "task_id": task_id, "data": {"recommendation": "do this"}}),
            json.dumps({"event_type": "task_complete", "task_id": task_id, "data": {"summary": "Done"}})
        ]
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = events
        mock_ws_connect = AsyncMock()
        mock_ws_connect.__aenter__.return_value = mock_ws
        mock_post_resp = MagicMock(status_code=200)
        mock_post_resp.json.return_value = {"task_id": task_id}

        with patch("websockets.connect", return_value=mock_ws_connect), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp):
            session = MagicMock()
            await client.submit_and_stream("Test", session)

    @pytest.mark.asyncio
    async def test_unknown_event_fallthrough(self, client):
        """Submits an unknown event type to fall through the if/elif block and loop back."""
        task_id = "task_unknown"
        events = [
            json.dumps({"event_type": "some_unhandled_event", "task_id": task_id, "data": {}}),
            json.dumps({"event_type": "task_complete", "task_id": task_id, "data": {"summary": "Done"}})
        ]
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = events
        mock_ws_connect = AsyncMock()
        mock_ws_connect.__aenter__.return_value = mock_ws
        mock_post_resp = MagicMock(status_code=200)
        mock_post_resp.json.return_value = {"task_id": task_id}

        with patch("websockets.connect", return_value=mock_ws_connect), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp):
            session = MagicMock()
            await client.submit_and_stream("Test", session)

    @pytest.mark.asyncio
    async def test_event_filtering_branches(self, client):
        """Tests event filtering edge cases (missing event_task_id, overseer_report exception)."""
        task_id = "my_task"
        events = [
            json.dumps({"event_type": "agent_log", "data": {"message": "Global log"}}),
            json.dumps({"event_type": "overseer_report", "task_id": "other_task", "data": {}}),
            json.dumps({"event_type": "task_complete", "task_id": task_id, "data": {"summary": "Done"}}),
        ]
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = events
        mock_ws_connect = AsyncMock()
        mock_ws_connect.__aenter__.return_value = mock_ws
        mock_post_resp = MagicMock(status_code=200)
        mock_post_resp.json.return_value = {"task_id": task_id}

        with patch("websockets.connect", return_value=mock_ws_connect), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp):
            session = MagicMock()
            result = await client.submit_and_stream("Test filtering", session)
            assert result is True

    @pytest.mark.asyncio
    async def test_event_filtering_no_local_task_id(self, client):
        """Tests event filtering when local task_id is None."""
        events = [
            json.dumps({"event_type": "agent_log", "task_id": "some_task", "data": {"message": "Log"}}),
            json.dumps({"event_type": "task_complete", "data": {"summary": "Done"}}),
        ]
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = events
        mock_ws_connect = AsyncMock()
        mock_ws_connect.__aenter__.return_value = mock_ws
        mock_post_resp = MagicMock(status_code=200)
        mock_post_resp.json.return_value = {}

        with patch("websockets.connect", return_value=mock_ws_connect), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp):
            session = MagicMock()
            result = await client.submit_and_stream("Test filtering no task_id", session)
            assert result is True

    @pytest.mark.asyncio
    async def test_submit_and_stream_task_error(self, client):
        """Test stream terminating on task_error event."""
        task_id = "task_error_123"
        events = [
            json.dumps({"event_type": "task_error", "task_id": task_id, "data": {"error": "Execution crashed"}})
        ]
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = events
        mock_ws_connect = AsyncMock()
        mock_ws_connect.__aenter__.return_value = mock_ws
        mock_post_resp = MagicMock(status_code=200)
        mock_post_resp.json.return_value = {"task_id": task_id}

        with patch("websockets.connect", return_value=mock_ws_connect), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_post_resp):
            session = MagicMock()
            result = await client.submit_and_stream("Failing action", session)
            assert result is False

    @pytest.mark.asyncio
    async def test_submit_and_stream_exceptions(self, client):
        """Test exception handling during streaming (connection error, websockets disconnect)."""
        session = MagicMock()

        with patch("websockets.connect", side_effect=httpx.RequestError("Host unreachable")):
            assert await client.submit_and_stream("Hello", session) is False

        ws_closed_exc = websockets.exceptions.ConnectionClosedOK(rcvd=None, sent=None)
        with patch("websockets.connect", side_effect=ws_closed_exc):
            assert await client.submit_and_stream("Hello", session) is True

        with patch("websockets.connect", side_effect=RuntimeError("Unexpected")):
            assert await client.submit_and_stream("Hello", session) is False


# ============================================================================
# 3. CLI Main Entrypoint Tests
# ============================================================================

class TestAsyncMain:

    @pytest.mark.asyncio
    async def test_ping_flag_success(self):
        """--ping flag outputs success and exits with code 0."""
        test_args = ["cli.py", "--ping"]
        with patch("sys.argv", test_args), \
             patch.object(CharonClient, "ping_daemon", new_callable=AsyncMock, return_value=True), \
             pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    @pytest.mark.asyncio
    async def test_ping_flag_failure(self):
        """--ping flag outputs error and exits with code 1 when offline."""
        test_args = ["cli.py", "--ping"]
        with patch("sys.argv", test_args), \
             patch.object(CharonClient, "ping_daemon", new_callable=AsyncMock, return_value=False), \
             pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_unreachable_daemon_exit(self):
        """Main execution exits if pre-flight ping fails."""
        test_args = ["cli.py", "status"]
        with patch("sys.argv", test_args), \
             patch.object(CharonClient, "ping_daemon", new_callable=AsyncMock, return_value=False), \
             pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_positional_command_non_interactive(self):
        """Positional command with -n flag executes once and exits."""
        test_args = ["cli.py", "build", "project", "-n"]
        with patch("sys.argv", test_args), \
             patch.object(CharonClient, "ping_daemon", new_callable=AsyncMock, return_value=True), \
             patch.object(CharonClient, "submit_and_stream", new_callable=AsyncMock, return_value=True), \
             pytest.raises(SystemExit) as exc_info:
            await async_main()
        assert exc_info.value.code == 0

    @pytest.mark.asyncio
    async def test_positional_command_interactive(self):
        """Positional command without -n executes initial command, then enters interactive loop."""
        test_args = ["cli.py", "status"]
        mock_session = AsyncMock()
        mock_session.prompt_async.return_value = "exit"

        with patch("sys.argv", test_args), \
             patch("charon.cli.PromptSession", return_value=mock_session), \
             patch.object(CharonClient, "ping_daemon", new_callable=AsyncMock, return_value=True), \
             patch.object(CharonClient, "submit_and_stream", new_callable=AsyncMock, return_value=True) as mock_submit:
            await async_main()
            assert mock_submit.called
            assert mock_session.prompt_async.called

    @pytest.mark.asyncio
    async def test_interactive_loop_valid_command_and_empty(self):
        """Tests valid user input, empty input loopbacks, and safe exit in REPL."""
        test_args = ["cli.py"]
        mock_session = AsyncMock()

        mock_session.prompt_async.side_effect = ["", "run diagnostic", "exit"]

        with patch("sys.argv", test_args), \
             patch("charon.cli.PromptSession", return_value=mock_session), \
             patch.object(CharonClient, "ping_daemon", new_callable=AsyncMock, return_value=True), \
             patch.object(CharonClient, "submit_and_stream", new_callable=AsyncMock, return_value=True) as mock_submit:
            await async_main()

            assert mock_submit.call_count == 1
            assert mock_submit.call_args[0][0] == "run diagnostic"

    @pytest.mark.asyncio
    async def test_interactive_loop_keyboard_interrupt(self):
        """Test KeyboardInterrupt exception block in interactive loop."""
        test_args = ["cli.py"]
        mock_session = AsyncMock()
        mock_session.prompt_async.side_effect = KeyboardInterrupt

        with patch("sys.argv", test_args), \
             patch("charon.cli.PromptSession", return_value=mock_session), \
             patch.object(CharonClient, "ping_daemon", new_callable=AsyncMock, return_value=True):
            await async_main()
            assert mock_session.prompt_async.called

    @pytest.mark.asyncio
    async def test_interactive_loop_eof_error(self):
        """Test EOFError exception block in interactive loop."""
        test_args = ["cli.py"]
        mock_session = AsyncMock()
        mock_session.prompt_async.side_effect = EOFError

        with patch("sys.argv", test_args), \
             patch("charon.cli.PromptSession", return_value=mock_session), \
             patch.object(CharonClient, "ping_daemon", new_callable=AsyncMock, return_value=True):
            await async_main()
            assert mock_session.prompt_async.called

    def test_main_wrapper(self):
        """Test synchronous main() wrapper handling KeyboardInterrupt."""
        with patch("charon.cli.async_main", side_effect=KeyboardInterrupt):
            main()
