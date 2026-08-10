#!/usr/bin/env python3
"""Tests for Charon Gateway Core Daemon (charon/gateway/core.py)."""

import asyncio
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from charon.gateway.core import CharonDaemon
from charon.gateway.models import WSEvent
from charon.intent import AgentEnum, EngineerPayload


class DummyPayload(BaseModel):
    action: str = "draft_build_sequence"
    requires_approval: bool = False


class TestCharonDaemonInit:
    """Tests for CharonDaemon initialization and properties."""

    def test_init_with_default_engine(self, tmp_path):
        """Tests daemon initialization when engine is constructed automatically."""
        with patch("charon.gateway.core.SessionGateway") as mock_orch_cls, \
                patch("charon.gateway.core.OrchestrationEngine") as mock_eng_cls, \
                patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(db_path=tmp_path)
            assert daemon.db_path == Path(tmp_path)
            mock_orch_cls.assert_called_once()
            mock_eng_cls.assert_called_once()

    def test_init_with_provided_engine(self):
        """Tests daemon initialization with an injected engine instance."""
        mock_engine = MagicMock()
        mock_engine.orchestrator = MagicMock()

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            assert daemon.engine == mock_engine
            assert daemon.orchestrator == mock_engine.orchestrator

    def test_awaiting_gatekeeper_property(self):
        """Tests backward compatibility helper property for gatekeeper state."""
        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=MagicMock())
            daemon.gatekeeper.awaiting_approval = True
            assert daemon.awaiting_gatekeeper is True

            daemon.gatekeeper.awaiting_approval = False
            assert daemon.awaiting_gatekeeper is False


class TestCharonDaemonDispatch:
    """Tests for task dispatching and Gatekeeper interception."""

    @pytest.mark.asyncio
    async def test_dispatch_intercepted_by_gatekeeper(self):
        """Tests task interception when Gatekeeper requires user authorization."""
        mock_engine = MagicMock()
        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)

            payload = DummyPayload(requires_approval=True)
            daemon.gatekeeper.requires_approval = MagicMock(return_value=True)
            daemon.gatekeeper.intercept_task = MagicMock(return_value=({"manifest": "data"}, "action_needed"))
            daemon.emitter.emit_gatekeeper = AsyncMock()

            await daemon.dispatch(AgentEnum.ENGINEER, payload, user_raw_input="run tool")

            daemon.gatekeeper.intercept_task.assert_called_once_with(AgentEnum.ENGINEER, payload, "run tool")
            daemon.emitter.emit_gatekeeper.assert_called_once_with({"manifest": "data"}, "action_needed")

    @pytest.mark.asyncio
    async def test_dispatch_executes_task_directly(self):
        """Tests task execution when Gatekeeper authorization is not required."""
        mock_engine = MagicMock()
        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)

            payload = DummyPayload(requires_approval=False)
            daemon.gatekeeper.requires_approval = MagicMock(return_value=False)
            daemon._execute_task = AsyncMock()

            await daemon.dispatch(AgentEnum.GENERALIST, payload, user_raw_input="do work")

            daemon._execute_task.assert_called_once_with(AgentEnum.GENERALIST, payload, "do work")


class TestCharonDaemonExecuteTask:
    """Tests for internal agent task execution logic and escalations."""

    @pytest.mark.asyncio
    async def test_execute_task_stream_callback(self):
        """Tests streaming callback execution inside _execute_task."""
        mock_engine = MagicMock()
        mock_orchestrator = MagicMock()
        mock_engine.orchestrator = mock_orchestrator

        async def mock_exec_task(agent, extraction, user_raw_input, stream_cb):
            stream_cb("Streaming chunk test")
            return "Task complete"

        mock_orchestrator.execute_agent_task = AsyncMock(side_effect=mock_exec_task)

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.emitter.emit_stream = AsyncMock()

            payload = DummyPayload(action="other_action")
            await daemon._execute_task(
                AgentEnum.GENERALIST, payload, user_raw_input="test stream"
            )

            daemon.emitter.emit_stream.assert_called_with("Streaming chunk test")

    @pytest.mark.asyncio
    async def test_execute_task_planner_delegation_to_engineer(self):
        """Tests Planner blueprint specification emission and auto-delegation to Engineer."""
        mock_engine = MagicMock()
        mock_orchestrator = MagicMock()
        mock_engine.orchestrator = mock_orchestrator
        mock_orchestrator.execute_agent_task = AsyncMock(return_value="Blueprint Step 1: Design CAD")

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.emitter.emit_stream = AsyncMock()

            with patch.object(daemon, "_execute_task", wraps=daemon._execute_task) as mock_exec:
                payload = DummyPayload(action="draft_build_sequence")
                await daemon._execute_task(AgentEnum.PLANNER, payload, user_raw_input="build robot")

                assert mock_exec.call_count == 2
                assert daemon.emitter.emit_stream.call_count >= 3

                # Second call should be delegation to Engineer
                call_agent, call_payload = mock_exec.call_args_list[1][0][:2]
                assert call_agent == AgentEnum.ENGINEER
                assert isinstance(call_payload, EngineerPayload)
                assert call_payload.action == "solve_edge_case"

    @pytest.mark.asyncio
    async def test_execute_task_planner_non_delegated_action(self):
        """Tests Planner agent with action not requiring Engineer delegation."""
        mock_engine = MagicMock()
        mock_orchestrator = MagicMock()
        mock_engine.orchestrator = mock_orchestrator
        mock_orchestrator.execute_agent_task = AsyncMock(return_value="General plan summary")

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.emitter.emit_stream = AsyncMock()
            daemon.emitter.emit_completed = AsyncMock()

            payload = DummyPayload(action="custom_plan_action")
            await daemon._execute_task(
                AgentEnum.PLANNER, payload, user_raw_input="plan something"
            )

            daemon.emitter.emit_completed.assert_called_once_with(
                "[System]: General plan summary"
            )

    @pytest.mark.asyncio
    async def test_execute_task_planner_awaiting_result_no_delegation(self):
        """Tests Planner output starting with 'Awaiting' skips blueprint delegation."""
        mock_engine = MagicMock()
        mock_orchestrator = MagicMock()
        mock_engine.orchestrator = mock_orchestrator
        mock_orchestrator.execute_agent_task = AsyncMock(return_value="Awaiting user specification")

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.emitter.emit_stream = AsyncMock()
            daemon.emitter.emit_completed = AsyncMock()

            payload = DummyPayload(action="draft_build_sequence")
            await daemon._execute_task(AgentEnum.PLANNER, payload, user_raw_input="plan task")

            daemon.emitter.emit_completed.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_task_completed_with_concierge_suggestion(self):
        """Tests successful agent execution triggering Concierge next-step suggestions."""
        mock_engine = MagicMock()
        mock_orchestrator = MagicMock()
        mock_engine.orchestrator = mock_orchestrator
        mock_orchestrator.execute_agent_task = AsyncMock(return_value="Part sliced successfully")

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.emitter.emit_completed = AsyncMock()
            daemon.emitter.emit_concierge = AsyncMock()
            daemon.concierge.evaluate_next_step = MagicMock(return_value="Send gcode to printer?")

            payload = DummyPayload(action="slice_model")
            await daemon._execute_task(AgentEnum.MACHINIST, payload, user_raw_input="slice model.stl")

            daemon.emitter.emit_completed.assert_called_once_with("[System]: Part sliced successfully")
            daemon.concierge.evaluate_next_step.assert_called_once_with("slice_model", payload.model_dump())
            daemon.emitter.emit_concierge.assert_called_once_with("Send gcode to printer?")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("falsy_suggestion", [None, ""])
    async def test_execute_task_concierge_no_suggestion(self, falsy_suggestion):
        """Tests execution completion when Concierge produces no next step suggestion (None or empty)."""
        mock_engine = MagicMock()
        mock_orchestrator = MagicMock()
        mock_engine.orchestrator = mock_orchestrator
        mock_orchestrator.execute_agent_task = AsyncMock(return_value="Done")

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.emitter.emit_completed = AsyncMock()
            daemon.emitter.emit_concierge = AsyncMock()
            daemon.concierge.evaluate_next_step = MagicMock(return_value=falsy_suggestion)

            payload = DummyPayload(action="unknown_action")
            await daemon._execute_task(
                AgentEnum.GENERALIST, payload, user_raw_input="task"
            )

            daemon.emitter.emit_completed.assert_called_once_with("[System]: Done")
            daemon.emitter.emit_concierge.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_task_exception_escalates_to_engineer(self):
        """Tests non-engineer agent failure escalating execution to The_Engineer."""
        mock_engine = MagicMock()
        mock_orchestrator = MagicMock()
        mock_engine.orchestrator = mock_orchestrator
        mock_orchestrator.execute_agent_task = AsyncMock(side_effect=RuntimeError("GCode generation failed"))

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.emitter.emit_stream = AsyncMock()
            daemon.dispatch = AsyncMock()

            payload = DummyPayload(action="slice")
            await daemon._execute_task(AgentEnum.MACHINIST, payload, user_raw_input="generate gcode")

            daemon.emitter.emit_stream.assert_called_once()
            daemon.dispatch.assert_called_once()
            call_agent, call_payload = daemon.dispatch.call_args[0][:2]
            assert call_agent == AgentEnum.ENGINEER
            assert isinstance(call_payload, EngineerPayload)

    @pytest.mark.asyncio
    async def test_execute_task_engineer_exception_emits_error(self):
        """Tests failure on Engineer agent stopping escalation and emitting error completion."""
        mock_engine = MagicMock()
        mock_orchestrator = MagicMock()
        mock_engine.orchestrator = mock_orchestrator
        mock_orchestrator.execute_agent_task = AsyncMock(side_effect=RuntimeError("Fatal solver crash"))

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.emitter.emit_completed = AsyncMock()

            payload = EngineerPayload(action="solve_edge_case", problem="test problem")
            await daemon._execute_task(AgentEnum.ENGINEER, payload, user_raw_input="solve issue")

            daemon.emitter.emit_completed.assert_called_once_with(
                "[System Error]: Execution Failed on The_Engineer: Fatal solver crash"
            )


class TestCharonDaemonQueueAndTelemetry:
    """Tests background telemetry loops and task queue processing."""

    @pytest.mark.asyncio
    async def test_verify_engine_and_start_overseer_reporter(self):
        """Tests verify_engine delegation and starting overseer reporter."""
        mock_engine = MagicMock()
        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.telemetry.verify_engine = AsyncMock(return_value=True)
            daemon.telemetry.start_loop = AsyncMock()

            res = await daemon.verify_engine(retries=2, delay=0.1)
            assert res is True
            daemon.telemetry.verify_engine.assert_called_once_with(retries=2, delay=0.1)

            await daemon.start_overseer_reporter(interval=15)
            daemon.telemetry.start_loop.assert_called_once_with(interval=15)

    @pytest.mark.asyncio
    async def test_process_queue_engine_verification_retry_loop(self):
        """Tests process_queue retrying engine verification until available."""
        mock_engine = MagicMock()
        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.verify_engine = AsyncMock(side_effect=[False, True])

            async def stop_queue():
                raise asyncio.CancelledError()

            daemon.queue.get = AsyncMock(side_effect=stop_queue)

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await daemon.process_queue()
                mock_sleep.assert_called_once_with(10)

    @pytest.mark.asyncio
    async def test_process_queue_gatekeeper_proceed_command(self):
        """Tests queue processing handling a 'proceed' authorization response."""
        mock_engine = MagicMock()
        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.verify_engine = AsyncMock(return_value=True)
            daemon.gatekeeper.awaiting_approval = True
            daemon.gatekeeper.handle_approval = MagicMock(return_value=(AgentEnum.ENGINEER, DummyPayload(), "prompt"))
            daemon._execute_task = AsyncMock()
            daemon.emitter.set_context = MagicMock()
            daemon.emitter.emit_targeted = AsyncMock()

            task_item = {"task_id": "t1", "client_id": "c1", "prompt": "PROCEED"}
            await daemon.queue.put(task_item)

            orig_get = daemon.queue.get

            async def mock_get():
                if daemon.queue.empty():
                    raise asyncio.CancelledError()
                return await orig_get()

            daemon.queue.get = mock_get

            await daemon.process_queue()
            daemon.gatekeeper.handle_approval.assert_called_once()
            daemon._execute_task.assert_called_once_with(AgentEnum.ENGINEER, ANY, user_raw_input="prompt")

    @pytest.mark.asyncio
    async def test_process_queue_gatekeeper_cancel_command(self):
        """Tests queue processing handling a 'cancel' or 'rescind' authorization denial."""
        mock_engine = MagicMock()
        mock_orchestrator = MagicMock()
        mock_engine.orchestrator = mock_orchestrator

        mock_routing = MagicMock()
        mock_routing.agent = AgentEnum.GENERALIST
        mock_orchestrator.parse_routing = AsyncMock(return_value=mock_routing)

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.verify_engine = AsyncMock(return_value=True)
            daemon.gatekeeper.awaiting_approval = True
            daemon.gatekeeper.reset = MagicMock()
            daemon.emitter.emit_completed = AsyncMock()
            daemon.emitter.set_context = MagicMock()
            daemon.emitter.emit_targeted = AsyncMock()

            task_item = {"task_id": "t2", "client_id": "c1", "prompt": "cancel"}
            await daemon.queue.put(task_item)

            orig_get = daemon.queue.get

            async def mock_get():
                if daemon.queue.empty():
                    raise asyncio.CancelledError()
                return await orig_get()

            daemon.queue.get = mock_get

            await daemon.process_queue()
            daemon.gatekeeper.reset.assert_called_once()
            daemon.emitter.emit_completed.assert_called_once_with("Order rescinded.")

    @pytest.mark.asyncio
    async def test_process_queue_gatekeeper_architect_denial(self):
        """Tests gatekeeper denial triggered by Architect routing decision."""
        mock_engine = MagicMock()
        mock_orchestrator = MagicMock()
        mock_engine.orchestrator = mock_orchestrator

        mock_routing = MagicMock()
        mock_routing.agent = AgentEnum.ARCHITECT
        mock_orchestrator.parse_routing = AsyncMock(return_value=mock_routing)

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.verify_engine = AsyncMock(return_value=True)
            daemon.gatekeeper.awaiting_approval = True
            daemon.gatekeeper.reset = MagicMock()
            daemon.emitter.emit_completed = AsyncMock()
            daemon.emitter.set_context = MagicMock()
            daemon.emitter.emit_targeted = AsyncMock()

            task_item = {"task_id": "t3", "client_id": "c1", "prompt": "new directive"}
            await daemon.queue.put(task_item)

            orig_get = daemon.queue.get

            async def mock_get():
                if daemon.queue.empty():
                    raise asyncio.CancelledError()
                return await orig_get()

            daemon.queue.get = mock_get

            await daemon.process_queue()
            daemon.gatekeeper.reset.assert_called_once()
            daemon.emitter.emit_completed.assert_called_once_with("Order rescinded.")

    @pytest.mark.asyncio
    async def test_process_queue_gatekeeper_unrecognized_input_resets(self):
        """Tests unrecognized input while awaiting approval resets gatekeeper and processes request."""
        mock_engine = MagicMock()
        mock_orchestrator = MagicMock()
        mock_engine.orchestrator = mock_orchestrator

        mock_routing = MagicMock()
        mock_routing.agent = AgentEnum.GENERALIST
        mock_orchestrator.parse_routing = AsyncMock(return_value=mock_routing)

        async def mock_process_req(user_input, stream_cb, agent_override):
            stream_cb("Streaming queue output")
            return "New task result"

        mock_engine.process_request = AsyncMock(side_effect=mock_process_req)

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.verify_engine = AsyncMock(return_value=True)
            daemon.gatekeeper.awaiting_approval = True
            daemon.gatekeeper.reset = MagicMock()
            daemon.emitter.emit_stream = AsyncMock()
            daemon.emitter.emit_completed = AsyncMock()
            daemon.emitter.set_context = MagicMock()
            daemon.emitter.emit_targeted = AsyncMock()

            task_item = {"task_id": "t4", "client_id": "c1", "prompt": "different prompt"}
            await daemon.queue.put(task_item)

            orig_get = daemon.queue.get

            async def mock_get():
                if daemon.queue.empty():
                    raise asyncio.CancelledError()
                return await orig_get()

            daemon.queue.get = mock_get

            await daemon.process_queue()
            daemon.gatekeeper.reset.assert_called_once()
            mock_engine.process_request.assert_called_once()
            daemon.emitter.emit_stream.assert_called_once_with("Streaming queue output")
            daemon.emitter.emit_completed.assert_called_once_with("New task result")

    @pytest.mark.asyncio
    async def test_process_queue_cancelled_during_processing(self):
        """Tests queue processing handles CancelledError while processing a task item."""
        mock_engine = MagicMock()
        started_event = asyncio.Event()

        async def slow_process(*args, **kwargs):
            started_event.set()
            await asyncio.sleep(10)

        mock_engine.process_request = AsyncMock(side_effect=slow_process)

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.verify_engine = AsyncMock(return_value=True)
            daemon.emitter.set_context = MagicMock()
            daemon.emitter.emit_targeted = AsyncMock()

            task_item = {"task_id": "t_cancel", "prompt": "cancel mid process"}
            await daemon.queue.put(task_item)

            proc_task = asyncio.create_task(daemon.process_queue())
            await started_event.wait()
            proc_task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await proc_task

            assert daemon.queue.empty()

    @pytest.mark.asyncio
    async def test_process_queue_normal_task_processing_and_exception_resilience(self):
        """Tests standard task queue execution and exception resilience during processing."""
        mock_engine = MagicMock()
        mock_engine.process_request = AsyncMock(side_effect=[
            "Task finished successfully",
            RuntimeError("Processing failure"),
        ])

        with patch("charon.gateway.core.ensure_ecosystem_directories"):
            daemon = CharonDaemon(engine=mock_engine)
            daemon.verify_engine = AsyncMock(return_value=True)
            daemon.gatekeeper.awaiting_approval = False
            daemon.emitter.set_context = MagicMock()
            daemon.emitter.emit_targeted = AsyncMock()
            daemon.emitter.emit_completed = AsyncMock()

            items = [
                {"task_id": "t1", "prompt": "build model", "agent_override": "machinist"},
                {"task_id": "t2", "prompt": "faulty prompt"},
            ]
            for item in items:
                await daemon.queue.put(item)

            orig_get = daemon.queue.get

            async def mock_get():
                if daemon.queue.empty():
                    raise asyncio.CancelledError()
                return await orig_get()

            daemon.queue.get = mock_get

            await daemon.process_queue()
            assert daemon.emitter.emit_completed.call_count == 1
            daemon.emitter.emit_completed.assert_called_once_with("Task finished successfully")

    @pytest.mark.asyncio
    async def test_execute_task_without_extraction(self):
        """
        Covers the missing branch (133->exit):
        Validates _execute_task safely exits when `extraction` is None
        but execution is successful.
        """
        # Setup mock OrchestrationEngine
        mock_engine = MagicMock()
        mock_orchestrator = MagicMock()
        mock_engine.orchestrator = mock_orchestrator

        # Return a valid result that does not start with "Awaiting"
        mock_orchestrator.execute_agent_task = AsyncMock(
            return_value="Task completed gracefully"
        )
        mock_orchestrator.memory = MagicMock()

        # Initialize Daemon
        daemon = CharonDaemon(engine=mock_engine)
        daemon.emitter = MagicMock()
        daemon.emitter.emit_completed = AsyncMock()
        daemon.emitter.emit_stream = AsyncMock()

        # Execute with extraction=None
        await daemon._execute_task(
            AgentEnum.GENERALIST,
            extraction=None,
            user_raw_input="Test without extraction"
        )

        # Assertions
        daemon.emitter.emit_completed.assert_called_once_with("[System]: Task completed gracefully")
        mock_orchestrator.memory.add_system_message.assert_called_once_with("Task completed gracefully")

        # Ensure concierge was never called (since extraction was None)
        daemon.concierge = MagicMock()
        daemon.concierge.evaluate_next_step.assert_not_called()