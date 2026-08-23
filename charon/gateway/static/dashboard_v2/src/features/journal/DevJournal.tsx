import React, { useState } from 'react';
import { AuditLedger } from './AuditLedger';
import { SystemNotes } from './SystemNotes';

type JournalSubTab = 'audit' | 'notes';

export function DevJournal() {
  const [activeSubTab, setActiveSubTab] = useState<JournalSubTab>('audit');

  return (
    <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', height: '100%', boxSizing: 'border-box' }}>
      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e293b', padding: '1rem 1.5rem', borderRadius: '8px', border: '1px solid #334155' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#f8fafc' }}>Dev Journal</h2>
          <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
            Review global system audit logs and track session engineering notes.
          </p>
        </div>

        {/* Sub-tab Switcher */}
        <div style={{ display: 'flex', backgroundColor: '#0f172a', borderRadius: '6px', padding: '4px', border: '1px solid #334155' }}>
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
          <button
            onClick={() => setActiveSubTab('notes')}
            style={{
              padding: '0.4rem 1rem',
              border: 'none',
              borderRadius: '4px',
              backgroundColor: activeSubTab === 'notes' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'notes' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'notes' ? 'bold' : 'normal',
              cursor: 'pointer',
              fontSize: '0.85rem',
              transition: 'all 0.2s ease'
            }}
          >
            System Notes
          </button>
        </div>
      </div>

      {/* Content View */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {activeSubTab === 'audit' ? <AuditLedger /> : <SystemNotes />}
      </div>
    </div>
  );
}