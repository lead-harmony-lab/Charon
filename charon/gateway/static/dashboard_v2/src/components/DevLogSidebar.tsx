/**
 * @file src/components/DevLogSidebar.tsx
 * @description
 */
import React, { useState, useMemo, useEffect } from 'react';
import { JournalEntry, EntryType, formatTimestamp } from '../features/journal/types';

// ADDED 'runbook' type color mapping
const TYPE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  observation: { bg: '#1e3a8a20', text: '#60a5fa', border: '#1e3a8a' },
  defect: { bg: '#7f1d1d20', text: '#f87171', border: '#7f1d1d' },
  feature: { bg: '#064e3b20', text: '#34d399', border: '#064e3b' },
  architecture: { bg: '#4c1d9520', text: '#c084fc', border: '#4c1d95' },
  session: { bg: '#854d0e20', text: '#facc15', border: '#854d0e' },
  runbook: { bg: '#14532d20', text: '#4ade80', border: '#14532d' }, // New Build Tab Type
};

type TabType = 'sessions' | 'logs' | 'builds' | 'tickets';

interface DevLogSidebarProps {
  entries: JournalEntry[];
  activeId: string;
  onSelectId: (id: string) => void;
  onStartCreate: (defaultType?: EntryType, templateKey?: string) => void;
}

export function DevLogSidebar({
  entries,
  activeId,
  onSelectId,
  onStartCreate,
}: DevLogSidebarProps) {
  const [activeTab, setActiveTab] = useState<TabType>('sessions');
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');

  // Auto-switch tab when an external selection is made (e.g., from global sidebar or direct link)
  useEffect(() => {
    const activeEntry = entries.find(e => e.id === activeId);
    if (activeEntry) {
      if (activeEntry.type === 'runbook') setActiveTab('builds');
      else if (activeEntry.type === 'session') setActiveTab('sessions');
      else if (activeEntry.status) setActiveTab('tickets');
      else setActiveTab('logs');
    }
  }, [activeId, entries]);

  const treeGroups = useMemo(() => {
    const filtered = entries.filter((item) => {
      // 1. Filter by Active Tab
      let matchesTab = false;
      if (activeTab === 'sessions') matchesTab = item.type === 'session';
      else if (activeTab === 'builds') matchesTab = item.type === 'runbook';
      else if (activeTab === 'tickets') matchesTab = item.status !== null;
      else if (activeTab === 'logs') matchesTab = item.type !== 'session' && item.type !== 'runbook' && !item.status;

      // 2. Filter by Search Query
      const q = searchQuery.toLowerCase();
      const matchesQuery =
        item.title.toLowerCase().includes(q) ||
        item.content.toLowerCase().includes(q) ||
        item.id.toLowerCase().includes(q) ||
        item.linkedArtifacts.some((a) => a.toLowerCase().includes(q));

      // 3. Filter by Dropdown Type
      const matchesType = typeFilter === 'all' || item.type === typeFilter;

      return matchesTab && matchesQuery && matchesType;
    });

    const groups: Record<string, JournalEntry[]> = {};
    filtered.forEach((entry) => {
      const date = new Date(entry.timestamp);
      const groupKey = isNaN(date.getTime())
        ? 'Other'
        : date.toLocaleString(undefined, { year: 'numeric', month: 'long' });
      if (!groups[groupKey]) groups[groupKey] = [];
      groups[groupKey].push(entry);
    });

    return groups;
  }, [entries, activeTab, searchQuery, typeFilter]);

  return (
    <div style={{ width: '280px', backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', display: 'flex', flexDirection: 'column', flexShrink: 0, overflow: 'hidden' }}>

      {/* Header Actions */}
      <div style={{ padding: '1rem', borderBottom: '1px solid #334155', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', color: '#f8fafc' }}>Dev Journal</h3>
        <div style={{ display: 'flex', gap: '0.25rem' }}>
          <button onClick={() => onStartCreate('session', 'standard')} style={{ backgroundColor: '#eab308', color: '#0f172a', border: 'none', padding: '0.25rem 0.5rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.75rem' }}>
            ⚡ Session
          </button>
          <button onClick={() => onStartCreate('observation')} style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.25rem 0.6rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.75rem' }}>
            + New
          </button>
        </div>
      </div>

      {/* Tabs Layout */}
      <div style={{ display: 'flex', borderBottom: '1px solid #334155', backgroundColor: '#0f172a' }}>
        {(['sessions', 'logs', 'builds', 'tickets'] as TabType[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              flex: 1,
              padding: '0.6rem 0',
              backgroundColor: activeTab === tab ? '#1e293b' : 'transparent',
              color: activeTab === tab ? '#38bdf8' : '#64748b',
              border: 'none',
              borderBottom: activeTab === tab ? '2px solid #38bdf8' : '2px solid transparent',
              cursor: 'pointer',
              fontSize: '0.75rem',
              fontWeight: activeTab === tab ? 'bold' : 'normal',
              textTransform: 'capitalize',
              transition: 'all 0.2s ease'
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Filter & Search Panel */}
      <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <input
          type="text"
          placeholder="Search entries..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#e2e8f0', padding: '0.5rem 0.75rem', borderRadius: '6px', fontSize: '0.85rem', boxSizing: 'border-box' }}
        />

        {activeTab !== 'sessions' && activeTab !== 'builds' && (
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#e2e8f0', padding: '0.4rem 0.6rem', borderRadius: '6px', fontSize: '0.8rem', cursor: 'pointer', boxSizing: 'border-box' }}
          >
            <option value="all">All Sub-Types</option>
            <option value="observation">Observation</option>
            <option value="defect">Defect</option>
            <option value="feature">Feature</option>
            <option value="architecture">Architecture</option>
          </select>
        )}
      </div>

      {/* Entry List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '0 1rem 1rem 1rem', overflowY: 'auto', flex: 1 }}>
        {Object.keys(treeGroups).length > 0 ? (
          Object.entries(treeGroups).map(([groupName, groupEntries]) => (
            <div key={groupName} style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                📅 {groupName}
              </span>
              {groupEntries.map((entry) => {
                const isSelected = entry.id === activeId;
                const typeStyle = TYPE_COLORS[entry.type] || TYPE_COLORS.observation;

                return (
                  <button
                    key={entry.id}
                    onClick={() => onSelectId(entry.id)}
                    style={{
                      textAlign: 'left',
                      backgroundColor: isSelected ? '#0f172a' : 'transparent',
                      color: isSelected ? typeStyle.text : '#cbd5e1',
                      border: '1px solid',
                      borderColor: isSelected ? typeStyle.border : 'transparent',
                      borderRadius: '6px',
                      padding: '0.5rem 0.65rem',
                      cursor: 'pointer',
                      fontSize: '0.825rem',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.25rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 'bold', fontSize: '0.75rem', color: '#94a3b8' }}>{entry.id}</span>
                      {entry.type === 'session' && <span style={{ color: '#facc15', fontSize: '0.7rem' }}>⚡ Session</span>}
                      {entry.type === 'runbook' && <span style={{ color: '#4ade80', fontSize: '0.7rem' }}>🛠️ Build</span>}
                      {entry.status && entry.type !== 'session' && entry.type !== 'runbook' && <span style={{ color: '#fb923c', fontSize: '0.7rem' }}>📌 Ticket</span>}
                    </div>
                    <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{entry.title}</span>
                  </button>
                );
              })}
            </div>
          ))
        ) : (
          <p style={{ color: '#64748b', fontSize: '0.85rem', textAlign: 'center', marginTop: '1rem' }}>No entries found.</p>
        )}
      </div>
    </div>
  );
}