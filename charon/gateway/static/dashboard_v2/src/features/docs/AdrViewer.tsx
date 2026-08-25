/**
 * @file src/features/docs/AdrViewer.tsx
 * @description Architecture Decision Record viewer, editor, and creation layout.
 */
import React from 'react';
import { FlatDocumentViewer } from './FlatDocumentViewer';

interface ADR {
  id: string;
  title: string;
  status: 'ACCEPTED' | 'PROPOSED' | 'DEPRECATED';
  date: string;
  summary: string;
  content: string;
}

/** Formats ISO timestamp string to readable date + time string */
function formatTimestamp(isoString?: string): string {
  if (!isoString) return '';
  try {
    const date = new Date(isoString);
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoString;
  }
}

export function AdrViewer() {
  return (
    <FlatDocumentViewer<ADR>
      title="Decision Records"
      docType="adr"
      apiPath="/v1/docs/adrs"
      baseRoute="/docs/adrs" // NEW: Added baseRoute for deep linking
      extractData={(data) => data.adrs}
      filterItem={(adr, query) => {
        const q = query.toLowerCase();
        return adr.title.toLowerCase().includes(q) ||
               adr.id.toLowerCase().includes(q) ||
               adr.summary.toLowerCase().includes(q) ||
               adr.content.toLowerCase().includes(q);
      }}
      renderListItem={(adr) => (
        <>
          <div style={{ fontWeight: 'bold' }}>{adr.id}: {adr.title}</div>
          <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '4px' }}>
            {adr.status} • {formatTimestamp(adr.date)}
          </div>
        </>
      )}
      renderViewerHeader={(adr) => (
        <>
          <span style={{ fontSize: '0.8rem', padding: '2px 8px', borderRadius: '4px', backgroundColor: '#38bdf820', color: '#38bdf8', border: '1px solid #38bdf8', marginRight: '8px' }}>
            {adr.status}
          </span>
          <span style={{ fontSize: '0.85rem', color: '#64748b' }}>{formatTimestamp(adr.date)}</span>
          <h2 style={{ color: '#f8fafc', margin: '0.5rem 0 0 0' }}>{adr.id}: {adr.title}</h2>
        </>
      )}
      renderEditForm={(form, updateForm) => (
        <>
          <input
            type="text"
            value={form.title || ''}
            onChange={(e) => updateForm({ title: e.target.value })}
            placeholder="ADR Title"
            style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', padding: '0.6rem', borderRadius: '4px', boxSizing: 'border-box' }}
          />
          <input
            type="text"
            value={form.summary || ''}
            onChange={(e) => updateForm({ summary: e.target.value })}
            placeholder="Summary"
            style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#94a3b8', padding: '0.6rem', borderRadius: '4px', boxSizing: 'border-box' }}
          />
        </>
      )}
      renderExtraViewerContent={(adr) => (
        <p style={{ color: '#94a3b8', fontStyle: 'italic', marginBottom: '1.5rem' }}>{adr.summary}</p>
      )}
    />
  );
}