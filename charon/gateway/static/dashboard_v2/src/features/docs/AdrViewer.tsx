/**
 * @file src/features/docs/AdrViewer.tsx
 * @description Architecture Decision Record viewer, editor, and creation layout.
 */
import React, { useState, useEffect } from 'react';
import { authFetch } from '../../core/api/client';
import { MarkdownRenderer } from '../../components/MarkdownRenderer';
import { CreateDocModal } from './CreateDocModal';

interface ADR {
  id: string;
  title: string;
  status: 'ACCEPTED' | 'PROPOSED' | 'DEPRECATED';
  date: string;
  summary: string;
  content: string;
}

export function AdrViewer() {
  const [adrs, setAdrs] = useState<ADR[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editForm, setEditForm] = useState<Partial<ADR>>({});
  const [statusMsg, setStatusMsg] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const fetchAdrs = async () => {
    try {
      const res = await authFetch('/v1/docs/adrs');
      if (res.ok) {
        const data = await res.json();
        const items: ADR[] = data.adrs || [];
        setAdrs(items);
        if (items.length > 0 && !selectedId) setSelectedId(items[0].id);
      }
    } catch (err) {
      console.error('Failed to load ADRs', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAdrs();
  }, []);

  const activeAdr = adrs.find((item) => item.id === selectedId);

  const handleStartEdit = () => {
    if (!activeAdr) return;
    setEditForm({ ...activeAdr });
    setIsEditing(true);
    setStatusMsg('');
  };

  const handleSave = async () => {
    if (!selectedId) return;
    setStatusMsg('Saving changes...');
    try {
      const res = await authFetch(`/v1/docs/adrs/${selectedId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
      });
      if (res.ok) {
        setStatusMsg('ADR updated successfully!');
        setIsEditing(false);
        await fetchAdrs();
      } else {
        setStatusMsg('Failed to update ADR.');
      }
    } catch (err) {
      setStatusMsg('Error saving document.');
    }
  };

  const filteredAdrs = adrs.filter((adr) => {
    const q = searchQuery.toLowerCase();
    return (
      adr.title.toLowerCase().includes(q) ||
      adr.id.toLowerCase().includes(q) ||
      adr.summary.toLowerCase().includes(q) ||
      adr.content.toLowerCase().includes(q)
    );
  });

  if (loading) return <p style={{ color: '#94a3b8' }}>Loading decision records...</p>;

  return (
    <div style={{ display: 'flex', gap: '1.5rem', height: '100%' }}>
      {/* Sidebar List */}
      <div style={{ width: '280px', backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: '0.95rem', color: '#f8fafc' }}>Decision Records</h3>
          <button
            onClick={() => setIsModalOpen(true)}
            style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.25rem 0.6rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.75rem' }}
          >
            + New
          </button>
        </div>
        <input
          type="text"
          placeholder="Filter ADRs..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#e2e8f0', padding: '0.5rem 0.75rem', borderRadius: '6px', fontSize: '0.85rem', boxSizing: 'border-box' }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', overflowY: 'auto' }}>
          {filteredAdrs.map((adr) => (
            <button
              key={adr.id}
              onClick={() => { setSelectedId(adr.id); setIsEditing(false); }}
              style={{
                textAlign: 'left',
                backgroundColor: adr.id === selectedId ? '#0f172a' : 'transparent',
                color: adr.id === selectedId ? '#38bdf8' : '#cbd5e1',
                border: '1px solid',
                borderColor: adr.id === selectedId ? '#38bdf8' : '#334155',
                borderRadius: '6px',
                padding: '0.75rem',
                cursor: 'pointer',
                fontSize: '0.85rem'
              }}
            >
              <div style={{ fontWeight: 'bold' }}>{adr.id}: {adr.title}</div>
              <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '4px' }}>{adr.status} • {adr.date}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Reader / Editor Panel */}
      <div style={{ flex: 1, backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '1.5rem', overflowY: 'auto' }}>
        {activeAdr ? (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '1rem', marginBottom: '1rem' }}>
              <div>
                <span style={{ fontSize: '0.8rem', padding: '2px 8px', borderRadius: '4px', backgroundColor: '#38bdf820', color: '#38bdf8', border: '1px solid #38bdf8', marginRight: '8px' }}>
                  {activeAdr.status}
                </span>
                <span style={{ fontSize: '0.85rem', color: '#64748b' }}>{activeAdr.date}</span>
                <h2 style={{ color: '#f8fafc', margin: '0.5rem 0 0 0' }}>{activeAdr.id}: {activeAdr.title}</h2>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                {statusMsg && <span style={{ fontSize: '0.8rem', color: statusMsg.includes('successfully') ? '#10b981' : '#38bdf8' }}>{statusMsg}</span>}
                {isEditing ? (
                  <>
                    <button onClick={handleSave} style={{ backgroundColor: '#10b981', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.85rem' }}>Save</button>
                    <button onClick={() => setIsEditing(false)} style={{ backgroundColor: '#334155', color: '#f8fafc', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>Cancel</button>
                  </>
                ) : (
                  <button onClick={handleStartEdit} style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.85rem' }}>Edit ADR</button>
                )}
              </div>
            </div>

            {isEditing ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <input
                  type="text"
                  value={editForm.title || ''}
                  onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                  placeholder="ADR Title"
                  style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', padding: '0.6rem', borderRadius: '4px', boxSizing: 'border-box' }}
                />
                <input
                  type="text"
                  value={editForm.summary || ''}
                  onChange={(e) => setEditForm({ ...editForm, summary: e.target.value })}
                  placeholder="Summary"
                  style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#94a3b8', padding: '0.6rem', borderRadius: '4px', boxSizing: 'border-box' }}
                />
                <textarea
                  value={editForm.content || ''}
                  onChange={(e) => setEditForm({ ...editForm, content: e.target.value })}
                  rows={16}
                  style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#38bdf8', padding: '0.8rem', borderRadius: '6px', fontFamily: 'monospace', fontSize: '0.85rem', boxSizing: 'border-box' }}
                />
              </div>
            ) : (
              <>
                <p style={{ color: '#94a3b8', fontStyle: 'italic', marginBottom: '1.5rem' }}>{activeAdr.summary}</p>
                <MarkdownRenderer content={activeAdr.content} />
              </>
            )}
          </div>
        ) : (
          <p style={{ color: '#64748b', fontStyle: 'italic' }}>Select an ADR to view details.</p>
        )}
      </div>

      <CreateDocModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        docType="adr"
        onSuccess={fetchAdrs}
      />
    </div>
  );
}