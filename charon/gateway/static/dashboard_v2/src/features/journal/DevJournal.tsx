/**
 * @file src/features/journal/DevJournal.tsx
 * @description
 */
import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DevLog } from './DevLog';
import { IssueTracker } from './IssueTracker';
import { DocQueue } from './DocQueue';
import { JournalEntry, TicketStatus } from './types';
import { authFetch } from '../../core/api/client';

type JournalSubTab = 'log' | 'tracker' | 'doc_queue';

export function DevJournal() {
  // Replace local state with URL search parameters
  const [searchParams, setSearchParams] = useSearchParams();

  // Derive state from the URL, providing sensible defaults
  const activeSubTab = (searchParams.get('tab') as JournalSubTab) || 'log';
  const selectedLogId = searchParams.get('logId');

  const [entries, setEntries] = useState<JournalEntry[]>([]);

  // Helpers to update the URL without blowing away other params
  const setActiveSubTab = (tab: JournalSubTab) => {
    setSearchParams(
      (prev) => {
        prev.set('tab', tab);
        return prev;
      },
      { replace: true } // Prevents pushing a massive amount of history state when just clicking tabs
    );
  };

  const setSelectedLogId = (id: string | null) => {
    setSearchParams(
      (prev) => {
        if (id) {
          prev.set('logId', id);
        } else {
          prev.delete('logId');
        }
        return prev;
      }
    );
  };

  const fetchEntries = async () => {
    try {
      const res = await authFetch('/v1/journal/entries');
      if (res.ok) {
        const data = await res.json();
        if (data.entries && Array.isArray(data.entries)) {
          setEntries(data.entries);
        }
      }
    } catch (err) {
      console.error('Failed to load journal entries', err);
    }
  };

  useEffect(() => {
    fetchEntries();
  }, []);

  const handleSaveEntry = async (entry: JournalEntry) => {
    const previousEntries = entries;

    setEntries((prev) => {
      const exists = prev.some((e) => e.id === entry.id);
      return exists ? prev.map((e) => (e.id === entry.id ? entry : e)) : [entry, ...prev];
    });

    try {
      const res = await authFetch('/v1/journal/entries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(entry),
      });

      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    } catch (err) {
      console.error('Failed to save entry to backend', err);
      setEntries(previousEntries);
    }
  };

  const handleDeleteEntry = async (id: string) => {
    if (!window.confirm(`Delete post ${id}?`)) return;

    const previousEntries = entries;
    const remainingEntries = entries.filter((e) => e.id !== id);

    setEntries(remainingEntries);

    if (selectedLogId === id) {
      setSelectedLogId(remainingEntries.length > 0 ? remainingEntries[0].id : null);
    }

    try {
      const res = await authFetch(`/v1/journal/entries/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    } catch (err) {
      console.error('Failed to delete entry', err);
      setEntries(previousEntries);
      setSelectedLogId(id);
    }
  };

  const handleUpdateStatus = async (id: string, newStatus: TicketStatus) => {
    let targetEntry: JournalEntry | undefined;

    setEntries((prev) => {
      targetEntry = prev.find((e) => e.id === id);
      return prev;
    });

    if (!targetEntry) return;

    const updatedEntry = { ...targetEntry, status: newStatus };
    await handleSaveEntry(updatedEntry);
  };

  return (
    <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', height: '100%', boxSizing: 'border-box' }}>
      {/* Header & Sub-tab Navigation */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e293b', padding: '1rem 1.5rem', borderRadius: '8px', border: '1px solid #334155' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#f8fafc' }}>Dev Journal</h2>
          <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
            Chronological system log, architectural telemetry, and issue tracking.
          </p>
        </div>

        <div style={{ display: 'flex', backgroundColor: '#0f172a', borderRadius: '6px', padding: '4px', border: '1px solid #334155' }}>
          <button
            onClick={() => setActiveSubTab('log')}
            style={{
              padding: '0.4rem 1rem', border: 'none', borderRadius: '4px',
              backgroundColor: activeSubTab === 'log' ? '#38bdf8' : 'transparent',
              color: activeSubTab === 'log' ? '#0f172a' : '#94a3b8',
              fontWeight: activeSubTab === 'log' ? 'bold' : 'normal', cursor: 'pointer', fontSize: '0.85rem'
            }}
          >
            Dev Log
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
            Issue Tracker ({entries.filter((e) => e.status !== null).length})
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

      {/* Main Content Area */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {activeSubTab === 'log' && (
          <DevLog
            entries={entries}
            selectedId={selectedLogId}
            onSelectId={setSelectedLogId}
            onSaveEntry={handleSaveEntry}
            onDeleteEntry={handleDeleteEntry}
          />
        )}
        {activeSubTab === 'tracker' && (
          <IssueTracker
            entries={entries}
            onUpdateStatus={handleUpdateStatus}
            onSelectEntry={(id) => {
              setSelectedLogId(id);
              setActiveSubTab('log');
            }}
          />
        )}
        {activeSubTab === 'doc_queue' && <DocQueue />}
      </div>
    </div>
  );
}