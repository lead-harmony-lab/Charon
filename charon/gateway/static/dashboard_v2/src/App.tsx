/**
 * @file src/App.tsx
 * @description Main application entry point utilizing React Router for SPA navigation.
 */
import React, { useEffect, useState, useRef } from 'react';
// 1. Change BrowserRouter to HashRouter here:
import { HashRouter, Routes, Route, Navigate, NavLink, useLocation } from 'react-router-dom';
import { wsClient } from './core/ws/CharonStream';
import { getApiKey } from './core/api/client';

import { SystemDiagnostics } from './features/diagnostics/SystemDiagnostics';
import { AgentStudio } from './features/agents/AgentStudio';
import { IntegrationMatrix } from './features/system/IntegrationMatrix';
import { KnowledgeBase } from './features/docs/KnowledgeBase';
import { DevJournal } from './features/journal/DevJournal';

function AppLayout() {
  const [connected, setConnected] = useState(false);
  const isConnecting = useRef(false);
  const location = useLocation();

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

  return (
    <div style={{ display: 'flex', height: '100vh', backgroundColor: '#0f172a', color: '#f8fafc', fontFamily: 'sans-serif' }}>
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
          <TabButton to="/diagnostics" label="Diagnostics" />
          <TabButton to="/studio" label="Agent Studio" />
          <TabButton to="/matrix" label="Integration Matrix" />
          <TabButton to="/docs" label="Knowledge Base" isActive={location.pathname.startsWith('/docs')} />
          <TabButton to="/journal" label="Dev Journal" isActive={location.pathname.startsWith('/journal')} />
        </div>
      </nav>

      <main style={{ flex: 1, overflowY: 'auto' }}>
        <Routes>
          <Route path="/" element={<Navigate to="/diagnostics" replace />} />
          <Route path="/diagnostics" element={<SystemDiagnostics />} />
          <Route path="/studio" element={<AgentStudio />} />
          <Route path="/matrix" element={<IntegrationMatrix />} />
          <Route path="/docs/*" element={<KnowledgeBase />} />
          <Route path="/journal/*" element={<DevJournal />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  // 2. Wrap the application in HashRouter instead of BrowserRouter
  return (
    <HashRouter>
      <AppLayout />
    </HashRouter>
  );
}

const TabButton = ({ to, label, isActive: forceActive }: { to: string, label: string, isActive?: boolean }) => {
  return (
    <NavLink
      to={to}
      style={({ isActive }) => {
        const active = forceActive !== undefined ? forceActive : isActive;
        return {
          backgroundColor: active ? '#334155' : 'transparent',
          color: active ? '#38bdf8' : '#94a3b8',
          textDecoration: 'none',
          padding: '1rem 1.5rem',
          fontSize: '1rem',
          borderLeft: active ? '4px solid #38bdf8' : '4px solid transparent',
          transition: 'all 0.2s ease',
          display: 'block'
        };
      }}
    >
      {label}
    </NavLink>
  );
};