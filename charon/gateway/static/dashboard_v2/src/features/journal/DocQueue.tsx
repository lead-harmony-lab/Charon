/**
 * @file src/features/journal/DocQueue.tsx
 * @description Automated documentation queue for reviewing and publishing agent-generated docs.
 */
import React, { useState } from 'react';

// --- Data Model ---
export type DocType = 'ADR' | 'API_Spec' | 'System_Guide' | 'Changelog';
export type QueueStatus = 'pending' | 'generating' | 'review' | 'published';

export interface DocTask {
  id: string;
  title: string;
  type: DocType;
  status: QueueStatus;
  linkedTicketId?: string; // Ties back to the Issue Tracker
  assignedAgent: string;
  timestamp: string;
}

// --- Mock Data ---
const INITIAL_QUEUE: DocTask[] = [
  {
    id: 'DOC-042',
    title: 'GnomeIPC Lifecycle & Reconnection Strategy',
    type: 'System_Guide',
    status: 'review',
    linkedTicketId: 'CHAR-001',
    assignedAgent: 'Architect-Omega',
    timestamp: new Date(Date.now() - 1000 * 60 * 15).toISOString(), // 15 mins ago
  },
  {
    id: 'DOC-043',
    title: 'Update Blackboard Telemetry Specs',
    type: 'API_Spec',
    status: 'generating',
    assignedAgent: 'TechWriter-Sigma',
    timestamp: new Date().toISOString(),
  },
  {
    id: 'DOC-044',
    title: 'ADR: Standardize UI to Kanban-lite Tracking',
    type: 'ADR',
    status: 'pending',
    linkedTicketId: 'CHAR-002',
    assignedAgent: 'Architect-Omega',
    timestamp: new Date().toISOString(),
  }
];

// --- Helper Components ---
const StatusIndicator = ({ status }: { status: QueueStatus }) => {
  const configs = {
    pending: { color: '#94a3b8', label: 'Queued', icon: '⏳' },
    generating: { color: '#38bdf8', label: 'Agent Drafting...', icon: '⚙️' },
    review: { color: '#fb923c', label: 'Needs Review', icon: '👀' },
    published: { color: '#10b981', label: 'Published', icon: '✅' }
  };

  const conf = configs[status];

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: conf.color, fontSize: '0.85rem', fontWeight: 'bold' }}>
      <span className={status === 'generating' ? 'spin-animation' : ''}>{conf.icon}</span>
      {conf.label}
      <style>{`
        @keyframes spin { 100% { transform: rotate(360deg); } }
        .spin-animation { display: inline-block; animation: spin 2s linear infinite; }
      `}</style>
    </div>
  );
};

// --- Main Component ---
export function DocQueue() {
  const [queue, setQueue] = useState<DocTask[]>(INITIAL_QUEUE);

  const handlePublish = (id: string) => {
    setQueue(prev => prev.map(task => task.id === id ? { ...task, status: 'published' } : task));
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '0.5rem', borderBottom: '1px solid #334155' }}>
        <h3 style={{ margin: 0, color: '#e2e8f0', fontSize: '1.1rem' }}>Automated Doc Queue</h3>
        <button style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#e2e8f0', padding: '0.5rem 1rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>
          + Trigger Manual Run
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', overflowY: 'auto', paddingRight: '0.5rem' }}>
        {queue.map(task => (
          <div key={task.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#1e293b', padding: '1rem 1.25rem', borderRadius: '8px', border: '1px solid #334155' }}>

            {/* Left Col: Info */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{ color: '#94a3b8', fontSize: '0.75rem', fontWeight: 'bold', fontFamily: 'monospace' }}>{task.id}</span>
                <span style={{ backgroundColor: '#0f172a', color: '#a78bfa', padding: '2px 8px', borderRadius: '4px', fontSize: '0.7rem', border: '1px solid #4c1d95' }}>
                  {task.type.replace('_', ' ')}
                </span>
                {task.linkedTicketId && (
                  <span style={{ color: '#64748b', fontSize: '0.75rem' }}>
                    Triggered by <span style={{ color: '#38bdf8' }}>{task.linkedTicketId}</span>
                  </span>
                )}
              </div>
              <h4 style={{ margin: 0, color: '#f8fafc', fontSize: '1rem' }}>{task.title}</h4>
              <div style={{ color: '#64748b', fontSize: '0.8rem' }}>
                Assigned to: <strong style={{ color: '#cbd5e1' }}>{task.assignedAgent}</strong>
              </div>
            </div>

            {/* Right Col: Status & Actions */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
              <StatusIndicator status={task.status} />

              {task.status === 'review' && (
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button style={{ backgroundColor: 'transparent', border: '1px solid #ef4444', color: '#ef4444', padding: '0.4rem 0.75rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem' }}>
                    Reject
                  </button>
                  <button
                    onClick={() => handlePublish(task.id)}
                    style={{ backgroundColor: '#10b981', border: 'none', color: '#022c22', padding: '0.4rem 0.75rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 'bold' }}>
                    Approve & Publish
                  </button>
                </div>
              )}
              {task.status === 'published' && (
                <button style={{ backgroundColor: '#334155', border: 'none', color: '#f8fafc', padding: '0.4rem 0.75rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem' }}>
                  View in KB
                </button>
              )}
            </div>

          </div>
        ))}
      </div>
    </div>
  );
}