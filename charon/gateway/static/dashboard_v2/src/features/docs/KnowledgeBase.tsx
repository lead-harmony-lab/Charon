/**
 * @file src/features/docs/KnowledgeBase.tsx
 */
import React, { useState } from 'react';
import { AdrViewer } from './AdrViewer';
import { SpecsViewer } from './SpecsViewer';
import { ManualViewer } from './ManualViewer';

// Added 'manual' to the type
type DocsSubTab = 'adrs' | 'specs' | 'manual';

export function KnowledgeBase() {
  const [activeSubTab, setActiveSubTab] = useState<DocsSubTab>('adrs');

  return (
    <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', height: '100%', boxSizing: 'border-box' }}>
      {/* Top Controls Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e293b', padding: '1rem 1.5rem', borderRadius: '8px', border: '1px solid #334155' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#f8fafc' }}>Knowledge Base</h2>
          <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
            Access system specifications, protocol definitions, Architectural Decision Records (ADRs), and User Manuals.
          </p>
        </div>

        {/* Sub-tab Switcher */}
        <div style={{ display: 'flex', backgroundColor: '#0f172a', borderRadius: '6px', padding: '4px', border: '1px solid #334155' }}>
          <button
            onClick={() => setActiveSubTab('adrs')}
            style={{
              padding: '0.4rem 1rem',
              border: 'none',
              borderRadius: '4px',
              backgroundColor: activeSubTab === 'adrs' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'adrs' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'adrs' ? 'bold' : 'normal',
              cursor: 'pointer',
              fontSize: '0.85rem',
              transition: 'all 0.2s ease'
            }}
          >
            ADR Index
          </button>
          <button
            onClick={() => setActiveSubTab('specs')}
            style={{
              padding: '0.4rem 1rem',
              border: 'none',
              borderRadius: '4px',
              backgroundColor: activeSubTab === 'specs' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'specs' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'specs' ? 'bold' : 'normal',
              cursor: 'pointer',
              fontSize: '0.85rem',
              transition: 'all 0.2s ease'
            }}
          >
            System Specs
          </button>
          <button
            onClick={() => setActiveSubTab('manual')}
            style={{
              padding: '0.4rem 1rem',
              border: 'none',
              borderRadius: '4px',
              backgroundColor: activeSubTab === 'manual' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'manual' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'manual' ? 'bold' : 'normal',
              cursor: 'pointer',
              fontSize: '0.85rem',
              transition: 'all 0.2s ease'
            }}
          >
            User Manual
          </button>
        </div>
      </div>

      {/* Sub-View Content */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {activeSubTab === 'adrs' && <AdrViewer />}
        {activeSubTab === 'specs' && <SpecsViewer />}
        {activeSubTab === 'manual' && <ManualViewer />}
      </div>
    </div>
  );
}