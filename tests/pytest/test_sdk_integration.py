#!/usr/bin/env python3
"""Standalone Integration Test Suite for Charon SDK (`sdk.py`).

Spins up an ephemeral mock daemon server, connects `CharonClientNode`, and tests:
  1. API Key Authentication & Health REST Endpoint
  2. Automatic Hardware Telemetry Discovery
  3. Task Submission REST Endpoint
  4. Real-time WebSocket Event Dispatching
  5. Gatekeeper Authorization Intercept & Response
"""

import asyncio
import logging
import socket
import sys
from typing import Dict, List

import pytest
from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import uvicorn

# Import target SDK node
from charon.sdk import CharonClientNode, WSEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TestSDK")

TEST_API_KEY = "test-charon-secret-123"


# ==============================================================================
# Helper to Find an Available Ephemeral Port
# ==============================================================================
def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ==============================================================================
# Mock Daemon Server Setup (FastAPI)
# ==============================================================================
app = FastAPI(title="Mock Charond Engine")
active_websockets: Dict[str, WebSocket] = {}


class TaskRequestPayload(BaseModel):
    prompt: str
    client_id: str
    agent_override: str | None = None
    context: dict = {}


class GatekeeperResponsePayload(BaseModel):
    approval_id: str
    decision: str
    client_id: str
    notes: str | None = None


def verify_api_key(x_api_key: str | None = Header(None)):
    if x_api_key != TEST_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized API Key")


@app.get("/v1/health")
async def health():
    return {"status": "ok", "version": "3.1.0-mock"}


@app.post("/v1/task")
async def submit_task(payload: TaskRequestPayload, x_api_key: str | None = Header(None)):
    verify_api_key(x_api_key)
    task_id = "task_test_999"

    # Trigger async event sequence over WebSocket if client is connected
    asyncio.create_task(_simulate_task_lifecycle(payload.client_id, task_id, payload.prompt))

    return {
        "task_id": task_id,
        "status": "queued",
        "assigned_agent": payload.agent_override or "orchestrator",
        "message": "Task queued successfully",
    }


@app.post("/v1/gatekeeper/respond")
async def gatekeeper_respond(payload: GatekeeperResponsePayload, x_api_key: str | None = Header(None)):
    verify_api_key(x_api_key)

    # Broadcast task completion after approval
    ws = active_websockets.get(payload.client_id)
    if ws:
        event = WSEvent(
            event_type="task_complete",
            task_id="task_test_999",
            client_id=payload.client_id,
            data={"summary": f"Action authorized ({payload.decision}) and executed successfully."},
        )
        await ws.send_text(event.model_dump_json())

    return {"status": "accepted", "approval_id": payload.approval_id}


@app.websocket("/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str = Query(...),
    api_key: str | None = Query(None),
    x_api_key: str | None = Header(None),
):
    key = api_key or x_api_key
    if key != TEST_API_KEY:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    active_websockets[client_id] = websocket
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_websockets.pop(client_id, None)


async def _simulate_task_lifecycle(client_id: str, task_id: str, prompt: str):
    await asyncio.sleep(0.1)
    ws = active_websockets.get(client_id)
    if not ws:
        return

    # 1. Stream log chunk
    log_event = WSEvent(
        event_type="agent_log",
        task_id=task_id,
        client_id=client_id,
        data={"message": f"Analyzing task prompt: '{prompt}'...\n"},
    )
    await ws.send_text(log_event.model_dump_json())
    await asyncio.sleep(0.1)

    # 2. Trigger Gatekeeper Intercept
    intercept_event = WSEvent(
        event_type="gatekeeper_intercept",
        task_id=task_id,
        client_id=client_id,
        data={
            "approval_id": "appr_777",
            "action": "Execute high-risk system command",
            "manifest": "Target: /dev/sda1",
        },
    )
    await ws.send_text(intercept_event.model_dump_json())


# ==============================================================================
# Integration Test Execution
# ==============================================================================
async def run_integration_tests():
    port = get_free_port()
    server_url = f"http://127.0.0.1:{port}"

    # Start Uvicorn mock daemon in background
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # Wait briefly for mock daemon startup
    await asyncio.sleep(0.5)

    client_id = "test_node_01"
    received_events: List[WSEvent] = []
    intercept_received = asyncio.Event()
    task_completed = asyncio.Event()

    # Initialize SDK Client Node
    node = CharonClientNode(
        client_id=client_id,
        engine_url=server_url,
        api_key=TEST_API_KEY,
        auto_discover_hardware=True,
    )

    # Register event handlers via SDK decorator
    @node.on("agent_log")
    async def handle_log(event: WSEvent):
        logger.info(f"[SDK Received Log]: {event.data.get('message', '').strip()}")
        received_events.append(event)

    @node.on("gatekeeper_intercept")
    async def handle_intercept(event: WSEvent):
        logger.info(f"[SDK Received Intercept]: Approval ID = {event.data.get('approval_id')}")
        received_events.append(event)
        intercept_received.set()

    @node.on("task_complete")
    async def handle_completion(event: WSEvent):
        logger.info(f"[SDK Received Complete]: {event.data.get('summary')}")
        received_events.append(event)
        task_completed.set()

    try:
        logger.info("=== TEST 1: Connection & Health Check ===")
        await node.connect()

        await asyncio.sleep(0.1)

        assert node.is_connected, "Node failed to establish WebSocket connection"

        health_res = await node.check_health()
        assert health_res["status"] == "ok"
        logger.info("✓ Health check REST call passed.")

        logger.info("\n=== TEST 2: Telemetry Discovery ===")
        telemetry = node.telemetry
        assert "hostname" in telemetry
        assert "ip_address" in telemetry
        assert "os" in telemetry
        logger.info(f"✓ Telemetry auto-discovered: OS={telemetry['os']}, Cores={telemetry['cpu_cores']}")

        logger.info("\n=== TEST 3: Task Submission & WS Streaming ===")
        task_res = await node.submit_task(
            prompt="Perform deep hardware diagnostics",
            agent_override="engineer",
        )
        assert task_res.task_id == "task_test_999"
        logger.info(f"✓ Task submitted successfully: Task ID = {task_res.task_id}")

        # Await WS Gatekeeper Intercept Event
        await asyncio.wait_for(intercept_received.wait(), timeout=3.0)
        logger.info("✓ WebSocket Gatekeeper intercept received.")

        logger.info("\n=== TEST 4: Gatekeeper Response ===")
        gk_res = await node.respond_gatekeeper(
            approval_id="appr_777",
            decision="proceed",
            notes="Authorized by automated test suite",
        )
        assert gk_res["status"] == "accepted"
        logger.info("✓ Gatekeeper decision transmitted via REST.")

        # Await final Task Completion Event
        await asyncio.wait_for(task_completed.wait(), timeout=3.0)
        logger.info("✓ Final task completion event received via WebSocket stream.")

        assert len(received_events) == 3, f"Expected 3 events, got {len(received_events)}"
        logger.info("\n[SUCCESS] All Charon SDK Integration Tests Passed!")

    finally:
        # Cleanup Node & Server
        await node.disconnect()
        server.should_exit = True
        await server_task


# Pytest runner entrypoint
@pytest.mark.asyncio
async def test_charon_sdk_integration():
    await run_integration_tests()


if __name__ == "__main__":
    try:
        asyncio.run(run_integration_tests())
    except KeyboardInterrupt:
        sys.exit(0)
