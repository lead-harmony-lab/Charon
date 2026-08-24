/**
 * @file src/features/diagnostics/DagVisualizer.tsx
 * @description
 */
import React from 'react';
import { StepRecord } from './BlackboardObserver';

export function DagVisualizer({ steps }: { steps: StepRecord[] }) {
  if (steps.length === 0) {
    return (
      <div style={{ padding: '2rem', color: '#64748b', textAlign: 'center', fontStyle: 'italic' }}>
        Awaiting task execution...
      </div>
    );
  }

  return (
    <div style={{ padding: '1.5rem', overflowY: 'auto', flex: 1 }}>
      {steps.map((step, index) => (
        <div key={step.id} style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', position: 'relative' }}>
          {/* Timeline Line connecting nodes */}
          {index !== steps.length - 1 && (
            <div style={{ position: 'absolute', left: '11px', top: '24px', bottom: '-24px', width: '2px', backgroundColor: '#334155' }} />
          )}

          {/* Node Dot */}
          <div style={{
            width: '24px', height: '24px', borderRadius: '50%', backgroundColor: '#0f172a',
            border: '2px solid #38bdf8', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1
          }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#38bdf8' }} />
          </div>

          {/* Step Details */}
          <div style={{ flex: 1, backgroundColor: '#0f172a', padding: '1rem', borderRadius: '6px', border: '1px solid #334155' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.85rem', color: '#38bdf8', fontWeight: 'bold' }}>{step.agent_name}</span>
              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                {new Date(step.timestamp).toLocaleTimeString()}
              </span>
            </div>
            <div style={{ fontSize: '0.95rem', color: '#cbd5e1' }}>
              {step.step}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}