import React, { useState } from 'react';
import { SkillMatrix } from './SkillMatrix';
import { PromptEditor } from './PromptEditor';

type StudioSubTab = 'matrix' | 'prompts';

export function AgentStudio() {
  const [activeSubTab, setActiveSubTab] = useState<StudioSubTab>('matrix');

  return (
    <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', height: '100%', boxSizing: 'border-box' }}>
      {/* Top Controls Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e293b', padding: '1rem 1.5rem', borderRadius: '8px', border: '1px solid #334155' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#f8fafc' }}>Agent Studio</h2>
          <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
            Manage agent priority weights, active tools, and core prompts.
          </p>
        </div>

        {/* Sub-tab Switcher */}
        <div style={{ display: 'flex', backgroundColor: '#0f172a', borderRadius: '6px', padding: '4px', border: '1px solid #334155' }}>
          <button
            onClick={() => setActiveSubTab('matrix')}
            style={{
              padding: '0.4rem 1rem',
              border: 'none',
              borderRadius: '4px',
              backgroundColor: activeSubTab === 'matrix' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'matrix' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'matrix' ? 'bold' : 'normal',
              cursor: 'pointer',
              fontSize: '0.85rem',
              transition: 'all 0.2s ease'
            }}
          >
            Skill Matrix
          </button>
          <button
            onClick={() => setActiveSubTab('prompts')}
            style={{
              padding: '0.4rem 1rem',
              border: 'none',
              borderRadius: '4px',
              backgroundColor: activeSubTab === 'prompts' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'prompts' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'prompts' ? 'bold' : 'normal',
              cursor: 'pointer',
              fontSize: '0.85rem',
              transition: 'all 0.2s ease'
            }}
          >
            Prompt Editor
          </button>
        </div>
      </div>

      {/* Sub-View Panel */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {activeSubTab === 'matrix' ? <SkillMatrix /> : <PromptEditor />}
      </div>
    </div>
  );
}