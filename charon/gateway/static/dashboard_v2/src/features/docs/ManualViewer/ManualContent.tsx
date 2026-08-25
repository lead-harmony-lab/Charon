/**
 * @file src/features/docs/ManualViewer/ManualContent.tsx
 * @description
 */
import React, { RefObject } from 'react';
import { MarkdownRenderer } from '../../../components/MarkdownRenderer';
import { MarkdownToolbar } from '../../../components/MarkdownToolbar';
import { ManualNode } from '../../../components/treeUtils';

interface ManualContentProps {
  activeNode: ManualNode | null; // Fixed: Allow null
  isEditing: boolean;
  editForm: { title: string; content: string };
  statusMsg: string;
  editTextareaRef: RefObject<HTMLTextAreaElement | null>; // Fixed: Allow HTMLTextAreaElement | null
  setEditForm: (form: { title: string; content: string }) => void;
  setIsEditing: (val: boolean) => void;
  onSaveEdit: () => void;
  onStartEdit: () => void;
  onCopyLink: () => void;
  onAddSubTopic: () => void;
  onDeleteNode: () => void;
  onNavigate: (id: string) => void;
  onOpenLinkModal: () => void;
}

export function ManualContent(props: ManualContentProps) {
  const {
    activeNode, isEditing, editForm, statusMsg, editTextareaRef,
    setEditForm, setIsEditing, onSaveEdit, onStartEdit, onCopyLink,
    onAddSubTopic, onDeleteNode, onNavigate, onOpenLinkModal
  } = props;

  if (!activeNode) {
    return (
      <div style={{ flex: 1, backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '1.5rem', overflowY: 'auto' }}>
        <p style={{ color: '#64748b' }}>Select a topic to view.</p>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '1.5rem', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '1rem', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ color: '#f8fafc', margin: 0 }}>{activeNode.title}</h2>
          <span style={{ fontSize: '0.75rem', color: '#64748b', fontFamily: 'monospace', display: 'block', marginBottom: '0.5rem' }}>ID: {activeNode.id}</span>
          {(activeNode.updatedAt || activeNode.lastChildUpdate) && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              {activeNode.updatedAt && (
                <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                  Edited: {new Date(activeNode.updatedAt).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                </span>
              )}
              {activeNode.lastChildUpdate && (
                <span onClick={() => onNavigate(activeNode.lastChildUpdate!.id)} style={{ fontSize: '0.75rem', color: '#38bdf8', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }} title="Click to view updated child document">
                  ↳ Child '{activeNode.lastChildUpdate.title}' updated {new Date(activeNode.lastChildUpdate.timestamp).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                </span>
              )}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          {statusMsg && <span style={{ fontSize: '0.8rem', color: statusMsg.includes('Error') ? '#ef4444' : statusMsg.includes('successfully') ? '#10b981' : '#38bdf8', marginRight: '0.5rem' }}>{statusMsg}</span>}
          {isEditing ? (
            <>
              <button onClick={onSaveEdit} style={{ backgroundColor: '#10b981', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.85rem' }}>Save</button>
              <button onClick={() => setIsEditing(false)} style={{ backgroundColor: '#334155', color: '#f8fafc', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>Cancel</button>
            </>
          ) : (
            <>
              <button onClick={onCopyLink} style={{ backgroundColor: 'transparent', color: '#cbd5e1', border: '1px solid #475569', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>🔗 Copy Link</button>
              <button onClick={onAddSubTopic} style={{ backgroundColor: '#0f172a', color: '#cbd5e1', border: '1px solid #475569', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>+ Sub-Topic</button>
              <button onClick={onStartEdit} style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.85rem' }}>Edit Section</button>
              <button onClick={onDeleteNode} style={{ backgroundColor: 'transparent', color: '#ef4444', border: '1px solid #ef4444', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>Delete</button>
            </>
          )}
        </div>
      </div>
      {isEditing ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <input type="text" value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', padding: '0.6rem', borderRadius: '4px', fontWeight: 'bold' }} />
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#0f172a', border: '1px solid #334155', borderBottom: 'none', padding: '0.25rem 0.5rem', borderRadius: '6px 6px 0 0' }}>
              <MarkdownToolbar textareaRef={editTextareaRef as RefObject<HTMLTextAreaElement>} content={editForm.content} setContent={(content) => setEditForm({ ...editForm, content })} />
              <button type="button" onClick={onOpenLinkModal} style={{ backgroundColor: '#0284c7', color: '#f8fafc', border: 'none', padding: '0.25rem 0.6rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem', fontWeight: '600' }}>🔗 Link to Topic</button>
            </div>
            <textarea ref={editTextareaRef} value={editForm.content} onChange={(e) => setEditForm({ ...editForm, content: e.target.value })} rows={20} style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#38bdf8', padding: '0.8rem', borderRadius: '0 0 6px 6px', fontFamily: 'monospace', resize: 'vertical' }} />
          </div>
        </div>
      ) : (
        <MarkdownRenderer content={activeNode.content || '*No content provided.*'} onInternalLinkClick={onNavigate} />
      )}
    </div>
  );
}