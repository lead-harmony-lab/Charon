import React, { useEffect, useState } from 'react';
import { wsClient, CharonWSFrame } from '../../core/ws/CharonStream';
import { DagVisualizer } from './DagVisualizer';
import { BlackboardTrace } from './BlackboardTrace';

export interface StepRecord {
  id: string;
  step: string;
  agent_name: string;
  timestamp: string;
  status?: string;
}

export interface ThoughtRecord {
  id: string;
  agent_name: string;
  thought_type: string;
  message: string;
  timestamp: string;
}

export function BlackboardObserver() {
  const [steps, setSteps] = useState<StepRecord[]>([]);
  const [thoughts, setThoughts] = useState<ThoughtRecord[]>([]);

  useEffect(() => {
    // Listen for high-level execution steps
    const unsubStep = wsClient.subscribe('step', (frame: CharonWSFrame) => {
      setSteps((prev) => [...prev, {
        id: crypto.randomUUID(),
        step: frame.data?.step || 'Unknown step executed',
        agent_name: frame.agent_name || 'System',
        timestamp: frame.timestamp || new Date().toISOString(),
        status: frame.data?.status || 'completed'
      }]);
    });

    // Listen for granular internal reasoning (CoT)
    const unsubThought = wsClient.subscribe('thought_record', (frame: CharonWSFrame) => {
      setThoughts((prev) => [...prev, {
        id: frame.data?.record_id || crypto.randomUUID(),
        agent_name: frame.agent_name || 'System',
        thought_type: frame.data?.thought_type || 'ANALYSIS',
        message: frame.data?.message || '',
        timestamp: frame.timestamp || new Date().toISOString(),
      }]);
    });

    return () => {
      unsubStep();
      unsubThought();
    };
  }, []);

  return (
    <div style={{ display: 'flex', height: '100%', padding: '1.5rem', gap: '1.5rem', boxSizing: 'border-box' }}>
      {/* Left Pane: Execution Timeline */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', overflow: 'hidden' }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid #334155', backgroundColor: '#0f172a' }}>
          <h2 style={{ margin: 0, fontSize: '1.1rem', color: '#f8fafc' }}>Execution DAG</h2>
        </div>
        <DagVisualizer steps={steps} />
      </div>

      {/* Right Pane: Live Telemetry & Thoughts */}
      <div style={{ flex: 1.5, display: 'flex', flexDirection: 'column', backgroundColor: '#1e293b', borderRadius: '8px', border: '1px solid #334155', overflow: 'hidden' }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid #334155', backgroundColor: '#0f172a' }}>
          <h2 style={{ margin: 0, fontSize: '1.1rem', color: '#f8fafc' }}>Blackboard Trace</h2>
        </div>
        <BlackboardTrace thoughts={thoughts} />
      </div>
    </div>
  );
}