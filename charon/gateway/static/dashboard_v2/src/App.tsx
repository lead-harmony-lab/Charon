import React, { useEffect, useState, useRef } from 'react';
import { wsClient } from './core/ws/CharonStream';
import { getApiKey } from './core/api/client';
import { BlackboardObserver } from './features/coordinator/BlackboardObserver';

// We will build these placeholder components next
import { AgentStudio } from './features/agents/AgentStudio';
import { IntegrationMatrix } from './features/system/IntegrationMatrix';
import { KnowledgeBase } from './features/docs/KnowledgeBase';
import { DevJournal } from './features/journal/DevJournal';

type TabID = 'blackboard' | 'studio' | 'matrix' | 'docs' | 'journal';

export default function App() {
  const [connected, setConnected] = useState(false);
  const [activeTab, setActiveTab] = useState<TabID>('blackboard');
  const isConnecting = useRef(false);

  useEffect(() => {
    if (isConnecting.current) return;
    isConnecting.current = true;

    const apiKey = getApiKey();

    const unsubscribe = wsClient.subscribe('connection_status', (frame) => {
      setConnected(frame.data?.connected || false);
    });

    wsClient.connect(apiKey);

    return () => {
      unsubscribe();
      wsClient.disconnect();
      isConnecting.current = false;
    };
  }, []);

  const renderActiveTab = () => {
    switch (activeTab) {
      case 'blackboard': return <BlackboardObserver />;
      case 'studio': return <AgentStudio />;
      case 'matrix': return <IntegrationMatrix />;
      case 'docs': return <KnowledgeBase />;
      case 'journal': return <DevJournal />;
      default: return <BlackboardObserver />;
    }
  };

  return (
    <div style={{ display: 'flex', height: '100vh', backgroundColor: '#0f172a', color: '#f8fafc', fontFamily: 'sans-serif' }}>

      {/* Sidebar Navigation */}
      <nav style={{ width: '250px', backgroundColor: '#1e293b', borderRight: '1px solid #334155', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '1.5rem', borderBottom: '1px solid #334155' }}>
          <h1 style={{ margin: '0 0 0.5rem 0', fontSize: '1.2rem', color: '#38bdf8' }}>Charon Control</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem' }}>
            <div style={{
              width: '10px', height: '10px', borderRadius: '50%',
              backgroundColor: connected ? '#10b981' : '#ef4444',
              boxShadow: connected ? '0 0 8px #10b981' : 'none',
              transition: 'all 0.3s ease'
            }} />
            <span style={{ color: connected ? '#10b981' : '#ef4444' }}>
              {connected ? 'Daemon Connected' : 'Disconnected'}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', padding: '1rem 0' }}>
          <TabButton id="blackboard" label="Blackboard" active={activeTab} onClick={setActiveTab} />
          <TabButton id="studio" label="Agent Studio" active={activeTab} onClick={setActiveTab} />
          <TabButton id="matrix" label="Integration Matrix" active={activeTab} onClick={setActiveTab} />
          <TabButton id="docs" label="Knowledge Base" active={activeTab} onClick={setActiveTab} />
          <TabButton id="journal" label="Dev Journal" active={activeTab} onClick={setActiveTab} />
        </div>
      </nav>

      {/* Main Content Area */}
      <main style={{ flex: 1, overflowY: 'auto' }}>
        {renderActiveTab()}
      </main>
    </div>
  );
}

// Reusable Tab Button Component
const TabButton = ({ id, label, active, onClick }: { id: TabID, label: string, active: TabID, onClick: (id: TabID) => void }) => {
  const isActive = active === id;
  return (
    <button
      onClick={() => onClick(id)}
      style={{
        backgroundColor: isActive ? '#334155' : 'transparent',
        color: isActive ? '#38bdf8' : '#94a3b8',
        border: 'none',
        textAlign: 'left',
        padding: '1rem 1.5rem',
        cursor: 'pointer',
        fontSize: '1rem',
        borderLeft: isActive ? '4px solid #38bdf8' : '4px solid transparent',
        transition: 'all 0.2s ease'
      }}
    >
      {label}
    </button>
  );
};