import React, { useEffect, useRef } from 'react';
import { ThoughtRecord } from './BlackboardObserver';

export function BlackboardTrace({ thoughts }: { thoughts: ThoughtRecord[] }) {
  const endOfListRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new thoughts
  useEffect(() => {
    endOfListRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [thoughts]);

  const getThoughtColor = (type: string) => {
    switch (type.toUpperCase()) {
      case 'ANALYSIS': return '#8b5cf6'; // Purple
      case 'PLANNING': return '#3b82f6'; // Blue
      case 'EXECUTION': return '#10b981'; // Green
      case 'ERROR': return '#ef4444'; // Red
      default: return '#64748b'; // Gray
    }
  };

  if (thoughts.length === 0) {
    return (
      <div style={{ padding: '2rem', color: '#64748b', textAlign: 'center', fontStyle: 'italic' }}>
        Listening for agent telemetry...
      </div>
    );
  }

  return (
    <div style={{ padding: '1rem', overflowY: 'auto', flex: 1, fontFamily: 'monospace' }}>
      {thoughts.map((thought) => (
        <div key={thought.id} style={{ marginBottom: '0.75rem', fontSize: '0.9rem', lineHeight: '1.4' }}>
          <span style={{ color: '#64748b' }}>[{new Date(thought.timestamp).toLocaleTimeString()}] </span>
          <span style={{ color: '#38bdf8', fontWeight: 'bold' }}>{thought.agent_name}</span>
          <span style={{ color: '#64748b' }}> :: </span>
          <span style={{
            color: getThoughtColor(thought.thought_type),
            border: `1px solid ${getThoughtColor(thought.thought_type)}40`,
            backgroundColor: `${getThoughtColor(thought.thought_type)}10`,
            padding: '2px 6px',
            borderRadius: '4px',
            fontSize: '0.75rem',
            marginRight: '8px'
          }}>
            {thought.thought_type}
          </span>
          <span style={{ color: '#e2e8f0' }}>{thought.message}</span>
        </div>
      ))}
      <div ref={endOfListRef} />
    </div>
  );
}