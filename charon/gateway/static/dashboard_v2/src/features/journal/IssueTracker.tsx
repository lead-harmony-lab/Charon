/**
 * @file src/features/journal/IssueTracker.tsx
 * @description Kanban-style issue tracker with support for linking Blackboard execution traces.
 */
import React, { useState } from 'react';

// --- Data Model ---
export type TicketStatus = 'todo' | 'in_progress' | 'blocked' | 'done';
export type TicketPriority = 'low' | 'medium' | 'high' | 'critical';

export interface Ticket {
  id: string;
  title: string;
  description: string;
  status: TicketStatus;
  priority: TicketPriority;
  linkedTraces: string[]; // Blackboard trace IDs
  createdAt: string;
}

// --- Mock Data ---
const INITIAL_TICKETS: Ticket[] = [
  {
    id: 'CHAR-001',
    title: 'Resolve GnomeIPC race condition',
    description: 'Daemon disconnects intermittently under heavy load during matrix sync.',
    status: 'in_progress',
    priority: 'high',
    linkedTraces: ['trace-9f8a-4b2c'],
    createdAt: new Date().toISOString(),
  },
  {
    id: 'CHAR-002',
    title: 'Implement automated doc generation',
    description: 'Pipe completed ticket data into the Knowledge Base via the Doc Queue.',
    status: 'todo',
    priority: 'medium',
    linkedTraces: [],
    createdAt: new Date().toISOString(),
  }
];

// --- Helper Components ---
const PriorityBadge = ({ priority }: { priority: TicketPriority }) => {
  const colors = {
    low: { bg: '#064e3b', text: '#34d399' },       // Emerald
    medium: { bg: '#1e3a8a', text: '#60a5fa' },    // Blue
    high: { bg: '#7c2d12', text: '#fb923c' },      // Orange
    critical: { bg: '#7f1d1d', text: '#f87171' },  // Red
  };
  const { bg, text } = colors[priority];

  return (
    <span style={{ backgroundColor: bg, color: text, padding: '2px 8px', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 'bold', textTransform: 'uppercase' }}>
      {priority}
    </span>
  );
};

// --- Main Component ---
export function IssueTracker() {
  const [tickets, setTickets] = useState<Ticket[]>(INITIAL_TICKETS);

  const columns: { id: TicketStatus; label: string }[] = [
    { id: 'todo', label: 'To Do' },
    { id: 'in_progress', label: 'In Progress' },
    { id: 'blocked', label: 'Blocked' },
    { id: 'done', label: 'Done' }
  ];

  return (
    <div style={{ display: 'flex', gap: '1rem', height: '100%', overflowX: 'auto', paddingBottom: '1rem' }}>
      {columns.map(column => (
        <div key={column.id} style={{ flex: '1 1 300px', minWidth: '280px', backgroundColor: '#0f172a', borderRadius: '8px', border: '1px solid #334155', display: 'flex', flexDirection: 'column' }}>

          {/* Column Header */}
          <div style={{ padding: '1rem', borderBottom: '1px solid #334155', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0, fontSize: '0.95rem', color: '#e2e8f0' }}>{column.label}</h3>
            <span style={{ backgroundColor: '#1e293b', color: '#94a3b8', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem' }}>
              {tickets.filter(t => t.status === column.id).length}
            </span>
          </div>

          {/* Ticket List */}
          <div style={{ padding: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', overflowY: 'auto', flex: 1 }}>
            {tickets.filter(t => t.status === column.id).map(ticket => (
              <div key={ticket.id} style={{ backgroundColor: '#1e293b', padding: '1rem', borderRadius: '6px', border: '1px solid #334155', cursor: 'grab' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                  <span style={{ color: '#38bdf8', fontSize: '0.8rem', fontWeight: 'bold' }}>{ticket.id}</span>
                  <PriorityBadge priority={ticket.priority} />
                </div>
                <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', color: '#f8fafc', lineHeight: '1.4' }}>
                  {ticket.title}
                </h4>
                {ticket.linkedTraces.length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '0.75rem', color: '#94a3b8', fontSize: '0.75rem' }}>
                    <span role="img" aria-label="link">🔗</span>
                    {ticket.linkedTraces.length} linked trace(s)
                  </div>
                )}
              </div>
            ))}

            {/* Add Ticket Button */}
            <button style={{ backgroundColor: 'transparent', border: '1px dashed #334155', color: '#94a3b8', padding: '0.75rem', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', textAlign: 'center', transition: 'all 0.2s' }}
              onMouseOver={(e) => e.currentTarget.style.borderColor = '#38bdf8'}
              onMouseOut={(e) => e.currentTarget.style.borderColor = '#334155'}
            >
              + Add Issue
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}