/**
 * @file src/features/docs/ManualViewer.tsx
 * @description A recursive, multi-level Markdown viewer and editor for system manuals with Drag and Drop, Backend API Integration, internal linking, and node search filtering.
 */
import React, { useState, useEffect, useMemo, DragEvent, useRef } from 'react';
import { MarkdownRenderer } from '../../components/MarkdownRenderer';
import { authFetch } from '../../core/api/client';
import { MarkdownToolbar } from '../../components/MarkdownToolbar';
import {
  ManualNode,
  findNodeById,
  findNodePath,
  filterTree,
  updateTree,
  addNodeToTree,
  isDescendant,
  removeNode,
  insertNode
} from '../../components/treeUtils';

const INITIAL_TREE: ManualNode[] = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    content: `## Charon Control: Getting Started\n\nWelcome to Charon Control. This system orchestrates agents, diagnostics, and integrations via a unified daemon connection. See [Backend Orchestrator](#backend-orchestrator) for more info.`
  },
  {
    id: 'backend-orchestrator',
    title: 'Backend Orchestrator',
    content: `## Backend Orchestrator\n\nThe central rust/node daemon that manages state.`,
    children: [
      {
        id: 'websocket-protocol',
        title: 'WebSocket Protocol',
        content: `### WebSocket Protocol\n\nAll real-time communication flows through the centralized WS router.`,
      }
    ]
  },
  {
    id: 'desktop-avatar',
    title: 'Desktop Avatar',
    content: `## Desktop Avatar\n\nThe primary user-facing frontend.`,
    children: []
  }
];

export function ManualViewer() {
  const [manualTree, setManualTree] = useState<ManualNode[]>(INITIAL_TREE);
  const [selectedId, setSelectedId] = useState<string>(INITIAL_TREE[0].id);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set(['backend-orchestrator', 'desktop-avatar']));

  // Search State
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Edit & Create State
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editForm, setEditForm] = useState<{ title: string; content: string }>({ title: '', content: '' });
  const [statusMsg, setStatusMsg] = useState<string>('');
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createTargetParentId, setCreateTargetParentId] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState('');

  // Markdown Editor Ref
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);

  // Drag & Drop State
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [dropPosition, setDropPosition] = useState<'before' | 'after' | 'inside' | null>(null);

  const activeNode = findNodeById(manualTree, selectedId);

  // Compute filtered tree based on active search query
  const filteredTree = useMemo(() => {
    return filterTree(manualTree, searchQuery);
  }, [manualTree, searchQuery]);

  // Auto-expand all parent nodes in search results so matches are visible
  useEffect(() => {
    if (!searchQuery.trim()) return;

    const collectParentIds = (nodes: ManualNode[]): string[] => {
      let ids: string[] = [];
      for (const node of nodes) {
        if (node.children && node.children.length > 0) {
          ids.push(node.id);
          ids = ids.concat(collectParentIds(node.children));
        }
      }
      return ids;
    };

    const matchedParentIds = collectParentIds(filteredTree);
    setExpandedIds(prev => new Set([...prev, ...matchedParentIds]));
  }, [searchQuery, filteredTree]);

  // --- REST API Persistence Synchronization ---

  const loadManualTree = async () => {
    try {
      const response = await authFetch('/v1/docs/manual');
      const rawText = await response.text();

      if (!response.ok) {
        console.error(`HTTP Error ${response.status}:`, rawText);
        throw new Error('Failed to fetch manual tree');
      }

      let data;
      try {
        data = JSON.parse(rawText);
      } catch (parseError) {
        console.error("Failed to parse this raw response as JSON:", rawText);
        throw parseError;
      }

      if (data.tree && Array.isArray(data.tree) && data.tree.length > 0) {
        setManualTree(data.tree);

        // Ensure our currently selected node still exists in the fresh tree
        if (!findNodeById(data.tree, selectedId)) {
          setSelectedId(data.tree[0].id);
        }
      }
    } catch (err) {
      console.error("Failed to fetch manual tree:", err);
      setStatusMsg('Error: Failed to load manual data.');
    }
  };

  const saveTreeToBackend = async (treeToSave: ManualNode[]) => {
    setStatusMsg('Saving changes...');
    try {
      const response = await authFetch('/v1/docs/manual', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(treeToSave)
      });

      if (!response.ok) throw new Error('Failed to save manual tree');

      // Fetch the freshly stamped tree back from the server
      await loadManualTree();

      setStatusMsg('Section updated successfully!');
    } catch (err) {
      console.error("Failed to save tree via REST:", err);
      setStatusMsg('Error: Failed to save changes.');
    }
  };

  // Initial load on mount
  useEffect(() => {
    loadManualTree();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // --- Drag & Drop Handlers ---

  const handleDragStart = (e: DragEvent<HTMLDivElement>, id: string) => {
    e.dataTransfer.setData('text/plain', id);
    e.dataTransfer.effectAllowed = 'move';
    setDraggedId(id);
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>, targetId: string) => {
    e.preventDefault();
    if (!draggedId || draggedId === targetId || isDescendant(manualTree, draggedId, targetId)) {
      setDropPosition(null);
      setDragOverId(null);
      return;
    }

    setDragOverId(targetId);

    const rect = e.currentTarget.getBoundingClientRect();
    const relativeY = e.clientY - rect.top;

    if (relativeY < rect.height * 0.25) {
      setDropPosition('before');
    } else if (relativeY > rect.height * 0.75) {
      setDropPosition('after');
    } else {
      setDropPosition('inside');
    }
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    setDragOverId(null);
    setDropPosition(null);
  };

  const handleDrop = async (e: DragEvent<HTMLDivElement>, targetId: string) => {
    e.preventDefault();
    if (!draggedId || !dropPosition || draggedId === targetId || isDescendant(manualTree, draggedId, targetId)) {
      setDraggedId(null);
      setDragOverId(null);
      setDropPosition(null);
      return;
    }

    const { newTree, removedNode } = removeNode(manualTree, draggedId);

    if (removedNode) {
      const finalTree = insertNode(newTree, targetId, removedNode, dropPosition);
      setManualTree(finalTree);

      if (dropPosition === 'inside') {
        setExpandedIds(prev => new Set(prev).add(targetId));
      }

      await saveTreeToBackend(finalTree);
    }

    setDraggedId(null);
    setDragOverId(null);
    setDropPosition(null);
  };

  const handleDragEnd = () => {
    setDraggedId(null);
    setDragOverId(null);
    setDropPosition(null);
  };

  // --- Standard Handlers (Click, Edit, Create, Delete, Navigate) ---

  const toggleExpand = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleStartEdit = () => {
    if (!activeNode) return;
    setEditForm({ title: activeNode.title, content: activeNode.content || '' });
    setIsEditing(true);
    setStatusMsg('');
  };

  const handleSaveEdit = async () => {
    if (!selectedId) return;
    setStatusMsg('Saving changes...');

    const updated = updateTree(manualTree, selectedId, { title: editForm.title, content: editForm.content });
    setManualTree(updated);

    await saveTreeToBackend(updated);
    setIsEditing(false);
  };

  const handleCreateNode = async () => {
    if (!newTitle.trim()) return;
    const generatedId = newTitle.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
    const newNode: ManualNode = {
      id: generatedId,
      title: newTitle.trim(),
      content: `## ${newTitle.trim()}\n\nStart writing documentation here...`,
      children: []
    };

    const updated = addNodeToTree(manualTree, createTargetParentId, newNode);
    setManualTree(updated);

    if (createTargetParentId) setExpandedIds(prev => new Set(prev).add(createTargetParentId));
    setSelectedId(generatedId);
    setIsCreateModalOpen(false);
    setIsEditing(false);

    await saveTreeToBackend(updated);
  };

  const handleDeleteNode = async () => {
    if (!activeNode) return;

    // Confirm deletion to prevent accidental data loss
    if (!window.confirm(`Are you sure you want to delete "${activeNode.title}"? This will also delete any sub-topics.`)) {
      return;
    }

    setStatusMsg('Deleting...');

    const { newTree } = removeNode(manualTree, activeNode.id);
    setManualTree(newTree);

    // If we deleted the active node, select the first available node or fallback to an empty string
    if (newTree.length > 0) {
      setSelectedId(newTree[0].id);
    } else {
      setSelectedId('');
    }

    await saveTreeToBackend(newTree);
  };

  const handleInternalNavigation = (targetId: string) => {
    const path = findNodePath(manualTree, targetId);
    if (path !== null) {
      setSelectedId(targetId);
      // Auto-expand all parent folders leading to the newly selected node
      setExpandedIds(prev => {
        const next = new Set(prev);
        path.forEach(id => next.add(id));
        return next;
      });
      setIsEditing(false);
      setStatusMsg('');
    } else {
      setStatusMsg(`Error: Target page '${targetId}' not found.`);
    }
  };

  // --- Render ---

  const renderTree = (nodes: ManualNode[], depth: number = 0) => {
    return nodes.map((node) => {
      const hasChildren = node.children && node.children.length > 0;
      const isExpanded = expandedIds.has(node.id);
      const isSelected = selectedId === node.id;
      const isRoot = depth === 0;

      const isDragTarget = dragOverId === node.id;
      const isBeingDragged = draggedId === node.id;

      return (
        <div key={node.id} style={{ display: 'flex', flexDirection: 'column', marginTop: isRoot ? '0.5rem' : '0' }}>

          {/* Top Drop Indicator (Before) */}
          {isDragTarget && dropPosition === 'before' && (
            <div style={{ height: '2px', backgroundColor: '#38bdf8', width: '100%', margin: '1px 0' }} />
          )}

          <div
            draggable
            onDragStart={(e) => handleDragStart(e, node.id)}
            onDragOver={(e) => handleDragOver(e, node.id)}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, node.id)}
            onDragEnd={handleDragEnd}
            onClick={(e) => {
              setSelectedId(node.id);
              setIsEditing(false);
              setStatusMsg('');

              if (hasChildren) {
                toggleExpand(node.id, e);
              }
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              backgroundColor: isDragTarget && dropPosition === 'inside' ? 'rgba(56, 189, 248, 0.2)'
                             : isSelected ? '#0f172a'
                             : isRoot ? 'rgba(15, 23, 42, 0.4)' : 'transparent',
              color: isSelected ? '#38bdf8' : isRoot ? '#f1f5f9' : '#cbd5e1',
              border: '1px solid',
              borderColor: isDragTarget && dropPosition === 'inside' ? '#38bdf8'
                         : isSelected ? '#38bdf8' : isRoot ? '#334155' : 'transparent',
              borderLeft: isRoot ? `3px solid ${isSelected ? '#38bdf8' : '#0284c7'}` : undefined,
              borderRadius: '6px',
              padding: isRoot ? '0.5rem 0.6rem' : '0.35rem 0.5rem',
              paddingLeft: `${depth * 0.85 + 0.5}rem`,
              cursor: 'pointer',
              fontSize: isRoot ? '0.875rem' : '0.825rem',
              transition: 'all 0.1s ease',
              marginBottom: '2px',
              opacity: isBeingDragged ? 0.4 : 1
            }}
          >
            <div
              onClick={(e) => hasChildren ? toggleExpand(node.id, e) : undefined}
              style={{
                width: '16px', marginRight: '6px', cursor: hasChildren ? 'pointer' : 'default',
                display: 'flex', alignItems: 'center', justifyContent: 'center', color: isRoot ? '#38bdf8' : '#64748b',
                fontSize: '0.75rem'
              }}
            >
              {hasChildren ? (isExpanded ? '▼' : '▶') : (isRoot ? '📁' : '•')}
            </div>

            <span style={{
              fontWeight: isRoot ? '600' : isSelected ? 'bold' : 'normal',
              userSelect: 'none',
              letterSpacing: isRoot ? '0.02em' : 'normal',
              textTransform: isRoot ? 'uppercase' : 'none'
            }}>
              {node.title}
            </span>
          </div>

          {/* Bottom Drop Indicator (After) */}
          {isDragTarget && dropPosition === 'after' && (
            <div style={{ height: '2px', backgroundColor: '#38bdf8', width: '100%', margin: '1px 0' }} />
          )}

          {hasChildren && isExpanded && (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {renderTree(node.children!, depth + 1)}
            </div>
          )}
        </div>
      );
    });
  };

  return (
    <div style={{ display: 'flex', gap: '1.5rem', height: '100%', position: 'relative' }}>

      {/* Sidebar TOC */}
      <div style={{ width: '300px', backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '1rem', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        <h3 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem', color: '#f8fafc', paddingLeft: '0.25rem' }}>Manual Explorer</h3>

        {/* Search Bar Input */}
        <div style={{ marginBottom: '0.75rem', position: 'relative' }}>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search nodes..."
            style={{
              width: '100%',
              backgroundColor: '#0f172a',
              border: '1px solid #334155',
              color: '#f8fafc',
              padding: '0.4rem 1.8rem 0.4rem 0.6rem',
              borderRadius: '6px',
              fontSize: '0.8rem',
              boxSizing: 'border-box'
            }}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              style={{
                position: 'absolute',
                right: '0.4rem',
                top: '50%',
                transform: 'translateY(-50%)',
                background: 'none',
                border: 'none',
                color: '#64748b',
                cursor: 'pointer',
                fontSize: '0.75rem'
              }}
            >
              ✕
            </button>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', overflowY: 'auto', flex: 1, marginBottom: '1rem' }}>
          {filteredTree.length > 0 ? (
            renderTree(filteredTree)
          ) : (
            <span style={{ fontSize: '0.8rem', color: '#64748b', fontStyle: 'italic', paddingLeft: '0.5rem' }}>
              No nodes match "{searchQuery}"
            </span>
          )}
        </div>

        <button
          onClick={() => { setCreateTargetParentId(null); setNewTitle(''); setIsCreateModalOpen(true); }}
          style={{ backgroundColor: '#0f172a', color: '#cbd5e1', border: '1px dashed #475569', padding: '0.5rem', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem' }}
        >
          + Add Root Topic
        </button>
      </div>

      {/* Content Panel */}
      <div style={{ flex: 1, backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '1.5rem', overflowY: 'auto' }}>
        {activeNode ? (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '1rem', marginBottom: '1.5rem' }}>
              <div>
                <h2 style={{ color: '#f8fafc', margin: 0 }}>{activeNode.title}</h2>
                <span style={{ fontSize: '0.75rem', color: '#64748b', fontFamily: 'monospace', display: 'block', marginBottom: '0.5rem' }}>
                  ID: {activeNode.id}
                </span>

                {/* Timestamp Metadata Block */}
                {(activeNode.updatedAt || activeNode.lastChildUpdate) && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                    {activeNode.updatedAt && (
                      <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                        Edited: {new Date(activeNode.updatedAt).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                      </span>
                    )}

                    {activeNode.lastChildUpdate && (
                      <span
                        onClick={() => handleInternalNavigation(activeNode.lastChildUpdate!.id)}
                        style={{
                          fontSize: '0.75rem',
                          color: '#38bdf8',
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.25rem'
                        }}
                        title="Click to view updated child document"
                      >
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
                    <button onClick={handleSaveEdit} style={{ backgroundColor: '#10b981', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer' }}>Save</button>
                    <button onClick={() => setIsEditing(false)} style={{ backgroundColor: '#334155', color: '#f8fafc', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer' }}>Cancel</button>
                  </>
                ) : (
                  <>
                    <button onClick={() => { setCreateTargetParentId(activeNode.id); setNewTitle(''); setIsCreateModalOpen(true); }} style={{ backgroundColor: '#0f172a', color: '#cbd5e1', border: '1px solid #475569', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer' }}>+ Sub-Topic</button>
                    <button onClick={handleStartEdit} style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer' }}>Edit Section</button>
                    <button onClick={handleDeleteNode} style={{ backgroundColor: '#ef4444', color: '#f8fafc', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer' }}>Delete</button>
                  </>
                )}
              </div>
            </div>

            {isEditing ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <input
                  type="text"
                  value={editForm.title}
                  onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                  style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', padding: '0.6rem', borderRadius: '4px', fontWeight: 'bold' }}
                />

                {/* Embedded Markdown Toolbar */}
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <MarkdownToolbar
                    textareaRef={editTextareaRef}
                    content={editForm.content}
                    setContent={(content) => setEditForm({ ...editForm, content })}
                  />
                  <textarea
                    ref={editTextareaRef}
                    value={editForm.content}
                    onChange={(e) => setEditForm({ ...editForm, content: e.target.value })}
                    rows={20}
                    style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', borderTop: 'none', color: '#38bdf8', padding: '0.8rem', borderRadius: '0 0 6px 6px', fontFamily: 'monospace', resize: 'vertical' }}
                  />
                </div>
              </div>
            ) : (
              <MarkdownRenderer
                content={activeNode.content || '*No content provided.*'}
                onInternalLinkClick={handleInternalNavigation}
              />
            )}
          </div>
        ) : (
          <p style={{ color: '#64748b' }}>Select a topic to view.</p>
        )}
      </div>

      {/* Create Modal Overlay */}
      {isCreateModalOpen && (
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(15, 23, 42, 0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, borderRadius: '8px' }}>
          <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1.5rem', width: '400px' }}>
            <h3 style={{ color: '#f8fafc', margin: '0 0 1rem 0' }}>{createTargetParentId ? 'Add Sub-Topic' : 'Add Root Topic'}</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Topic Title"
                autoFocus
                style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', padding: '0.6rem', borderRadius: '4px' }}
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                <button onClick={() => setIsCreateModalOpen(false)} style={{ backgroundColor: 'transparent', color: '#cbd5e1', border: '1px solid #475569', padding: '0.5rem 1rem', borderRadius: '4px', cursor: 'pointer' }}>Cancel</button>
                <button onClick={handleCreateNode} disabled={!newTitle.trim()} style={{ backgroundColor: newTitle.trim() ? '#38bdf8' : '#334155', color: '#0f172a', border: 'none', padding: '0.5rem 1rem', borderRadius: '4px', fontWeight: 'bold' }}>Create</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}