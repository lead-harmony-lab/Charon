import React, { useState } from 'react';
import { authFetch } from '../../core/api/client';

export function GnomeIPC() {
  const [payload, setPayload] = useState<string>('{\n  "target": "hud",\n  "command": "show_notification",\n  "message": "Hello from Dashboard"\n}');
  const [status, setStatus] = useState<string>('');

  const handleSendIPC = async () => {
    setStatus('Dispatching...');
    try {
      const parsed = JSON.parse(payload);
      const res = await authFetch('/v1/system/ipc/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed),
      });
      if (res.ok) setStatus('IPC frame dispatched successfully!');
      else setStatus('Failed to send IPC message.');
    } catch (err) {
      setStatus('Invalid JSON payload or dispatch error.');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0, fontSize: '1rem', color: '#f8fafc' }}>Dispatch Desktop IPC Payload</h3>
        <button onClick={handleSendIPC} style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.4rem 1rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer' }}>
          Dispatch Payload
        </button>
      </div>

      <textarea
        value={payload}
        onChange={(e) => setPayload(e.target.value)}
        style={{ width: '100%', height: '240px', backgroundColor: '#0f172a', color: '#38bdf8', border: '1px solid #334155', borderRadius: '6px', padding: '1rem', fontFamily: 'monospace', fontSize: '0.9rem', boxSizing: 'border-box' }}
      />

      {status && <span style={{ fontSize: '0.85rem', color: status.includes('successfully') ? '#10b981' : '#ef4444' }}>{status}</span>}
    </div>
  );
}