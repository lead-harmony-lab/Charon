/**
 * @file src/features/docs/ManualViewer/ManualSidebar.tsx
 * @description
 */
import React, { DragEvent } from 'react';
import { ManualNode } from '../../../components/treeUtils';

interface ManualSidebarProps {
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  filteredTree: ManualNode[];
  expandedIds: Set<string>;
  selectedId: string;
  draggedId: string | null;
  dragOverId: string | null;
  dropPosition: 'before' | 'after' | 'inside' | null;
  onDragStart: (e: DragEvent<HTMLDivElement>, id: string) => void;
  onDragOver: (e: DragEvent<HTMLDivElement>, id: string) => void;
  onDragLeave: () => void;
  onDrop: (e: DragEvent<HTMLDivElement>, id: string) => void;
  onDragEnd: () => void;
  onNavigate: (id: string) => void;
  onToggleExpand: (id: string, e: React.MouseEvent) => void;
  onAddRootTopic: () => void;
}

export function ManualSidebar(props: ManualSidebarProps) {
  const {
    searchQuery, setSearchQuery, filteredTree, expandedIds, selectedId,
    draggedId, dragOverId, dropPosition,
    onDragStart, onDragOver, onDragLeave, onDrop, onDragEnd,
    onNavigate, onToggleExpand, onAddRootTopic
  } = props;

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
          {isDragTarget && dropPosition === 'before' && (
            <div style={{ height: '2px', backgroundColor: '#38bdf8', width: '100%', margin: '1px 0' }} />
          )}
          <div
            draggable
            onDragStart={(e) => onDragStart(e, node.id)}
            onDragOver={(e) => onDragOver(e, node.id)}
            onDragLeave={onDragLeave}
            onDrop={(e) => onDrop(e, node.id)}
            onDragEnd={onDragEnd}
            onClick={(e) => {
              onNavigate(node.id);
              if (hasChildren) onToggleExpand(node.id, e);
            }}
            style={{
              display: 'flex', alignItems: 'center',
              backgroundColor: isDragTarget && dropPosition === 'inside' ? 'rgba(56, 189, 248, 0.2)'
                             : isSelected ? '#0f172a' : isRoot ? 'rgba(15, 23, 42, 0.4)' : 'transparent',
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
              onClick={(e) => hasChildren ? onToggleExpand(node.id, e) : undefined}
              style={{
                width: '16px', marginRight: '6px', cursor: hasChildren ? 'pointer' : 'default',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: isRoot ? '#38bdf8' : '#64748b', fontSize: '0.75rem'
              }}
            >
              {hasChildren ? (isExpanded ? '▼' : '▶') : (isRoot ? '📁' : '•')}
            </div>
            <span style={{
              fontWeight: isRoot ? '600' : isSelected ? 'bold' : 'normal',
              userSelect: 'none', letterSpacing: isRoot ? '0.02em' : 'normal',
              textTransform: isRoot ? 'uppercase' : 'none'
            }}>
              {node.title}
            </span>
          </div>
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
    <div style={{ width: '300px', backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', padding: '1rem', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
      <h3 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem', color: '#f8fafc', paddingLeft: '0.25rem' }}>Manual Explorer</h3>
      <div style={{ marginBottom: '0.75rem', position: 'relative' }}>
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search nodes..."
          style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', padding: '0.4rem 1.8rem 0.4rem 0.6rem', borderRadius: '6px', fontSize: '0.8rem', boxSizing: 'border-box' }}
        />
        {searchQuery && (
          <button onClick={() => setSearchQuery('')} style={{ position: 'absolute', right: '0.4rem', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: '0.75rem' }}>✕</button>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', overflowY: 'auto', flex: 1, marginBottom: '1rem' }}>
        {filteredTree.length > 0 ? renderTree(filteredTree) : <span style={{ fontSize: '0.8rem', color: '#64748b', fontStyle: 'italic', paddingLeft: '0.5rem' }}>No nodes match "{searchQuery}"</span>}
      </div>
      <button onClick={onAddRootTopic} style={{ backgroundColor: '#0f172a', color: '#cbd5e1', border: '1px dashed #475569', padding: '0.5rem', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem' }}>
        + Add Root Topic
      </button>
    </div>
  );
}