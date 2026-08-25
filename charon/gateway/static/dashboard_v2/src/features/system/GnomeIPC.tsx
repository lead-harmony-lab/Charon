/**
 * @file src/features/system/GnomeIPC.tsx
 * @description Master control component for dispatching real-time IPC frames to the GNOME desktop shell.
 */
import React, { useState } from 'react';
import { wsClient } from '../../core/ws/CharonStream';

export function GnomeIPC() {
  const [payload, setPayload] = useState<string>('{\n  "target": "hud",\n  "command": "show_notification",\n  "title": "👔 Charon IPC",\n  "message": "Hello from the Dashboard!"\n}');
  const [status, setStatus] = useState<string>('');

  const dispatchFrame = (customPayload?: object) => {
    setStatus('Dispatching via WebSocket...');
    try {
      const parsed = customPayload || JSON.parse(payload);

      wsClient.send({
        event_type: 'desktop_ipc',
        client_id: 'dashboard_ui',
        payload: parsed
      });

      setStatus('IPC frame dispatched successfully!');
      setTimeout(() => setStatus(''), 3000);
    } catch (err) {
      console.error('[GnomeIPC] Dispatch failed:', err);
      setStatus('Invalid JSON payload or WebSocket error.');
    }
  };

  const handleSendCustom = () => dispatchFrame();

  const handleQuickNotification = () => {
    dispatchFrame({
      target: "hud",
      command: "show_notification",
      title: "Quick Test",
      message: "This was triggered from a Quick Action button!"
    });
  };

  const handleToggleAvatar = () => {
    dispatchFrame({
      target: "hud",
      command: "toggle_avatar"
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0, fontSize: '1rem', color: '#f8fafc' }}>Desktop IPC Control</h3>

        {/* Quick Actions Row */}
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={handleQuickNotification}
            style={{ backgroundColor: '#475569', color: '#f8fafc', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}
          >
            🔔 Test Notification
          </button>
          <button
            onClick={handleToggleAvatar}
            style={{ backgroundColor: '#475569', color: '#f8fafc', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}
          >
            👤 Toggle Avatar
          </button>
        </div>
      </div>

      <textarea
        value={payload}
        onChange={(e) => setPayload(e.target.value)}
        style={{ width: '100%', height: '200px', backgroundColor: '#0f172a', color: '#38bdf8', border: '1px solid #334155', borderRadius: '6px', padding: '1rem', fontFamily: 'monospace', fontSize: '0.9rem', boxSizing: 'border-box', resize: 'vertical' }}
      />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '0.85rem', color: status.includes('successfully') ? '#10b981' : '#ef4444' }}>
          {status}
        </span>

        <button
          onClick={handleSendCustom}
          style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.4rem 1.5rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer' }}
        >
          Dispatch Custom JSON
        </button>
      </div>
    </div>
  );
}