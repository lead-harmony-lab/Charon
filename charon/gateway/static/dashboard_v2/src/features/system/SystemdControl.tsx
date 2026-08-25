/**
 * @file src/features/system/SystemdControl.tsx
 * @description Charon Systemd Service Management Panel with scoped monitoring, file editing, and registry management.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../../core/api/client';

export type ServiceScope = 'system' | 'user';

export interface UnitStatus {
  name: string;
  active: boolean;
  subState: string;
  scope: ServiceScope;
  uptime?: string;
  description?: string;
  loadState?: string;
}

interface EditorState {
  name: string;
  scope: ServiceScope;
  content: string;
}

export function SystemdControl() {
  const [units, setUnits] = useState<UnitStatus[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [actionPending, setActionPending] = useState<Record<string, string>>({});
  const [autoRefresh, setAutoRefresh] = useState<boolean>(false);

  // New Service Registration State
  const [newUnitName, setNewUnitName] = useState<string>('');
  const [newUnitScope, setNewUnitScope] = useState<ServiceScope>('user');
  const [isRegistering, setIsRegistering] = useState<boolean>(false);

  // Service File Editor State
  const [editorState, setEditorState] = useState<EditorState | null>(null);
  const [editorLoading, setEditorLoading] = useState<boolean>(false);
  const [editorSaving, setEditorSaving] = useState<boolean>(false);

  const fetchUnits = useCallback(async () => {
    try {
      setError(null);
      const res = await authFetch('/v1/system/units');
      if (res.ok) {
        const data = await res.json();
        setUnits(data.units || []);
      } else if (res.status === 404) {
        setError('Systemd control endpoints (/v1/system/units) are not yet implemented on the backend.');
        setUnits([]);
      } else {
        setError(`Server returned status ${res.status}: ${res.statusText}`);
      }
    } catch (err: any) {
      console.error('Failed to fetch systemd units', err);
      setError(err.message || 'Failed to connect to backend systemd endpoint.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUnits();
  }, [fetchUnits]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchUnits();
    }, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchUnits]);

  // Register a new service to settings file
  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUnitName.trim()) return;

    setIsRegistering(true);
    try {
      const res = await authFetch('/v1/system/registered-units', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newUnitName.trim(), scope: newUnitScope }),
      });
      if (res.ok) {
        setNewUnitName('');
        await fetchUnits();
      } else {
        setError(`Failed to register unit: ${res.statusText}`);
      }
    } catch (err: any) {
      setError(`Failed to register unit: ${err.message}`);
    } finally {
      setIsRegistering(false);
    }
  };

  // Unregister service from settings file
  const handleDeregister = async (unitName: string) => {
    try {
      const res = await authFetch(`/v1/system/registered-units/${encodeURIComponent(unitName)}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        await fetchUnits();
      }
    } catch (err) {
      console.error(`Failed to deregister ${unitName}`, err);
    }
  };

  // Lifecycle control (Start, Stop, Restart, Reload)
  const handleAction = async (unitName: string, scope: ServiceScope, action: 'start' | 'stop' | 'restart' | 'reload') => {
    setActionPending((prev) => ({ ...prev, [unitName]: action }));
    try {
      const res = await authFetch(`/v1/system/units/${encodeURIComponent(unitName)}/${action}?scope=${scope}`, {
        method: 'POST',
      });
      if (!res.ok) {
        console.error(`Action ${action} on ${unitName} failed with status ${res.status}`);
      }
      await fetchUnits();
    } catch (err) {
      console.error(`Failed to ${action} unit ${unitName}`, err);
    } finally {
      setActionPending((prev) => {
        const next = { ...prev };
        delete next[unitName];
        return next;
      });
    }
  };

  // Load service file content for editor
  const handleOpenEditor = async (unit: UnitStatus) => {
    setEditorLoading(true);
    try {
      const res = await authFetch(`/v1/system/units/${encodeURIComponent(unit.name)}/content?scope=${unit.scope}`);
      if (res.ok) {
        const data = await res.json();
        setEditorState({ name: unit.name, scope: unit.scope, content: data.content || '' });
      } else {
        setError(`Failed to fetch file content for ${unit.name}`);
      }
    } catch (err: any) {
      setError(`Failed to read service file: ${err.message}`);
    } finally {
      setEditorLoading(false);
    }
  };

  // Save updated service file content
  const handleSaveFile = async () => {
    if (!editorState) return;
    setEditorSaving(true);
    try {
      const res = await authFetch(`/v1/system/units/${encodeURIComponent(editorState.name)}/content?scope=${editorState.scope}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editorState.content }),
      });
      if (res.ok) {
        setEditorState(null);
        await fetchUnits();
      } else {
        setError(`Failed to save file content: ${res.statusText}`);
      }
    } catch (err: any) {
      setError(`Failed to save service file: ${err.message}`);
    } finally {
      setEditorSaving(false);
    }
  };

  const filteredUnits = units.filter(
    (u) =>
      u.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (u.description && u.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const activeCount = units.filter((u) => u.active).length;
  const inactiveCount = units.length - activeCount;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', height: '100%' }}>
      {/* Registration Bar */}
      <form
        onSubmit={handleRegister}
        style={{
          display: 'flex',
          gap: '0.75rem',
          alignItems: 'center',
          backgroundColor: '#1e293b',
          border: '1px solid #334155',
          borderRadius: '8px',
          padding: '0.85rem 1.25rem',
        }}
      >
        <span style={{ color: '#f8fafc', fontSize: '0.85rem', fontWeight: 600 }}>Register Service:</span>
        <input
          type="text"
          placeholder="e.g. charon-worker.service"
          value={newUnitName}
          onChange={(e) => setNewUnitName(e.target.value)}
          style={{
            flex: 1,
            backgroundColor: '#0f172a',
            border: '1px solid #334155',
            color: '#f8fafc',
            padding: '0.4rem 0.75rem',
            borderRadius: '4px',
            fontSize: '0.85rem',
          }}
        />
        <select
          value={newUnitScope}
          onChange={(e) => setNewUnitScope(e.target.value as ServiceScope)}
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid #334155',
            color: '#f8fafc',
            padding: '0.4rem 0.75rem',
            borderRadius: '4px',
            fontSize: '0.85rem',
          }}
        >
          <option value="user">User Space (--user)</option>
          <option value="system">System Space (--system)</option>
        </select>
        <button
          type="submit"
          disabled={isRegistering || !newUnitName.trim()}
          style={{
            backgroundColor: '#0284c7',
            color: '#fff',
            border: 'none',
            padding: '0.4rem 0.85rem',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '0.85rem',
            fontWeight: 600,
          }}
        >
          {isRegistering ? 'Adding...' : 'Add Service'}
        </button>
      </form>

      {/* Header Controls Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1rem 1.25rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#f8fafc' }}>Charon Monitored Services</h3>
          {units.length > 0 && (
            <div style={{ display: 'flex', gap: '0.5rem', fontSize: '0.75rem' }}>
              <span style={{ backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#34d399', border: '1px solid rgba(52, 211, 153, 0.3)', padding: '2px 8px', borderRadius: '4px', fontWeight: 600 }}>
                {activeCount} Active
              </span>
              <span style={{ backgroundColor: 'rgba(148, 163, 184, 0.15)', color: '#94a3b8', border: '1px solid #334155', padding: '2px 8px', borderRadius: '4px', fontWeight: 600 }}>
                {inactiveCount} Inactive
              </span>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <input
            type="text"
            placeholder="Filter services..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', padding: '0.4rem 0.75rem', borderRadius: '4px', fontSize: '0.85rem', width: '200px' }}
          />

          <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: '#cbd5e1', fontSize: '0.85rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              style={{ accentColor: '#38bdf8' }}
            />
            Auto-poll
          </label>

          <button
            onClick={fetchUnits}
            disabled={loading}
            style={{ backgroundColor: '#334155', color: '#f8fafc', border: '1px solid #475569', padding: '0.4rem 0.85rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600 }}
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Error Fallback Banner */}
      {error && (
        <div style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '8px', padding: '1rem 1.25rem', color: '#f87171', fontSize: '0.9rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <strong style={{ display: 'block', marginBottom: '0.25rem' }}>Endpoint Error</strong>
            <span>{error}</span>
          </div>
          <button onClick={fetchUnits} style={{ backgroundColor: '#ef4444', color: '#fff', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 'bold' }}>
            Retry
          </button>
        </div>
      )}

      {/* Loading State */}
      {loading && !units.length && !error && (
        <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>
          Loading registered systemd services...
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && filteredUnits.length === 0 && (
        <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '2rem', textAlign: 'center', color: '#64748b' }}>
          {units.length === 0 ? 'No services currently registered to watch list.' : 'No units match your search filter.'}
        </div>
      )}

      {/* Unit Status List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {filteredUnits.map((unit) => {
          const isPending = !!actionPending[unit.name];
          const currentPendingAction = actionPending[unit.name];

          return (
            <div
              key={unit.name}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '8px',
                padding: '1rem 1.25rem',
                opacity: isPending ? 0.7 : 1,
                transition: 'all 0.15s ease-in-out',
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  <span style={{
                    height: '8px',
                    width: '8px',
                    borderRadius: '50%',
                    backgroundColor: unit.active ? '#10b981' : '#ef4444',
                    boxShadow: unit.active ? '0 0 8px #10b981' : 'none'
                  }} />
                  <code style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.95rem', fontFamily: 'monospace' }}>
                    {unit.name}
                  </code>

                  {/* Space Scope Indicator */}
                  <span
                    style={{
                      fontSize: '0.65rem',
                      fontWeight: 700,
                      padding: '2px 6px',
                      borderRadius: '4px',
                      backgroundColor: unit.scope === 'user' ? 'rgba(56, 189, 248, 0.15)' : 'rgba(168, 85, 247, 0.15)',
                      color: unit.scope === 'user' ? '#38bdf8' : '#c084fc',
                      border: `1px solid ${unit.scope === 'user' ? 'rgba(56, 189, 248, 0.3)' : 'rgba(168, 85, 247, 0.3)'}`,
                      textTransform: 'uppercase',
                    }}
                  >
                    {unit.scope} space
                  </span>

                  {/* Substate Indicator */}
                  <span
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      padding: '2px 6px',
                      borderRadius: '4px',
                      backgroundColor: unit.active ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                      color: unit.active ? '#34d399' : '#f87171',
                      border: `1px solid ${unit.active ? 'rgba(52, 211, 153, 0.3)' : 'rgba(248, 113, 113, 0.3)'}`,
                      textTransform: 'uppercase',
                    }}
                  >
                    {unit.subState || (unit.active ? 'running' : 'dead')}
                  </span>
                </div>

                {unit.description && (
                  <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>{unit.description}</span>
                )}

                {unit.uptime && (
                  <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Uptime: {unit.uptime}</span>
                )}
              </div>

              {/* Action Controls */}
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <button
                  onClick={() => handleAction(unit.name, unit.scope, 'reload')}
                  disabled={isPending}
                  style={{ backgroundColor: '#334155', color: '#cbd5e1', border: '1px solid #475569', padding: '0.4rem 0.65rem', borderRadius: '4px', cursor: isPending ? 'not-allowed' : 'pointer', fontSize: '0.8rem', fontWeight: 600 }}
                >
                  Reload
                </button>
                <button
                  onClick={() => handleAction(unit.name, unit.scope, 'restart')}
                  disabled={isPending}
                  style={{ backgroundColor: '#334155', color: '#f8fafc', border: '1px solid #475569', padding: '0.4rem 0.75rem', borderRadius: '4px', cursor: isPending ? 'not-allowed' : 'pointer', fontSize: '0.85rem', fontWeight: 600 }}
                >
                  {currentPendingAction === 'restart' ? 'Restarting...' : 'Restart'}
                </button>
                <button
                  onClick={() => handleAction(unit.name, unit.scope, unit.active ? 'stop' : 'start')}
                  disabled={isPending}
                  style={{
                    backgroundColor: unit.active ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                    color: unit.active ? '#f87171' : '#34d399',
                    border: `1px solid ${unit.active ? 'rgba(239, 68, 68, 0.4)' : 'rgba(16, 185, 129, 0.4)'}`,
                    fontWeight: 'bold',
                    padding: '0.4rem 0.75rem',
                    borderRadius: '4px',
                    cursor: isPending ? 'not-allowed' : 'pointer',
                    fontSize: '0.85rem',
                  }}
                >
                  {isPending ? `${currentPendingAction}...` : unit.active ? 'Stop' : 'Start'}
                </button>

                <button
                  onClick={() => handleOpenEditor(unit)}
                  disabled={editorLoading}
                  style={{ backgroundColor: '#1e293b', color: '#38bdf8', border: '1px solid #38bdf8', padding: '0.4rem 0.65rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 600 }}
                >
                  Edit File
                </button>

                <button
                  onClick={() => handleDeregister(unit.name)}
                  title="Remove from Charon Dashboard"
                  style={{ backgroundColor: 'transparent', color: '#64748b', border: 'none', padding: '0.4rem', cursor: 'pointer', fontSize: '1rem' }}
                >
                  ✕
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Service File Editor Modal */}
      {editorState && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(15, 23, 42, 0.8)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }}>
          <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1.5rem', width: '700px', maxWidth: '90vw', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h4 style={{ margin: 0, color: '#f8fafc', fontSize: '1rem' }}>
                Editing {editorState.name} ({editorState.scope} space)
              </h4>
              <button onClick={() => setEditorState(null)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '1.2rem' }}>
                ✕
              </button>
            </div>

            <textarea
              rows={16}
              value={editorState.content}
              onChange={(e) => setEditorState({ ...editorState, content: e.target.value })}
              style={{
                backgroundColor: '#0f172a',
                border: '1px solid #334155',
                color: '#38bdf8',
                fontFamily: 'monospace',
                fontSize: '0.85rem',
                padding: '0.75rem',
                borderRadius: '4px',
                resize: 'vertical',
              }}
            />

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                onClick={() => setEditorState(null)}
                style={{ backgroundColor: '#334155', color: '#f8fafc', border: 'none', padding: '0.5rem 1rem', borderRadius: '4px', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveFile}
                disabled={editorSaving}
                style={{ backgroundColor: '#10b981', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '4px', cursor: 'pointer', fontWeight: 600 }}
              >
                {editorSaving ? 'Saving & Reloading...' : 'Save & Daemon Reload'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}