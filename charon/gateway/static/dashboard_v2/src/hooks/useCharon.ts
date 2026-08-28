import { useState, useEffect } from 'react';
import { wsClient, CharonWSFrame } from '../core/ws/CharonStream';

export const useCharon = () => {
  const [activeTask, setActiveTask] = useState<any>(null);
  const [telemetry, setTelemetry] = useState<CharonWSFrame[]>([]);
  const [finalResult, setFinalResult] = useState<any>(null);

  useEffect(() => {
    // 0. Status Stream (Captures initial "queued" acknowledgment and task_id)
    const unsubStatus = wsClient.subscribe('status_change', (frame: CharonWSFrame) => {
      const data = frame.data || frame;
      if (data.status === 'queued') {
        setActiveTask((prev: any) => ({
          ...prev,
          task_id: frame.task_id || data.task_id,
          status: 'Queued',
          timestamp: frame.timestamp || new Date().toISOString(),
        }));
      }
    });

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
      unsubStatus();
      unsubHeartbeat();
      unsubTrace();
      unsubProgress();
      unsubGap();
      unsubCompleted();
    };
  }, []);

  const submitTask = (prompt: string, agentOverride?: string) => {
    setFinalResult(null);
    setTelemetry([]);
    setActiveTask({ status: 'Submitting task...', active_agent: 'Gateway' });

    // Push task strictly over the WebSocket (Fire-and-forget)
    wsClient.send({
      action: 'submit_task',
      prompt,
      agent_override: agentOverride,
    });

    // Note: We no longer return a promise because the acknowledgment
    // will arrive asynchronously via the 'status_change' event listener above.
  };

  return { activeTask, telemetry, finalResult, submitTask };
};