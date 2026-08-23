import React, { useEffect, useState } from 'react';
import { wsClient } from '../../core/ws/CharonStream';

interface LogEvent {
  id: string;
  timestamp: string;
  level: string;
  message: string;
  source: string;
}

export function TriageTelemetry() {
  const [logs, setLogs] = useState<LogEvent[]>([]);

  useEffect(() => {
    // Subscribe to triage logs via the WebSocket
    const unsubscribe = wsClient.subscribe('triage_log', (frame) => {
      const newLog: LogEvent = {
        id: crypto.randomUUID(),
        timestamp: new Date().toLocaleTimeString(),
        level: frame.data?.level || 'INFO',
        message: frame.data?.message || JSON.stringify(frame.data),
        source: frame.data?.source || 'system',
      };
      
      setLogs(prev => [newLog, ...prev].slice(0, 50)); // Keep last 50 logs
    });

    return () => unsubscribe();
  }, []);

  return (
    <div style={{ marginTop: '2rem', border: '1px solid #333', borderRadius: '8px', padding: '1rem', backgroundColor: '#1e1e1e', color: '#fff' }}>
      <h2 style={{ marginTop: 0, fontSize: '1.2rem', borderBottom: '1px solid #444', paddingBottom: '0.5rem' }}>Live Triage Telemetry</h2>
      <div style={{ height: '300px', overflowY: 'auto', fontFamily: 'monospace', fontSize: '0.9rem', marginTop: '1rem' }}>
        {logs.length === 0 ? (
          <div style={{ color: '#888', fontStyle: 'italic' }}>Waiting for daemon telemetry...</div>
        ) : (
          logs.map(log => (
            <div key={log.id} style={{ marginBottom: '4px', display: 'flex', gap: '8px' }}>
              <span style={{ color: '#888', minWidth: '85px' }}>[{log.timestamp}]</span>
              <span style={{ 
                color: log.level === 'ERROR' ? '#ef4444' : log.level === 'WARN' ? '#f59e0b' : '#3b82f6',
                width: '50px' 
              }}>{log.level}</span>
              <span style={{ color: '#10b981' }}>[{log.source}]</span>
              <span style={{ wordBreak: 'break-word' }}>{log.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
