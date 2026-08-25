/**
 * @file src/features/system/CharonControl.tsx
 * @description Charon Control Panel with structured Live Telemetry unpacking and formatted Heartbeat.
 */
import React, { useState } from 'react';
import { useCharon } from '../../hooks/useCharon';

export function CharonControl() {
  const { activeTask, telemetry, finalResult, submitTask } = useCharon();
  const [prompt, setPrompt] = useState('');

  const handleRunTask = () => {
    if (prompt.trim()) {
      submitTask(prompt);
      setPrompt('');
    }
  };

  const renderHeartbeat = (task: any) => {
    if (!task) {
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#64748b', fontSize: '0.85rem' }}>
          <span style={{ height: '8px', width: '8px', borderRadius: '50%', backgroundColor: '#64748b' }} />
          <span>Daemon Idle. Ready for tasks.</span>
        </div>
      );
    }

    const taskId = task.task_id || task.taskId || task.id;
    const status = String(task.status || task.state || 'ACTIVE').toUpperCase();
    const promptText = task.prompt || task.original_prompt || task.description;
    const activeAgent = task.active_agent || task.agent_name || task.agent;
    const progress = task.progress_pct ?? task.progress;

    const knownKeys = ['task_id', 'taskId', 'id', 'status', 'state', 'prompt', 'original_prompt', 'description', 'active_agent', 'agent_name', 'agent', 'progress_pct', 'progress'];
    const extraDetails = Object.entries(task).filter(([k]) => !knownKeys.includes(k));

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.85rem' }}>
        {/* Header: ID & Status */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ height: '8px', width: '8px', borderRadius: '50%', backgroundColor: '#38bdf8', boxShadow: '0 0 8px #38bdf8' }} />
            {taskId ? (
              <code style={{ color: '#38bdf8', fontWeight: 600, fontFamily: 'monospace', fontSize: '0.8rem', backgroundColor: '#1e293b', padding: '2px 6px', borderRadius: '4px', border: '1px solid #334155' }}>
                {taskId}
              </code>
            ) : (
              <span style={{ color: '#94a3b8', fontStyle: 'italic', fontSize: '0.8rem' }}>Initializing Task...</span>
            )}
          </div>

          <span style={{
            fontSize: '0.7rem',
            fontWeight: 700,
            letterSpacing: '0.05em',
            padding: '2px 8px',
            borderRadius: '4px',
            backgroundColor: status.includes('COMPLETE') ? 'rgba(16, 185, 129, 0.15)' : status.includes('FAIL') ? 'rgba(239, 68, 68, 0.15)' : 'rgba(56, 189, 248, 0.15)',
            color: status.includes('COMPLETE') ? '#34d399' : status.includes('FAIL') ? '#f87171' : '#38bdf8',
            border: `1px solid ${status.includes('COMPLETE') ? 'rgba(52, 211, 153, 0.3)' : status.includes('FAIL') ? 'rgba(248, 113, 113, 0.3)' : 'rgba(56, 189, 248, 0.3)'}`
          }}>
            {status}
          </span>
        </div>

        {/* Active Agent & Progress */}
        {(activeAgent || progress != null) && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', backgroundColor: '#1e293b', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid #334155' }}>
            {activeAgent && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <span style={{ color: '#64748b', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: 600 }}>Active Agent</span>
                <span style={{ color: '#c084fc', fontWeight: 600, fontFamily: 'monospace', fontSize: '0.8rem' }}>&lt;{activeAgent}&gt;</span>
              </div>
            )}
            {progress != null && (
              <span style={{ color: '#fbbf24', fontSize: '0.75rem', fontWeight: 600, fontFamily: 'monospace' }}>
                {progress}%
              </span>
            )}
          </div>
        )}

        {/* Prompt Card */}
        {promptText && (
          <div style={{ backgroundColor: '#0f172a', padding: '0.6rem 0.75rem', borderRadius: '6px', border: '1px solid #1e293b' }}>
            <span style={{ color: '#64748b', fontSize: '0.7rem', display: 'block', marginBottom: '4px', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.05em' }}>Prompt</span>
            <div style={{ color: '#cbd5e1', fontSize: '0.8rem', lineHeight: '1.4' }}>{promptText}</div>
          </div>
        )}

        {/* Metadata Chips */}
        {extraDetails.length > 0 && (
          <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', marginTop: '0.15rem' }}>
            {extraDetails.map(([key, val]) => (
              <span key={key} style={{ fontSize: '0.7rem', color: '#94a3b8', backgroundColor: '#1e293b', border: '1px solid #334155', padding: '2px 6px', borderRadius: '4px' }}>
                <strong style={{ color: '#64748b' }}>{key}:</strong> {typeof val === 'object' ? JSON.stringify(val) : String(val)}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderTelemetryPayload = (payload: any) => {
    if (!payload || typeof payload !== 'object') {
      return <span style={{ color: '#cbd5e1' }}>{String(payload)}</span>;
    }

    const { action, event_type, duration_ms, reasoning_chunk, details } = payload;

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', marginTop: '0.35rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          {action && (
            <span style={{ color: '#f1f5f9', fontWeight: 600 }}>
              Action: <code style={{ color: '#38bdf8', backgroundColor: '#1e293b', padding: '2px 6px', borderRadius: '4px', fontFamily: 'monospace' }}>{action}</code>
            </span>
          )}

          {event_type && (
            <span style={{ fontSize: '0.75rem', color: '#94a3b8', backgroundColor: '#334155', padding: '1px 6px', borderRadius: '3px', textTransform: 'uppercase' }}>
              {event_type}
            </span>
          )}

          {duration_ms != null && (
            <span style={{ fontSize: '0.75rem', color: '#fbbf24', marginLeft: 'auto', fontWeight: 600 }}>
              ⚡ {typeof duration_ms === 'number' ? duration_ms.toFixed(1) : duration_ms} ms
            </span>
          )}
        </div>

        {reasoning_chunk && (
          <div style={{ color: '#cbd5e1', fontStyle: 'italic', fontSize: '0.8rem', backgroundColor: '#1e293b', padding: '0.5rem', borderRadius: '4px', borderLeft: '3px solid #c084fc' }}>
            "{reasoning_chunk}"
          </div>
        )}

        {details && Object.keys(details).length > 0 && (
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.15rem' }}>
            {Object.entries(details).map(([key, val]) => (
              <span key={key} style={{ fontSize: '0.75rem', color: '#cbd5e1', backgroundColor: '#0f172a', border: '1px solid #334155', padding: '2px 6px', borderRadius: '4px' }}>
                <strong style={{ color: '#64748b' }}>{key}:</strong> {String(val)}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', height: '100%' }}>

      {/* Task Submission */}
      <div style={{ display: 'flex', gap: '10px', backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1.25rem' }}>
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              handleRunTask();
            }
          }}
          placeholder="Issue a command to the Charon Daemon..."
          style={{ flex: 1, padding: '0.75rem', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', borderRadius: '4px' }}
        />
        <button
          onClick={handleRunTask}
          style={{ padding: '0.75rem 1.5rem', backgroundColor: '#38bdf8', border: 'none', color: '#0f172a', fontWeight: 'bold', borderRadius: '4px', cursor: 'pointer' }}
        >
          Execute
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        {/* Active Task / Heartbeat */}
        <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1.25rem' }}>
          <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', color: '#f8fafc' }}>Daemon Heartbeat</h3>
          <div style={{ backgroundColor: '#0f172a', padding: '1rem', borderRadius: '6px', border: '1px solid #334155' }}>
            {renderHeartbeat(activeTask)}
          </div>
        </div>

        {/* Final Output */}
        <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1.25rem' }}>
          <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', color: '#f8fafc' }}>Task Result</h3>
          <pre style={{ margin: 0, backgroundColor: '#0f172a', padding: '1rem', borderRadius: '6px', border: '1px solid #334155', color: '#10b981', fontSize: '0.85rem', overflowX: 'auto', minHeight: '60px' }}>
            {finalResult ? JSON.stringify(finalResult, null, 2) : 'Awaiting output...'}
          </pre>
        </div>
      </div>

      {/* Real-time Telemetry */}
      <div style={{ flex: 1, backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1.25rem', display: 'flex', flexDirection: 'column' }}>
        <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', color: '#f8fafc' }}>Live Telemetry Trace</h3>
        <div style={{ flex: 1, backgroundColor: '#0f172a', padding: '1rem', borderRadius: '6px', overflowY: 'auto', border: '1px solid #334155' }}>
          {telemetry.map((frame, idx) => {
            const payload = frame.data || frame.payload || {};
            const agentName = frame.agent_name || payload.agent_name;

            return (
              <div key={idx} style={{ marginBottom: '0.75rem', borderBottom: '1px solid #1e293b', paddingBottom: '0.75rem', fontSize: '0.85rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ color: '#38bdf8', fontWeight: 'bold' }}>[{frame.event_type}]</span>
                  {agentName && <span style={{ color: '#c084fc', fontWeight: 600 }}>&lt;{agentName}&gt;</span>}
                </div>
                {renderTelemetryPayload(payload)}
              </div>
            );
          })}
          {telemetry.length === 0 && <span style={{ color: '#64748b', fontSize: '0.85rem' }}>Awaiting telemetry stream...</span>}
        </div>
      </div>

    </div>
  );
}