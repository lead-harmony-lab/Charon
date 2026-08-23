import React, { useState, useEffect } from 'react';
import { authFetch } from '../../core/api/client';

export function SystemNotes() {
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState('');

  useEffect(() => {
    async function fetchNotes() {
      try {
        const res = await authFetch('/v1/journal/notes');
        if (res.ok) {
          const data = await res.json();
          setNotes(data.content || '');
        }
      } catch (err) {
        console.error('Failed to load notes', err);
      }
    }
    fetchNotes();
  }, []);

  const handleSave = async () => {
    setStatus('Saving...');
    try {
      const res = await authFetch('/v1/journal/notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: notes }),
      });
      if (res.ok) setStatus('Notes saved!');
      else setStatus('Failed to save notes.');
    } catch (err) {
      setStatus('Error saving notes.');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0, fontSize: '1rem', color: '#f8fafc' }}>Session Architectural Scratchpad</h3>
        <button onClick={handleSave} style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.4rem 1rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer' }}>
          Save Scratchpad
        </button>
      </div>

      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Record architectural decisions, session bugs, or runtime observations..."
        style={{ width: '100%', height: '350px', backgroundColor: '#0f172a', color: '#e2e8f0', border: '1px solid #334155', borderRadius: '6px', padding: '1rem', fontFamily: 'monospace', fontSize: '0.9rem', boxSizing: 'border-box' }}
      />

      {status && <span style={{ fontSize: '0.85rem', color: status.includes('saved!') ? '#10b981' : '#ef4444' }}>{status}</span>}
    </div>
  );
}