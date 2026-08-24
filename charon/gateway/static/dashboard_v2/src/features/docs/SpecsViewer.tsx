/**
 * @file src/features/docs/SpecsViewer.tsx
 */
import React from 'react';
import { FlatDocumentViewer } from './FlatDocumentViewer';
import { SpecRenderer } from './SpecRenderer';

interface SpecDoc {
  id: string;
  name: string;
  version: string;
  content: string;
  lastUpdated?: string;
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

export function SpecsViewer() {
  return (
    <FlatDocumentViewer<SpecDoc>
      title="System Specifications"
      docType="spec"
      apiPath="/v1/docs/specs"
      extractData={(data) => data.specs}
      filterItem={(spec, query) => {
        const q = query.toLowerCase();
        return spec.name.toLowerCase().includes(q) || spec.id.toLowerCase().includes(q);
      }}
      renderListItem={(spec) => (
        <>
          <div style={{ fontWeight: 'bold' }}>{spec.name}</div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '0.75rem',
              color: '#64748b',
              marginTop: '4px',
            }}
          >
            <span>v{spec.version}</span>
            {spec.lastUpdated && <span>{formatTimestamp(spec.lastUpdated)}</span>}
          </div>
        </>
      )}
      renderViewerHeader={(spec) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h2 style={{ color: '#f8fafc', margin: 0 }}>{spec.name}</h2>
            <span
              style={{
                fontSize: '0.8rem',
                color: '#38bdf8',
                backgroundColor: '#38bdf815',
                padding: '0.15rem 0.4rem',
                borderRadius: '4px',
                border: '1px solid #38bdf840',
              }}
            >
              v{spec.version}
            </span>
          </div>
          {spec.lastUpdated && (
            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
              Last updated: {formatTimestamp(spec.lastUpdated)}
            </span>
          )}
        </div>
      )}
      renderExtraViewerContent={(spec) => <SpecRenderer jsonContent={spec.content} />}
      renderEditForm={(form, updateForm) => (
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            type="text"
            value={form.name || ''}
            onChange={(e) => updateForm({ name: e.target.value })}
            placeholder="Spec Name"
            style={{
              flex: 2,
              backgroundColor: '#0f172a',
              border: '1px solid #334155',
              color: '#f8fafc',
              padding: '0.6rem',
              borderRadius: '4px',
            }}
          />
          <input
            type="text"
            value={form.version || ''}
            onChange={(e) => updateForm({ version: e.target.value })}
            placeholder="Version"
            style={{
              flex: 1,
              backgroundColor: '#0f172a',
              border: '1px solid #334155',
              color: '#38bdf8',
              padding: '0.6rem',
              borderRadius: '4px',
            }}
          />
        </div>
      )}
    />
  );
}