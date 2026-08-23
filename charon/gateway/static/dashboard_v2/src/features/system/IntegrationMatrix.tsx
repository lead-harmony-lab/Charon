import React, { useState } from 'react';
import { SystemdControl } from './SystemdControl';
import { GnomeIPC } from './GnomeIPC';

type MatrixSubTab = 'systemd' | 'gnome';

export function IntegrationMatrix() {
  const [activeSubTab, setActiveSubTab] = useState<MatrixSubTab>('systemd');

  return (
    <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', height: '100%', boxSizing: 'border-box' }}>
      {/* Top Controls Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e293b', padding: '1rem 1.5rem', borderRadius: '8px', border: '1px solid #334155' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#f8fafc' }}>Integration Matrix</h2>
          <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
            Control system background services, systemd units, and desktop IPC extension hooks.
          </p>
        </div>

        {/* Sub-tab Switcher */}
        <div style={{ display: 'flex', backgroundColor: '#0f172a', borderRadius: '6px', padding: '4px', border: '1px solid #334155' }}>
          <button
            onClick={() => setActiveSubTab('systemd')}
            style={{
              padding: '0.4rem 1rem',
              border: 'none',
              borderRadius: '4px',
              backgroundColor: activeSubTab === 'systemd' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'systemd' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'systemd' ? 'bold' : 'normal',
              cursor: 'pointer',
              fontSize: '0.85rem',
              transition: 'all 0.2s ease'
            }}
          >
            Systemd Control
          </button>
          <button
            onClick={() => setActiveSubTab('gnome')}
            style={{
              padding: '0.4rem 1rem',
              border: 'none',
              borderRadius: '4px',
              backgroundColor: activeSubTab === 'gnome' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'gnome' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'gnome' ? 'bold' : 'normal',
              cursor: 'pointer',
              fontSize: '0.85rem',
              transition: 'all 0.2s ease'
            }}
          >
            Desktop IPC
          </button>
        </div>
      </div>

      {/* Sub-View Panel */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {activeSubTab === 'systemd' ? <SystemdControl /> : <GnomeIPC />}
      </div>
    </div>
  );
}