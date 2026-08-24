/**
 * @file src/features/journal/DevJournal.tsx
 * @description Active human-in-the-loop workspace for architectural notes, task tracking, and doc workflows.
 */
import React, { useState } from 'react';
import { SystemNotes } from './SystemNotes';
import { IssueTracker } from './IssueTracker';
import { DocQueue } from './DocQueue';

// We will expand this as we build out the Tracker and Doc Queue
type JournalSubTab = 'notes' | 'tracker' | 'doc_queue';

export function DevJournal() {
  const [activeSubTab, setActiveSubTab] = useState<JournalSubTab>('notes');

  return (
    <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', height: '100%', boxSizing: 'border-box' }}>
      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e293b', padding: '1rem 1.5rem', borderRadius: '8px', border: '1px solid #334155' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#f8fafc' }}>Dev Journal</h2>
          <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
            System orchestration, architectural scratchpad, and task delegation.
          </p>
        </div>

        {/* Future Sub-tab Switcher - Prepared for the new features */}
        <div style={{ display: 'flex', backgroundColor: '#0f172a', borderRadius: '6px', padding: '4px', border: '1px solid #334155' }}>
          <button
            onClick={() => setActiveSubTab('notes')}
            style={{
              padding: '0.4rem 1rem', border: 'none', borderRadius: '4px',
              backgroundColor: activeSubTab === 'notes' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'notes' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'notes' ? 'bold' : 'normal', cursor: 'pointer', fontSize: '0.85rem'
            }}
          >
            Scratchpad
          </button>
          <button
            onClick={() => setActiveSubTab('tracker')}
            style={{
              padding: '0.4rem 1rem', border: 'none', borderRadius: '4px',
              backgroundColor: activeSubTab === 'tracker' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'tracker' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'tracker' ? 'bold' : 'normal', cursor: 'pointer', fontSize: '0.85rem'
            }}
          >
            Issue Tracker
          </button>
           <button
            onClick={() => setActiveSubTab('doc_queue')}
            style={{
              padding: '0.4rem 1rem', border: 'none', borderRadius: '4px',
              backgroundColor: activeSubTab === 'doc_queue' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'doc_queue' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'doc_queue' ? 'bold' : 'normal', cursor: 'pointer', fontSize: '0.85rem'
            }}
          >
            Doc Queue
          </button>
        </div>
      </div>

      {/* Content View */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {activeSubTab === 'notes' && <SystemNotes />}
        {activeSubTab === 'tracker' && <IssueTracker />}
        {activeSubTab === 'doc_queue' && <DocQueue />}
      </div>
    </div>
  );
}