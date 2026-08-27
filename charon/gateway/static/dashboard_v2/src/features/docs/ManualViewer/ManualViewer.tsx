/**
 * @file src/features/docs/ManualViewer/ManualViewer.tsx
 * @description A recursive, multi-level Markdown viewer and editor for system manuals with React Router integration,
 * Drag and Drop, Backend API Integration, internal node linking, node search filtering, and lazy loading.
 */
import React, { useState, useEffect, useMemo, DragEvent, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { authFetch } from '../../../core/api/client';
import { ManualSidebar } from './ManualSidebar';
import { ManualContent } from './ManualContent';
import { INITIAL_TREE } from './manualUtils';
import {
  ManualNode, findNodeById, findNodePath, filterTree,
  updateTree, addNodeToTree, isDescendant, removeNode,
  insertNode, flattenManualTree, stripContentForSave
} from '../../../components/treeUtils';

export * from './manualUtils';

export function ManualViewer() {
  const { nodeId } = useParams<{ nodeId?: string }>();
  const navigate = useNavigate();

  const [manualTree, setManualTree] = useState<ManualNode[]>(INITIAL_TREE);

  // Safely initialize to the URL param, or fallback to an empty string if the tree is empty
  const [selectedId, setSelectedId] = useState<string>(nodeId || '');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editForm, setEditForm] = useState({ title: '', content: '' });
  const [statusMsg, setStatusMsg] = useState<string>('');

  // Loading state for individual markdown content
  const [isLoadingContent, setIsLoadingContent] = useState<boolean>(false);

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createTargetParentId, setCreateTargetParentId] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState('');

  const [isLinkModalOpen, setIsLinkModalOpen] = useState(false);
  const [targetNodeId, setTargetNodeId] = useState<string>('');
  const [linkDisplayText, setLinkDisplayText] = useState<string>('');

  const editTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [dropPosition, setDropPosition] = useState<'before' | 'after' | 'inside' | null>(null);

  const activeNode = findNodeById(manualTree, selectedId) || null;
  const flatNodeList = useMemo(() => flattenManualTree(manualTree), [manualTree]);
  const filteredTree = useMemo(() => filterTree(manualTree, searchQuery), [manualTree, searchQuery]);

  // Handle URL Parameter Syncing
  useEffect(() => {
    if (nodeId && manualTree.length > 0) {
      const path = findNodePath(manualTree, nodeId);
      if (path !== null) {
        setSelectedId(nodeId);
        setExpandedIds(prev => new Set([...prev, ...path]));
        setIsEditing(false);
      } else {
        console.warn(`Node ID '${nodeId}' not found in tree structure.`);
        setStatusMsg(`Error: Target page '${nodeId}' not found.`);
      }
    }
  }, [nodeId, manualTree]);

  // Router-aware Navigation
  const handleInternalNavigation = useCallback((targetId: string) => {
    navigate(`/docs/manual/${targetId}`);
  }, [navigate]);

  // Auto-expand nodes matching search query
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
    setExpandedIds(prev => new Set([...prev, ...collectParentIds(filteredTree)]));
  }, [searchQuery, filteredTree]);

  const loadManualTree = async () => {
    try {
      const response = await authFetch('/v1/docs/manual');
      if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status}`);
      }

      const data = await response.json();
      let fetchedTree: ManualNode[] = [];

      if (Array.isArray(data)) {
        fetchedTree = data;
      } else if (data && Array.isArray(data.tree)) {
        fetchedTree = data.tree;
      } else if (data && data.tree && Array.isArray(data.tree.tree)) {
        fetchedTree = data.tree.tree;
      } else {
        console.warn("Unexpected manual tree format from backend:", data);
      }

      if (fetchedTree && fetchedTree.length > 0) {
        setManualTree(fetchedTree);

        if (!nodeId) {
          setTimeout(() => {
            navigate(`/docs/manual/${fetchedTree[0].id}`, { replace: true });
          }, 0);
        }
      } else {
        console.warn("Tree fetched successfully, but appears empty.");
      }
    } catch (err) {
      console.error("Failed to load manual tree:", err);
      setStatusMsg('Error: Failed to load manual structure.');
    }
  };

  // Lazy-load content when a node is selected and lacks the content property
  useEffect(() => {
    const node = findNodeById(manualTree, selectedId);

    if (node && typeof node.content !== 'string' && !isLoadingContent) {
      const fetchNodeContent = async () => {
        setIsLoadingContent(true);
        try {
          const response = await authFetch(`/v1/docs/manual/${selectedId}`);
          if (response.ok) {
            const data = await response.json();
            setManualTree(prevTree => {
              const targetNode = findNodeById(prevTree, selectedId);
              if (!targetNode) return prevTree;
              return updateTree(prevTree, selectedId, {
                title: targetNode.title,
                content: data.content || ''
              });
            });
          } else {
            console.error(`Failed to fetch content for ${selectedId}, HTTP ${response.status}`);
            setStatusMsg(`Error: Failed to load content for ${selectedId}`);
            setManualTree(prevTree => updateTree(prevTree, selectedId, { content: '' }));
          }
        } catch (error) {
          console.error(`Network issue loading ${selectedId}:`, error);
          setStatusMsg(`Error: Network issue loading ${selectedId}`);
          setManualTree(prevTree => updateTree(prevTree, selectedId, { content: '' }));
        } finally {
          setIsLoadingContent(false);
        }
      };

      fetchNodeContent();
    }
  }, [selectedId, manualTree, isLoadingContent]);

  // API Call: Save only the tree structure
  const saveTreeToBackend = async (treeToSave: ManualNode[]) => {
    setStatusMsg('Saving structure...');
    try {
      const leanTree = stripContentForSave(treeToSave);
      await authFetch('/v1/docs/manual', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(leanTree)
      });
      setStatusMsg('Structure updated successfully!');
      setTimeout(() => setStatusMsg(''), 3000);
    } catch {
      setStatusMsg('Error: Failed to save structure.');
    }
  };

  // API Call: Save markdown content and receive updated timestamps + tree
  const saveNodeContentToBackend = async (id: string, title: string, content: string) => {
    try {
      const response = await authFetch(`/v1/docs/manual/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content })
      });

      if (!response.ok) return null;
      return await response.json();
    } catch (err) {
      return null;
    }
  };

  useEffect(() => { loadManualTree(); }, []);

  // --- Drag & Drop Handlers ---
  const handleDragStart = (e: DragEvent<HTMLDivElement>, id: string) => {
    e.dataTransfer.setData('text/plain', id);
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
    if (relativeY < rect.height * 0.25) setDropPosition('before');
    else if (relativeY > rect.height * 0.75) setDropPosition('after');
    else setDropPosition('inside');
  };

  const handleDrop = async (e: DragEvent<HTMLDivElement>, targetId: string) => {
    e.preventDefault();
    if (!draggedId || !dropPosition || draggedId === targetId || isDescendant(manualTree, draggedId, targetId)) return;
    const { newTree, removedNode } = removeNode(manualTree, draggedId);
    if (removedNode) {
      const finalTree = insertNode(newTree, targetId, removedNode, dropPosition);
      setManualTree(finalTree);
      if (dropPosition === 'inside') setExpandedIds(prev => new Set(prev).add(targetId));
      await saveTreeToBackend(finalTree);
    }
    setDraggedId(null);
    setDragOverId(null);
    setDropPosition(null);
  };

  const handleDragLeave = () => { setDragOverId(null); setDropPosition(null); };
  const handleDragEnd = () => { setDraggedId(null); setDragOverId(null); setDropPosition(null); };

  const toggleExpand = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  // --- Topic Creation & Deletion Handlers ---
  const handleCreateNode = async () => {
    if (!newTitle.trim()) return;
    const generatedId = newTitle.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
    const initialContent = `## ${newTitle.trim()}\n\nStart writing documentation here...`;

    const newNode: ManualNode = {
      id: generatedId,
      title: newTitle.trim(),
      content: initialContent,
      children: []
    };

    const updated = addNodeToTree(manualTree, createTargetParentId, newNode);
    setManualTree(updated);

    if (createTargetParentId) setExpandedIds(prev => new Set(prev).add(createTargetParentId));
    setIsCreateModalOpen(false);
    setIsEditing(false);

    await saveTreeToBackend(updated);
    await saveNodeContentToBackend(generatedId, newTitle.trim(), initialContent);

    handleInternalNavigation(generatedId);
  };

  const handleDeleteNode = async () => {
    if (!activeNode || !window.confirm(`Are you sure you want to delete "${activeNode.title}"?`)) return;
    const { newTree } = removeNode(manualTree, activeNode.id);
    setManualTree(newTree);
    if (newTree.length > 0) {
      handleInternalNavigation(newTree[0].id);
    } else {
      navigate('/docs/manual');
      setSelectedId('');
    }
    await saveTreeToBackend(newTree);
  };

  const handleCopyLink = () => {
    if (!activeNode) return;
    navigator.clipboard.writeText(`${window.location.origin}/docs/manual/${activeNode.id}`)
      .then(() => { setStatusMsg('Link copied!'); setTimeout(() => setStatusMsg(''), 3000); })
      .catch(() => setStatusMsg('Error copying link.'));
  };

  const handleInsertNodeLink = () => {
    if (!targetNodeId || !editTextareaRef.current) return;
    const selectedNode = flatNodeList.find((n: any) => n.id === targetNodeId);
    const displayText = linkDisplayText.trim() || selectedNode?.title || targetNodeId;
    const markdownLink = `[${displayText}](/docs/manual/${targetNodeId})`;
    const textarea = editTextareaRef.current;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const currentContent = editForm.content;
    setEditForm({ ...editForm, content: currentContent.substring(0, start) + markdownLink + currentContent.substring(end) });
    setIsLinkModalOpen(false);
    setTargetNodeId('');
    setLinkDisplayText('');
    setTimeout(() => {
      textarea.focus();
      textarea.setSelectionRange(start + markdownLink.length, start + markdownLink.length);
    }, 50);
  };

  return (
    <div style={{ display: 'flex', gap: '1.5rem', height: '100%', position: 'relative' }}>
      <ManualSidebar
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        filteredTree={filteredTree}
        expandedIds={expandedIds}
        selectedId={selectedId}
        draggedId={draggedId}
        dragOverId={dragOverId}
        dropPosition={dropPosition}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onDragEnd={handleDragEnd}
        onNavigate={handleInternalNavigation}
        onToggleExpand={toggleExpand}
        onAddRootTopic={() => { setCreateTargetParentId(null); setNewTitle(''); setIsCreateModalOpen(true); }}
      />
      <ManualContent
        activeNode={activeNode}
        isEditing={isEditing}
        isLoadingContent={isLoadingContent}
        editForm={editForm}
        statusMsg={statusMsg}
        editTextareaRef={editTextareaRef}
        setEditForm={setEditForm}
        setIsEditing={setIsEditing}
        onSaveEdit={async () => {
          setStatusMsg('Saving document...');

          const saveResult = await saveNodeContentToBackend(selectedId, editForm.title, editForm.content);

          if (!saveResult) {
            setStatusMsg('Error: Failed to save document content.');
            return;
          }

          // Use returned structural tree (with new timestamps) merged with current content
          const baseTree = saveResult.tree && saveResult.tree.length > 0 ? saveResult.tree : manualTree;
          const updatedTree = updateTree(baseTree, selectedId, {
            title: editForm.title,
            content: editForm.content,
            updatedAt: saveResult.updatedAt
          });
          setManualTree(updatedTree);

          if (activeNode?.title !== editForm.title) {
            await saveTreeToBackend(updatedTree);
          } else {
            setStatusMsg('Document saved successfully!');
            setTimeout(() => setStatusMsg(''), 3000);
          }

          setIsEditing(false);
        }}
        onStartEdit={() => {
          setEditForm({ title: activeNode?.title || '', content: activeNode?.content || '' });
          setIsEditing(true);
          setStatusMsg('');
        }}
        onCopyLink={handleCopyLink}
        onAddSubTopic={() => { setCreateTargetParentId(activeNode?.id || null); setNewTitle(''); setIsCreateModalOpen(true); }}
        onDeleteNode={handleDeleteNode}
        onNavigate={handleInternalNavigation}
        onOpenLinkModal={() => {
          if (flatNodeList.length > 0) {
            setTargetNodeId(flatNodeList[0].id);
            setLinkDisplayText((flatNodeList[0] as any).title);
          }
          setIsLinkModalOpen(true);
        }}
      />

      {/* --- Link Modal --- */}
      {isLinkModalOpen && (
        <div style={{ position: 'absolute', inset: 0, backgroundColor: 'rgba(15,23,42,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60 }}>
          <div style={{ backgroundColor: '#1e293b', padding: '1.5rem', width: '420px', borderRadius: '8px' }}>
            <h3 style={{ color: '#f8fafc', margin: '0 0 1rem 0' }}>Insert Link to Manual Topic</h3>
            <select
              value={targetNodeId}
              onChange={(e) => {
                const chosenId = e.target.value;
                setTargetNodeId(chosenId);
                if (!linkDisplayText) setLinkDisplayText(flatNodeList.find((n: any) => n.id === chosenId)?.title || '');
              }}
              style={{ width: '100%', marginBottom: '1rem', padding: '0.5rem' }}
            >
              {flatNodeList.map((node: any) => <option key={node.id} value={node.id}>{node.title}</option>)}
            </select>
            <input
              type="text"
              placeholder="Display Text"
              value={linkDisplayText}
              onChange={(e) => setLinkDisplayText(e.target.value)}
              style={{ width: '100%', marginBottom: '1rem', padding: '0.5rem' }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button onClick={() => setIsLinkModalOpen(false)} style={{ color: '#cbd5e1' }}>Cancel</button>
              <button onClick={handleInsertNodeLink} style={{ backgroundColor: '#38bdf8', padding: '0.4rem 0.8rem' }}>Insert</button>
            </div>
          </div>
        </div>
      )}

      {/* --- Create Topic Modal --- */}
      {isCreateModalOpen && (
        <div style={{ position: 'absolute', inset: 0, backgroundColor: 'rgba(15,23,42,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}>
          <div style={{ backgroundColor: '#1e293b', padding: '1.5rem', width: '400px', borderRadius: '8px' }}>
            <h3 style={{ color: '#f8fafc', margin: '0 0 1rem 0' }}>{createTargetParentId ? 'Add Sub-Topic' : 'Add Root Topic'}</h3>
            <input
              type="text"
              placeholder="Topic Title"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              autoFocus
              style={{ width: '100%', marginBottom: '1rem', padding: '0.6rem' }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button onClick={() => setIsCreateModalOpen(false)} style={{ color: '#cbd5e1' }}>Cancel</button>
              <button onClick={handleCreateNode} disabled={!newTitle.trim()} style={{ backgroundColor: '#38bdf8', padding: '0.5rem 1rem' }}>Create</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}