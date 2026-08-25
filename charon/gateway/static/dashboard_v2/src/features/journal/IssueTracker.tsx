/**
 * @file src/features/journal/IssueTracker.tsx
 * @description Kanban view filtered for Journal entries with assigned statuses.
 */
import React from 'react';
import { JournalEntry, TicketStatus, TicketPriority } from './types';

interface IssueTrackerProps {
  entries: JournalEntry[];
  onUpdateStatus: (id: string, newStatus: TicketStatus) => Promise<void>;
  onSelectEntry: (id: string) => void;
}

const PriorityBadge = ({ priority }: { priority: TicketPriority }) => {
  const colors = {
    low: { bg: '#064e3b', text: '#34d399' },
    medium: { bg: '#1e3a8a', text: '#60a5fa' },
    high: { bg: '#7c2d12', text: '#fb923c' },
    critical: { bg: '#7f1d1d', text: '#f87171' },
  };
  const { bg, text } = colors[priority];

  return (
    <span style={{ backgroundColor: bg, color: text, padding: '2px 8px', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 'bold', textTransform: 'uppercase' }}>
      {priority}
    </span>
  );
};

export function IssueTracker({ entries, onUpdateStatus, onSelectEntry }: IssueTrackerProps) {
  const trackedTickets = entries.filter((e) => e.status !== null);

  const columns: { id: TicketStatus; label: string }[] = [
    { id: 'todo', label: 'To Do' },
    { id: 'in_progress', label: 'In Progress' },
    { id: 'blocked', label: 'Blocked' },
    { id: 'done', label: 'Done' },
  ];

  const handleDragStart = (e: React.DragEvent<HTMLDivElement>, ticketId: string) => {
    e.dataTransfer.setData('ticketId', ticketId);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault(); // Necessary to allow dropping
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>, status: TicketStatus) => {
    e.preventDefault();
    const ticketId = e.dataTransfer.getData('ticketId');
    if (ticketId) {
      onUpdateStatus(ticketId, status);
    }
  };

  return (
    <div style={{ display: 'flex', gap: '1rem', height: '100%', overflowX: 'auto', paddingBottom: '0.5rem' }}>
      {columns.map((column) => {
        const columnTickets = trackedTickets.filter((t) => t.status === column.id);

        return (
          <div key={column.id} style={{ flex: '1 1 300px', minWidth: '280px', backgroundColor: '#0f172a', borderRadius: '8px', border: '1px solid #334155', display: 'flex', flexDirection: 'column' }}>
            {/* Column Header */}
            <div style={{ padding: '1rem', borderBottom: '1px solid #334155', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: '0.95rem', color: '#e2e8f0' }}>{column.label}</h3>
              <span style={{ backgroundColor: '#1e293b', color: '#94a3b8', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem' }}>
                {columnTickets.length}
              </span>
            </div>

            {/* Drop Zone / Ticket List */}
            <div
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, column.id)}
              style={{ padding: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', overflowY: 'auto', flex: 1 }}
            >
              {columnTickets.map((ticket) => (
                <div
                  key={ticket.id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, ticket.id)}
                  style={{
                    backgroundColor: '#1e293b',
                    padding: '1rem',
                    borderRadius: '6px',
                    border: '1px solid #334155',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.5rem',
                    cursor: 'grab'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <button
                      onClick={() => onSelectEntry(ticket.id)}
                      style={{ background: 'none', border: 'none', color: '#38bdf8', fontSize: '0.8rem', fontWeight: 'bold', cursor: 'pointer', padding: 0 }}
                    >
                      {ticket.id}
                    </button>
                    <PriorityBadge priority={ticket.priority} />
                  </div>

                  <h4 style={{ margin: 0, fontSize: '0.9rem', color: '#f8fafc', lineHeight: '1.4' }}>
                    {ticket.title}
                  </h4>

                  {ticket.linkedArtifacts.length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#94a3b8', fontSize: '0.75rem' }}>
                      🔗 {ticket.linkedArtifacts.length} artifact(s) linked
                    </div>
                  )}

                  {/* Status Move Controls (Fallback) */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid #334155' }}>
                    <span style={{ fontSize: '0.7rem', color: '#64748b' }}>Move to:</span>
                    <select
                      value={ticket.status || ''}
                      onChange={(e) => onUpdateStatus(ticket.id, e.target.value as TicketStatus)}
                      style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#e2e8f0', fontSize: '0.75rem', borderRadius: '4px', padding: '2px 4px', cursor: 'pointer' }}
                    >
                      <option value="todo">To Do</option>
                      <option value="in_progress">In Progress</option>
                      <option value="blocked">Blocked</option>
                      <option value="done">Done</option>
                    </select>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}