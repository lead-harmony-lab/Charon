/**
 * @file src/features/journal/DevLog.tsx
 * @description Central DevLog component with embedded system manual doc definitions for granular linkage.
 */
import React, { useState, useEffect, useMemo } from 'react';
import { JournalEntry, EntryType } from './types';
import { DocMentionItem } from '../docs/types';
import { DevLogSidebar } from '../../components/DevLogSidebar';
import { DevLogForm } from '../../components/DevLogForm';
import { DevLogView } from '../../components/DevLogView';
import { ManualNode, flattenManualTree } from '../../components/treeUtils';
import { authFetch } from '../../core/api/client';

// We replaced the dummy manual items with placeholder ADRs/Specs.
// The manual items will now be dynamically loaded and injected below.
const STATIC_OTHER_DOCS: DocMentionItem[] = [
  { id: 'ADR-001', title: 'Architecture Decision Records', category: 'adr' },
  { id: 'SPEC-001', title: 'Technical Specifications', category: 'spec' }
];

interface DevLogProps {
  entries: JournalEntry[];
  selectedId: string | null;
  onSelectId: (id: string) => void;
  onSaveEntry: (entry: JournalEntry) => Promise<void>;
  onDeleteEntry: (id: string) => Promise<void>;
}

export function DevLog({ entries, selectedId, onSelectId, onSaveEntry, onDeleteEntry }: DevLogProps) {
  // NEW: Default to the most recent 'session' log if no selectedId is present in the URL
  const activeId = selectedId ||
                   entries.find(e => e.type === 'session')?.id ||
                   (entries.length > 0 ? entries[0].id : '');

  const activeEntry = entries.find((e) => e.id === activeId);

  const [isEditing, setIsEditing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [formData, setFormData] = useState<Partial<JournalEntry>>({});

  // NEW: State to hold the fetched manual tree
  const [manualTree, setManualTree] = useState<ManualNode[]>([]);

  // NEW: Fetch the AST structure on mount
  useEffect(() => {
    async function loadManual() {
      try {
        const res = await authFetch('/v1/docs/manual'); // Fixed: Use authFetch instead of fetch
        if (!res.ok) throw new Error('Network response was not ok');
        const data = await res.json();

        // Handle both raw array OR { tree: [...] } payloads based on backend quirks
        const treeNodes: ManualNode[] = Array.isArray(data) ? data : data.tree || [];
        setManualTree(treeNodes);
      } catch (err) {
        console.error('Failed to load manual tree for mentions:', err);
      }
    }
    loadManual();
  }, []);

  // NEW: Flatten the dynamic tree and merge it with ADR/Spec static docs
  const availableDocs = useMemo(() => {
    return [
      ...STATIC_OTHER_DOCS,
      ...flattenManualTree(manualTree)
    ];
  }, [manualTree]);

  const availableTickets = useMemo(() => {
    return entries.filter((e) => e.status !== null && e.id !== formData.id);
  }, [entries, formData.id]);

  const handleStartCreate = (defaultType: EntryType = 'observation') => {
    const highestNum = entries.reduce((max, e) => {
      const match = e.id.match(/^LOG-(\d+)$/i);
      return match ? Math.max(max, parseInt(match[1], 10)) : max;
    }, 0);

    setFormData({
      id: `LOG-${String(highestNum + 1).padStart(3, '0')}`,
      title: '',
      content: '',
      type: defaultType,
      linkedArtifacts: [],
      linkedTickets: [],
      timestamp: new Date().toISOString(),
    });
    setIsCreating(true);
    setIsEditing(true);
  };

  const handleSave = async () => {
    if (!formData.title?.trim()) return;
    const entryToSave: JournalEntry = {
      id: formData.id || `LOG-${Date.now()}`,
      title: formData.title,
      content: formData.content || '',
      timestamp: formData.timestamp || new Date().toISOString(),
      type: formData.type || 'observation',
      status: formData.status ?? null,
      priority: formData.priority || 'medium',
      linkedArtifacts: formData.linkedArtifacts || [],
      linkedTickets: formData.linkedTickets || [],
      updatedAt: new Date().toISOString(),
    };

    await onSaveEntry(entryToSave);
    onSelectId(entryToSave.id);
    setIsEditing(false);
    setIsCreating(false);
  };

  return (
    <div style={{ display: 'flex', gap: '1.5rem', height: '100%' }}>
      <DevLogSidebar
        entries={entries}
        activeId={activeId}
        onSelectId={(id) => { onSelectId(id); setIsEditing(false); setIsCreating(false); }}
        onStartCreate={handleStartCreate}
      />
      <div style={{ flex: 1, backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '1.5rem', overflowY: 'auto' }}>
        {isEditing ? (
          <DevLogForm
            formData={formData}
            setFormData={setFormData}
            isCreating={isCreating}
            entries={entries}
            availableTickets={availableTickets}
            availableDocs={availableDocs} // Now passes the dynamic array!
            onSave={handleSave}
            onCancel={() => { setIsEditing(false); setIsCreating(false); }}
          />
        ) : activeEntry ? (
          <DevLogView
            entry={activeEntry}
            allEntries={entries}
            availableDocs={availableDocs} // Now passes the dynamic array!
            onEdit={() => { setFormData({ ...activeEntry }); setIsCreating(false); setIsEditing(true); }}
            onDelete={() => onDeleteEntry(activeEntry.id)}
            onSelectId={onSelectId}
          />
        ) : (
          <p style={{ color: '#64748b', textAlign: 'center' }}>Select or create a log entry.</p>
        )}
      </div>
    </div>
  );
}