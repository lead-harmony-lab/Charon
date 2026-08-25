/**
 * @file src/components/DevLogView.tsx
 * @description View component for individual DevLog journal entries with linked documentation support.
 */
import React from 'react';
import { JournalEntry, EntryType, DocMentionItem, formatTimestamp } from '../features/journal/types';
import { MarkdownRenderer } from './MarkdownRenderer';

const TYPE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  observation: { bg: '#1e3a8a20', text: '#60a5fa', border: '#1e3a8a' },
  defect: { bg: '#7f1d1d20', text: '#f87171', border: '#7f1d1d' },
  feature: { bg: '#064e3b20', text: '#34d399', border: '#064e3b' },
  architecture: { bg: '#4c1d9520', text: '#c084fc', border: '#4c1d95' },
  session: { bg: '#854d0e20', text: '#facc15', border: '#854d0e' },
  runbook: { bg: '#14532d20', text: '#4ade80', border: '#14532d' }, // NEW
};

export interface DevLogViewProps {
  entry: JournalEntry;
  allEntries: JournalEntry[];
  availableDocs?: DocMentionItem[];
  onEdit: () => void;
  onDelete: () => void | Promise<void>;
  onSelectId: (id: string) => void;
  onSelectDocId?: (docId: string) => void;
}

export function DevLogView({
  entry,
  allEntries,
  availableDocs = [],
  onEdit,
  onDelete,
  onSelectId,
  onSelectDocId,
}: DevLogViewProps) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #334155', paddingBottom: '1rem', marginBottom: '1.25rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.4rem' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 'bold', fontFamily: 'monospace', color: '#38bdf8' }}>{entry.id}</span>
            <span style={{ fontSize: '0.7rem', padding: '2px 8px', borderRadius: '4px', fontWeight: 'bold', backgroundColor: TYPE_COLORS[entry.type].bg, color: TYPE_COLORS[entry.type].text, border: `1px solid ${TYPE_COLORS[entry.type].border}`, textTransform: 'uppercase' }}>
              {entry.type}
            </span>
            {entry.status && (
              <span style={{ fontSize: '0.7rem', padding: '2px 8px', borderRadius: '4px', fontWeight: 'bold', backgroundColor: '#334155', color: '#f8fafc' }}>
                Status: {entry.status.replace('_', ' ').toUpperCase()}
              </span>
            )}
          </div>
          <h2 style={{ color: '#f8fafc', margin: 0 }}>{entry.title}</h2>
          <span style={{ fontSize: '0.75rem', color: '#64748b', display: 'block', marginTop: '0.25rem' }}>
            Posted {formatTimestamp(entry.timestamp)}
          </span>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button onClick={onDelete} style={{ backgroundColor: 'transparent', color: '#ef4444', border: '1px solid #ef4444', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>Delete</button>
          <button onClick={onEdit} style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.85rem' }}>Edit Post</button>
        </div>
      </div>

      {entry.linkedTickets && entry.linkedTickets.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', backgroundColor: '#0f172a', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid #854d0e' }}>
          <span style={{ fontSize: '0.75rem', color: '#facc15', fontWeight: 'bold' }}>Linked Board Tickets:</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
            {entry.linkedTickets.map((ticketId) => {
              const linkedTicket = allEntries.find((e) => e.id === ticketId);
              return (
                <button
                  key={ticketId}
                  onClick={() => onSelectId(ticketId)}
                  title="Click to view ticket"
                  style={{ backgroundColor: '#1e293b', color: '#facc15', border: '1px solid #854d0e', padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', fontFamily: 'monospace', cursor: 'pointer' }}
                >
                  📌 [{ticketId}] {linkedTicket ? linkedTicket.title : ticketId}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {entry.linkedDocs && entry.linkedDocs.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', backgroundColor: '#0f172a', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid #4c1d95' }}>
          <span style={{ fontSize: '0.75rem', color: '#c084fc', fontWeight: 'bold' }}>Linked Documentation & Specs:</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
            {entry.linkedDocs.map((docId) => {
              const docMatch = availableDocs.find((d) => d.id === docId);
              return (
                <button
                  key={docId}
                  onClick={() => onSelectDocId?.(docId)}
                  title="Click to view document"
                  style={{ backgroundColor: '#1e293b', color: '#c084fc', border: '1px solid #4c1d95', padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', fontFamily: 'monospace', cursor: onSelectDocId ? 'pointer' : 'default' }}
                >
                  📄 [{docId}] {docMatch ? docMatch.title : docId}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {entry.linkedArtifacts && entry.linkedArtifacts.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem', backgroundColor: '#0f172a', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid #334155' }}>
          <span style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 'bold' }}>Linked Artifacts:</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
            {entry.linkedArtifacts.map((art, idx) => (
              <span key={idx} style={{ backgroundColor: '#1e293b', color: '#38bdf8', border: '1px solid #0284c7', padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', fontFamily: 'monospace' }}>
                🔗 {art}
              </span>
            ))}
          </div>
        </div>
      )}

      <MarkdownRenderer
        content={entry.content || '*No content provided.*'}
        onInternalLinkClick={onSelectId}
        onDocLinkClick={onSelectDocId}
      />
    </div>
  );
}