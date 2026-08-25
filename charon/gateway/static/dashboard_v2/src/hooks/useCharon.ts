/**
 * @file src/hooks/useCharon.ts
 * @description
 */
import { useState, useEffect } from 'react';
import { wsClient, CharonWSFrame } from '../core/ws/CharonStream';
import { authFetch } from '../core/api/client';

export const useCharon = () => {
  const [activeTask, setActiveTask] = useState<any>(null);
  const [telemetry, setTelemetry] = useState<CharonWSFrame[]>([]);
  const [finalResult, setFinalResult] = useState<any>(null);

  useEffect(() => {
    // 1. Daemon Heartbeat Stream (Engine Pulse)
    const unsubHeartbeat = wsClient.subscribe('task_heartbeat', (frame: CharonWSFrame) => {
      const data = frame.data || frame;
      setActiveTask({
        task_id: frame.task_id || data.task_id,
        status: data.status || 'processing',
        active_agent: data.active_agent || 'Orchestrator',
        elapsed_seconds: data.elapsed_seconds ?? 0,
        timestamp: frame.timestamp || new Date().toISOString(),
      });
    });

    // Helper to push execution updates to telemetry view
    const appendTelemetry = (frame: CharonWSFrame) => {
      setTelemetry((prev) => [...prev, frame]);
    };

    // 2. Granular Execution Telemetry Stream
    const unsubTrace = wsClient.subscribe('telemetry_trace', appendTelemetry);
    const unsubProgress = wsClient.subscribe('task_progress', appendTelemetry);
    const unsubGap = wsClient.subscribe('skill_gap_detected', appendTelemetry);

    // 3. Completion Handler
    const unsubCompleted = wsClient.subscribe('task_complete', (frame: CharonWSFrame) => {
      const data = frame.data || frame;
      const resultPayload = data.summary || data.result || data.output || data.content || data;
      setFinalResult(resultPayload);
      setActiveTask((prev: any) => (prev ? { ...prev, status: 'Completed' } : null));
    });

    return () => {
      unsubHeartbeat();
      unsubTrace();
      unsubProgress();
      unsubGap();
      unsubCompleted();
    };
  }, []);

  const submitTask = async (prompt: string, agentOverride?: string) => {
    setFinalResult(null);
    setTelemetry([]);
    setActiveTask({ status: 'Submitting task...', active_agent: 'Gateway' });

    const response = await authFetch(`/v1/task`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        client_id: wsClient.getClientId(),
        agent_override: agentOverride,
      }),
    });

    if (!response.ok) {
      setActiveTask(null);
      throw new Error(`Task submission failed: ${response.status}`);
    }

    return await response.json();
  };

  return { activeTask, telemetry, finalResult, submitTask };
};