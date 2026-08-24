/**
 * @file src/features/docs/FlatDocumentViewer.tsx
 * @description A generic viewer/editor for flat lists of documents.
 */
import React, { useState, useEffect } from 'react';
import { authFetch } from '../../core/api/client';
import { MarkdownRenderer } from '../../components/MarkdownRenderer';
import { CreateDocModal } from './CreateDocModal';

interface FlatDocumentViewerProps<T extends { id: string; content: string }> {
  title: string;
  docType: 'adr' | 'spec';
  apiPath: string;
  extractData: (json: any) => T[];
  filterItem: (item: T, query: string) => boolean;
  renderListItem: (item: T) => React.ReactNode;
  renderViewerHeader: (item: T) => React.ReactNode;
  renderEditForm: (form: Partial<T>, updateForm: (updates: Partial<T>) => void) => React.ReactNode;
  renderExtraViewerContent?: (item: T) => React.ReactNode;
}

export function FlatDocumentViewer<T extends { id: string; content: string }>({
  title,
  docType,
  apiPath,
  extractData,
  filterItem,
  renderListItem,
  renderViewerHeader,
  renderEditForm,
  renderExtraViewerContent
}: FlatDocumentViewerProps<T>) {
  const [items, setItems] = useState<T[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editForm, setEditForm] = useState<Partial<T>>({});
  const [statusMsg, setStatusMsg] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const fetchItems = async () => {
    try {
      const res = await authFetch(apiPath);
      if (res.ok) {
        const data = await res.json();
        const extracted = extractData(data) || [];
        setItems(extracted);
        // Only auto-select if we don't have a selection, or if the selection was deleted
        if (extracted.length > 0 && (!selectedId || !extracted.find(i => i.id === selectedId))) {
          setSelectedId(extracted[0].id);
        }
      }
    } catch (err) {
      console.error(`Failed to load ${title}`, err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchItems();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const activeItem = items.find((item) => item.id === selectedId);

  const handleStartEdit = () => {
    if (!activeItem) return;
    setEditForm({ ...activeItem });
    setIsEditing(true);
    setStatusMsg('');
  };

  const handleSave = async () => {
    if (!selectedId) return;
    setStatusMsg('Saving changes...');
    try {
      const res = await authFetch(`${apiPath}/${selectedId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
      });
      if (res.ok) {
        setStatusMsg('Updated successfully!');
        setIsEditing(false);
        await fetchItems();
      } else {
        setStatusMsg('Failed to update.');
      }
    } catch (err) {
      setStatusMsg('Error saving document.');
    }
  };

  const handleDelete = async () => {
    if (!selectedId) return;

    const confirmDelete = window.confirm('Are you sure you want to delete this document? This action cannot be undone.');
    if (!confirmDelete) return;

    setStatusMsg('Deleting...');
    try {
      const res = await authFetch(`${apiPath}/${selectedId}`, {
        method: 'DELETE',
      });

      if (res.ok) {
        setStatusMsg('');
        setSelectedId(''); // Clear selection so the UI falls back to the empty state or auto-selects the first item
        await fetchItems();
      } else {
        setStatusMsg('Failed to delete.');
      }
    } catch (err) {
      setStatusMsg('Error deleting document.');
    }
  };

  const filteredItems = items.filter((item) => filterItem(item, searchQuery));

  if (loading) return <p style={{ color: '#94a3b8' }}>Loading {title.toLowerCase()}...</p>;

  return (
    <div style={{ display: 'flex', gap: '1.5rem', height: '100%' }}>
      {/* Sidebar List */}
      <div style={{ width: '280px', backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: '0.95rem', color: '#f8fafc' }}>{title}</h3>
          <button
            onClick={() => setIsModalOpen(true)}
            style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.25rem 0.6rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.75rem' }}
          >
            + New
          </button>
        </div>
        <input
          type="text"
          placeholder={`Filter ${title}...`}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#e2e8f0', padding: '0.5rem 0.75rem', borderRadius: '6px', fontSize: '0.85rem', boxSizing: 'border-box' }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', overflowY: 'auto' }}>
          {filteredItems.map((item) => (
            <button
              key={item.id}
              onClick={() => { setSelectedId(item.id); setIsEditing(false); }}
              style={{
                textAlign: 'left',
                backgroundColor: item.id === selectedId ? '#0f172a' : 'transparent',
                color: item.id === selectedId ? '#38bdf8' : '#cbd5e1',
                border: '1px solid',
                borderColor: item.id === selectedId ? '#38bdf8' : '#334155',
                borderRadius: '6px',
                padding: '0.75rem',
                cursor: 'pointer',
                fontSize: '0.85rem'
              }}
            >
              {renderListItem(item)}
            </button>
          ))}
          {filteredItems.length === 0 && (
            <p style={{ color: '#64748b', fontSize: '0.85rem', textAlign: 'center', marginTop: '1rem' }}>No items found.</p>
          )}
        </div>
      </div>

      {/* Reader / Editor Panel */}
      <div style={{ flex: 1, backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '1.5rem', overflowY: 'auto' }}>
        {activeItem ? (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '1rem', marginBottom: '1rem' }}>

              <div>{renderViewerHeader(activeItem)}</div>

              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                {statusMsg && <span style={{ fontSize: '0.8rem', color: statusMsg.includes('successfully') ? '#10b981' : (statusMsg.includes('Failed') || statusMsg.includes('Error') ? '#ef4444' : '#38bdf8') }}>{statusMsg}</span>}
                {isEditing ? (
                  <>
                    <button onClick={handleSave} style={{ backgroundColor: '#10b981', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.85rem' }}>Save</button>
                    <button onClick={() => setIsEditing(false)} style={{ backgroundColor: '#334155', color: '#f8fafc', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>Cancel</button>
                  </>
                ) : (
                  <>
                    <button onClick={handleDelete} style={{ backgroundColor: 'transparent', color: '#ef4444', border: '1px solid #ef4444', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>Delete</button>
                    <button onClick={handleStartEdit} style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.85rem' }}>Edit</button>
                  </>
                )}
              </div>
            </div>

            {isEditing ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {renderEditForm(editForm, (updates) => setEditForm((prev) => ({ ...prev, ...updates })))}
                <textarea
                  value={editForm.content || ''}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, content: e.target.value }))}
                  rows={16}
                  style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#38bdf8', padding: '0.8rem', borderRadius: '6px', fontFamily: 'monospace', fontSize: '0.85rem', boxSizing: 'border-box' }}
                />
              </div>
            ) : (
              <>
                {renderExtraViewerContent && renderExtraViewerContent(activeItem)}
                {docType === 'adr' && <MarkdownRenderer content={activeItem.content} />}
              </>
            )}
          </div>
        ) : (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <p style={{ color: '#64748b', fontStyle: 'italic' }}>Select an item to view details or create a new one.</p>
          </div>
        )}
      </div>

      <CreateDocModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        docType={docType}
        onSuccess={fetchItems}
      />
    </div>
  );
}