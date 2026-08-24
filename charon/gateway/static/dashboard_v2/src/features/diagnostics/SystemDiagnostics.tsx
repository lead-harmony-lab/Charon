/**
 * @file src/features/diagnostics/SystemDiagnostics.tsx
 * @description Consolidated dashboard for real-time AI telemetry and system audit logs.
 */
import React, { useState } from 'react';
import { BlackboardObserver } from './BlackboardObserver';
import { AuditLedger } from './AuditLedger';

type DiagnosticsSubTab = 'telemetry' | 'audit';

export function SystemDiagnostics() {
  const [activeSubTab, setActiveSubTab] = useState<DiagnosticsSubTab>('telemetry');

  return (
    <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', height: '100%', boxSizing: 'border-box' }}>
      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e293b', padding: '1rem 1.5rem', borderRadius: '8px', border: '1px solid #334155' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#f8fafc' }}>System Diagnostics</h2>
          <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
            Monitor real-time agent execution and review historical system logs.
          </p>
        </div>

        {/* Sub-tab Switcher */}
        <div style={{ display: 'flex', backgroundColor: '#0f172a', borderRadius: '6px', padding: '4px', border: '1px solid #334155' }}>
          <button
            onClick={() => setActiveSubTab('telemetry')}
            style={{
              padding: '0.4rem 1rem',
              border: 'none',
              borderRadius: '4px',
              backgroundColor: activeSubTab === 'telemetry' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'telemetry' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'telemetry' ? 'bold' : 'normal',
              cursor: 'pointer',
              fontSize: '0.85rem',
              transition: 'all 0.2s ease'
            }}
          >
            Blackboard Telemetry
          </button>
          <button
            onClick={() => setActiveSubTab('audit')}
            style={{
              padding: '0.4rem 1rem',
              border: 'none',
              borderRadius: '4px',
              backgroundColor: activeSubTab === 'audit' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'audit' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'audit' ? 'bold' : 'normal',
              cursor: 'pointer',
              fontSize: '0.85rem',
              transition: 'all 0.2s ease'
            }}
          >
            Audit Ledger
          </button>
        </div>
      </div>

      {/* Content View */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {activeSubTab === 'telemetry' ? (
          <div style={{ height: '100%', margin: '-1.5rem' }}> {/* Offset Blackboard's internal padding */}
            <BlackboardObserver />
          </div>
        ) : (
          <AuditLedger />
        )}
      </div>
    </div>
  );
}