/**
 * @file src/features/docs/SpecsViewer.tsx
 * @description System Specifications viewer, editor, and creation layout.
 */
import React, { useState, useEffect } from 'react';
import { authFetch } from '../../core/api/client';
import { MarkdownRenderer } from '../../components/MarkdownRenderer';
import { CreateDocModal } from './CreateDocModal';

interface SpecDoc {
  id: string;
  name: string;
  version: string;
  content: string;
}

export function SpecsViewer() {
  const [specs, setSpecs] = useState<SpecDoc[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editForm, setEditForm] = useState<Partial<SpecDoc>>({});
  const [statusMsg, setStatusMsg] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const fetchSpecs = async () => {
    try {
      const res = await authFetch('/v1/docs/specs');
      if (res.ok) {
        const data = await res.json();
        const items: SpecDoc[] = data.specs || [];
        setSpecs(items);
        if (items.length > 0 && !selectedId) setSelectedId(items[0].id);
      }
    } catch (err) {
      console.error('Failed to load system specs', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSpecs();
  }, []);

  const activeSpec = specs.find((s) => s.id === selectedId);

  const handleStartEdit = () => {
    if (!activeSpec) return;
    setEditForm({ ...activeSpec });
    setIsEditing(true);
    setStatusMsg('');
  };

  const handleSave = async () => {
    if (!selectedId) return;
    setStatusMsg('Saving changes...');
    try {
      const res = await authFetch(`/v1/docs/specs/${selectedId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
      });
      if (res.ok) {
        setStatusMsg('Spec updated successfully!');
        setIsEditing(false);
        await fetchSpecs();
      } else {
        setStatusMsg('Failed to update spec.');
      }
    } catch (err) {
      setStatusMsg('Error saving spec.');
    }
  };

  const filteredSpecs = specs.filter((spec) => {
    const q = searchQuery.toLowerCase();
    return (
      spec.name.toLowerCase().includes(q) ||
      spec.id.toLowerCase().includes(q) ||
      spec.content.toLowerCase().includes(q)
    );
  });

  if (loading) return <p style={{ color: '#94a3b8' }}>Loading specification documents...</p>;

  return (
    <div style={{ display: 'flex', gap: '1.5rem', height: '100%' }}>
      {/* Sidebar List */}
      <div style={{ width: '280px', backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: '0.95rem', color: '#f8fafc' }}>System Specifications</h3>
          <button
            onClick={() => setIsModalOpen(true)}
            style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.25rem 0.6rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.75rem' }}
          >
            + New
          </button>
        </div>
        <input
          type="text"
          placeholder="Filter Specs..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#e2e8f0', padding: '0.5rem 0.75rem', borderRadius: '6px', fontSize: '0.85rem', boxSizing: 'border-box' }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', overflowY: 'auto' }}>
          {filteredSpecs.map((spec) => (
            <button
              key={spec.id}
              onClick={() => { setSelectedId(spec.id); setIsEditing(false); }}
              style={{
                textAlign: 'left',
                backgroundColor: spec.id === selectedId ? '#0f172a' : 'transparent',
                color: spec.id === selectedId ? '#38bdf8' : '#cbd5e1',
                border: '1px solid',
                borderColor: spec.id === selectedId ? '#38bdf8' : '#334155',
                borderRadius: '6px',
                padding: '0.75rem',
                cursor: 'pointer',
                fontSize: '0.85rem'
              }}
            >
              <div style={{ fontWeight: 'bold' }}>{spec.name}</div>
              <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '4px' }}>Version {spec.version}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Reader / Editor Panel */}
      <div style={{ flex: 1, backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '1.5rem', overflowY: 'auto' }}>
        {activeSpec ? (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '1rem', marginBottom: '1rem' }}>
              <div>
                <h2 style={{ color: '#f8fafc', margin: 0 }}>{activeSpec.name}</h2>
                <span style={{ fontSize: '0.8rem', color: '#38bdf8' }}>v{activeSpec.version}</span>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                {statusMsg && <span style={{ fontSize: '0.8rem', color: statusMsg.includes('successfully') ? '#10b981' : '#38bdf8' }}>{statusMsg}</span>}
                {isEditing ? (
                  <>
                    <button onClick={handleSave} style={{ backgroundColor: '#10b981', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.85rem' }}>Save</button>
                    <button onClick={() => setIsEditing(false)} style={{ backgroundColor: '#334155', color: '#f8fafc', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>Cancel</button>
                  </>
                ) : (
                  <button onClick={handleStartEdit} style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.85rem' }}>Edit Spec</button>
                )}
              </div>
            </div>

            {isEditing ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <input
                  type="text"
                  value={editForm.name || ''}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  placeholder="Spec Name"
                  style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', padding: '0.6rem', borderRadius: '4px', boxSizing: 'border-box' }}
                />
                <input
                  type="text"
                  value={editForm.version || ''}
                  onChange={(e) => setEditForm({ ...editForm, version: e.target.value })}
                  placeholder="Version"
                  style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#38bdf8', padding: '0.6rem', borderRadius: '4px', boxSizing: 'border-box' }}
                />
                <textarea
                  value={editForm.content || ''}
                  onChange={(e) => setEditForm({ ...editForm, content: e.target.value })}
                  rows={16}
                  style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#38bdf8', padding: '0.8rem', borderRadius: '6px', fontFamily: 'monospace', fontSize: '0.85rem', boxSizing: 'border-box' }}
                />
              </div>
            ) : (
              <MarkdownRenderer content={activeSpec.content} />
            )}
          </div>
        ) : (
          <p style={{ color: '#64748b', fontStyle: 'italic' }}>Select a spec document to view.</p>
        )}
      </div>

      <CreateDocModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        docType="spec"
        onSuccess={fetchSpecs}
      />
    </div>
  );
}