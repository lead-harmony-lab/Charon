import React, { useState, useEffect } from 'react';
import { authFetch } from '../../core/api/client';

interface AuditEntry {
  id: string;
  timestamp: string;
  level: 'INFO' | 'WARN' | 'ERROR';
  source: string;
  message: string;
}

export function AuditLedger() {
  const [logs, setLogs] = useState<AuditEntry[]>([]);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    async function fetchLogs() {
      try {
        const res = await authFetch('/v1/journal/audit');
        if (res.ok) {
          const data = await res.json();
          setLogs(data.logs || []);
        }
      } catch (err) {
        console.error('Failed to load audit logs', err);
      }
    }
    fetchLogs();
  }, []);

  const filteredLogs = logs.filter(
    (log) =>
      log.message.toLowerCase().includes(filter.toLowerCase()) ||
      log.source.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1.25rem' }}>
      <input
        type="text"
        placeholder="Filter logs by source or message..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#e2e8f0', padding: '0.6rem 1rem', borderRadius: '6px', boxSizing: 'border-box' }}
      />

      <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', overflowY: 'auto', maxHeight: '500px' }}>
        {filteredLogs.length === 0 ? (
          <p style={{ color: '#64748b', fontStyle: 'italic' }}>No matching audit records found.</p>
        ) : (
          filteredLogs.map((log) => (
            <div key={log.id} style={{ padding: '0.5rem 0', borderBottom: '1px solid #334155', display: 'flex', gap: '1rem' }}>
              <span style={{ color: '#64748b' }}>[{new Date(log.timestamp).toLocaleTimeString()}]</span>
              <span style={{ color: log.level === 'ERROR' ? '#ef4444' : log.level === 'WARN' ? '#f59e0b' : '#38bdf8', fontWeight: 'bold' }}>
                {log.level}
              </span>
              <span style={{ color: '#94a3b8' }}>[{log.source}]</span>
              <span style={{ color: '#f8fafc' }}>{log.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}