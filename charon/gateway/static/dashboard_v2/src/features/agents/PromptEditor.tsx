import React, { useState, useEffect } from 'react';
import { authFetch } from '../../core/api/client';

export function PromptEditor() {
  const [agents, setAgents] = useState<string[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string>('');
  const [prompt, setPrompt] = useState<string>('');
  const [status, setStatus] = useState<string>('');

  useEffect(() => {
    async function loadAgents() {
      try {
        const res = await authFetch('/v1/router/agents');
        if (res.ok) {
          const data = await res.json();
          const keys = Object.keys(data.agents || {});
          setAgents(keys);
          if (keys.length > 0) setSelectedAgent(keys[0]);
        }
      } catch (err) {
        console.error('Failed to load agents for prompt editor', err);
      }
    }
    loadAgents();
  }, []);

  useEffect(() => {
    if (!selectedAgent) return;
    async function loadPrompt() {
      try {
        const res = await authFetch(`/v1/router/agents/${selectedAgent}/prompt`);
        if (res.ok) {
          const data = await res.json();
          setPrompt(data.system_prompt || '');
        }
      } catch (err) {
        setPrompt('');
      }
    }
    loadPrompt();
  }, [selectedAgent]);

  const handleSave = async () => {
    setStatus('Saving...');
    try {
      const res = await authFetch(`/v1/router/agents/${selectedAgent}/prompt`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_prompt: prompt }),
      });
      if (res.ok) setStatus('Prompt saved successfully!');
      else setStatus('Failed to save prompt.');
    } catch (err) {
      setStatus('Error saving prompt.');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', backgroundColor: '#1e293b', padding: '1.25rem', borderRadius: '8px', border: '1px solid #334155' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <label style={{ color: '#f8fafc', fontSize: '0.9rem', fontWeight: 'bold' }}>
          Select Agent System Prompt:
          <select
            value={selectedAgent}
            onChange={(e) => setSelectedAgent(e.target.value)}
            style={{ marginLeft: '10px', backgroundColor: '#0f172a', color: '#38bdf8', border: '1px solid #334155', padding: '0.4rem 0.8rem', borderRadius: '4px' }}
          >
            {agents.map((id) => (
              <option key={id} value={id}>{id}</option>
            ))}
          </select>
        </label>

        <button
          onClick={handleSave}
          style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.4rem 1rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer' }}
        >
          Save System Prompt
        </button>
      </div>

      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Enter agent system instructions..."
        style={{ width: '100%', height: '300px', backgroundColor: '#0f172a', color: '#e2e8f0', border: '1px solid #334155', borderRadius: '6px', padding: '1rem', fontFamily: 'monospace', fontSize: '0.9rem', boxSizing: 'border-box' }}
      />

      {status && <span style={{ fontSize: '0.85rem', color: status.includes('successfully') ? '#10b981' : '#ef4444' }}>{status}</span>}
    </div>
  );
}