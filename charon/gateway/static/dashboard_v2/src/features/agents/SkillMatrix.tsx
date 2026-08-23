import React, { useEffect, useState, useCallback } from 'react';
import { authFetch } from '../../core/api/client';
import { wsClient } from '../../core/ws/CharonStream';

interface Skill {
  skill_type?: string;
  action_name: string;
  enabled?: boolean;
}

interface Agent {
  name?: string;
  description?: string;
  priority_weight?: number;
  skills?: Skill[];
}

type AgentMap = Record<string, Agent>;

export function SkillMatrix() {
  const [agents, setAgents] = useState<AgentMap>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    try {
      const res = await authFetch('/v1/router/agents');
      if (!res.ok) {
        throw new Error(`Server returned ${res.status}: ${res.statusText}`);
      }
      const data = await res.json();
      setAgents(data.agents || {});
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load agents');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAgents();

    // Auto-refresh matrix on real-time event bus updates
    const unsubUpdated = wsClient.subscribe('router_agent_updated', fetchAgents);
    const unsubToggled = wsClient.subscribe('router_tool_toggled', fetchAgents);

    return () => {
      unsubUpdated();
      unsubToggled();
    };
  }, [fetchAgents]);

  const handleWeightChange = async (agentId: string, weight: string) => {
    const parsedWeight = parseFloat(weight);
    if (isNaN(parsedWeight)) return;

    try {
      await authFetch(`/v1/router/agents/${agentId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ priority_weight: parsedWeight }),
      });
      fetchAgents();
    } catch (err) {
      console.error(`Failed to update weight for ${agentId}:`, err);
    }
  };

  const handleToggleTool = async (agentId: string, toolName: string, enabled: boolean) => {
    try {
      await authFetch(`/v1/router/agents/${agentId}/tools`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool_name: toolName, enabled }),
      });
      fetchAgents();
    } catch (err) {
      console.error(`Failed to toggle tool ${toolName} for ${agentId}:`, err);
    }
  };

  const groupSkills = (skills: Skill[]) => {
    return skills.reduce((acc, skill) => {
      const type = skill.skill_type || 'General';
      if (!acc[type]) acc[type] = [];
      acc[type].push(skill);
      return acc;
    }, {} as Record<string, Skill[]>);
  };

  return (
    <div style={{ marginTop: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#f8fafc' }}>Agent Skill Matrix</h2>
        <button
          onClick={fetchAgents}
          style={{
            backgroundColor: '#334155',
            color: '#f8fafc',
            border: 'none',
            padding: '0.4rem 0.8rem',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '0.85rem',
          }}
        >
          Refresh
        </button>
      </div>

      {loading && <p style={{ color: '#94a3b8' }}>Loading registered router agents...</p>}
      {error && <p style={{ color: '#ef4444' }}>Error: {error}</p>}

      {!loading && !error && Object.keys(agents).length === 0 && (
        <div style={{ padding: '1.5rem', backgroundColor: '#1e293b', borderRadius: '8px', color: '#94a3b8' }}>
          No router agents currently registered.
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' }}>
        {Object.entries(agents).map(([agentId, agent]) => {
          const groupedSkills = groupSkills(agent.skills || []);

          return (
            <div
              key={agentId}
              style={{
                backgroundColor: '#1e293b',
                borderRadius: '8px',
                border: '1px solid #334155',
                padding: '1.25rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#f8fafc' }}>{agent.name || agentId}</h3>
                  {agent.description && (
                    <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
                      {agent.description}
                    </p>
                  )}
                </div>

                <label style={{ fontSize: '0.8rem', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  Weight:
                  <input
                    type="number"
                    step="0.1"
                    min="0.1"
                    max="5.0"
                    defaultValue={agent.priority_weight ?? 1.0}
                    onBlur={(e) => handleWeightChange(agentId, e.target.value)}
                    style={{
                      width: '50px',
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      color: '#38bdf8',
                      borderRadius: '4px',
                      padding: '0.2rem 0.4rem',
                      textAlign: 'center',
                      fontSize: '0.85rem',
                    }}
                  />
                </label>
              </div>

              <div>
                <strong style={{ fontSize: '0.85rem', color: '#f8fafc' }}>Tools by Category:</strong>
                {agent.skills && agent.skills.length > 0 ? (
                  Object.entries(groupedSkills).map(([type, typeSkills]) => (
                    <div key={type} style={{ marginTop: '8px' }}>
                      <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: '#38bdf8', marginBottom: '4px', fontWeight: 600 }}>
                        {type}
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {typeSkills.map((skill) => (
                          <label
                            key={skill.action_name}
                            style={{
                              fontSize: '0.8rem',
                              backgroundColor: '#0f172a',
                              color: '#cbd5e1',
                              padding: '0.25rem 0.5rem',
                              borderRadius: '4px',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '6px',
                              cursor: 'pointer',
                              border: '1px solid #334155',
                            }}
                          >
                            <input
                              type="checkbox"
                              defaultChecked={skill.enabled !== false}
                              onChange={(e) => handleToggleTool(agentId, skill.action_name, e.target.checked)}
                            />
                            {skill.action_name}
                          </label>
                        ))}
                      </div>
                    </div>
                  ))
                ) : (
                  <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: '#64748b', fontStyle: 'italic' }}>
                    No tools equipped
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}