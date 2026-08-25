/**
 * @file src/features/docs/KnowledgeBase.tsx
 */
import React from 'react';
import { Routes, Route, Navigate, NavLink } from 'react-router-dom';
import { AdrViewer } from './AdrViewer';
import { SpecsViewer } from './SpecsViewer';
import { ManualViewer } from './ManualViewer/ManualViewer';

export function KnowledgeBase() {
  return (
    <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', height: '100%', boxSizing: 'border-box' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e293b', padding: '1rem 1.5rem', borderRadius: '8px', border: '1px solid #334155' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#f8fafc' }}>Knowledge Base</h2>
          <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
            Access system specifications, protocol definitions, Architectural Decision Records (ADRs), and User Manuals.
          </p>
        </div>

        <div style={{ display: 'flex', backgroundColor: '#0f172a', borderRadius: '6px', padding: '4px', border: '1px solid #334155' }}>
          {/* We don't use 'end' on manual so that deep links like /docs/manual/123 keep the Manual tab active */}
          <SubTabLink to="/docs/adrs" label="ADR Index" />
          <SubTabLink to="/docs/specs" label="System Specs" />
          <SubTabLink to="/docs/manual" label="User Manual" />
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        <Routes>
          <Route path="/" element={<Navigate to="adrs" replace />} />
          <Route path="adrs/*" element={<AdrViewer />} />
          <Route path="specs/*" element={<SpecsViewer />} />
          <Route path="manual">
            {/* Base manual route and deep link route */}
            <Route index element={<ManualViewer />} />
            <Route path=":nodeId" element={<ManualViewer />} />
          </Route>
        </Routes>
      </div>
    </div>
  );
}

const SubTabLink = ({ to, label }: { to: string; label: string }) => (
  <NavLink
    to={to}
    // react-router-dom v6 automatically detects if the current URL matches this path
    style={({ isActive }) => ({
      padding: '0.4rem 1rem',
      borderRadius: '4px',
      textDecoration: 'none',
      backgroundColor: isActive ? '#38bdf8' : 'transparent',
      color: isActive ? '#0f172a' : '#94a3b8',
      fontWeight: isActive ? 'bold' : 'normal',
      fontSize: '0.85rem',
      transition: 'all 0.2s ease'
    })}
  >
    {label}
  </NavLink>
);