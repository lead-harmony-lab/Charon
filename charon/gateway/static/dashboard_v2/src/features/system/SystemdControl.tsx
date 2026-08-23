import React, { useState, useEffect } from 'react';
import { authFetch } from '../../core/api/client';

interface UnitStatus {
  name: string;
  active: boolean;
  subState: string;
  uptime: string;
}

export function SystemdControl() {
  const [units, setUnits] = useState<UnitStatus[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchUnits = async () => {
    try {
      const res = await authFetch('/v1/system/units');
      if (res.ok) {
        const data = await res.json();
        setUnits(data.units || []);
      }
    } catch (err) {
      console.error('Failed to fetch systemd units', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUnits();
  }, []);

  const handleAction = async (unitName: string, action: 'start' | 'stop' | 'restart') => {
    try {
      await authFetch(`/v1/system/units/${unitName}/${action}`, { method: 'POST' });
      fetchUnits();
    } catch (err) {
      console.error(`Failed to ${action} unit ${unitName}`, err);
    }
  };

  if (loading) return <p style={{ color: '#94a3b8' }}>Loading system services...</p>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {units.map((unit) => (
        <div key={unit.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1rem 1.25rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontWeight: 'bold', color: '#f8fafc' }}>{unit.name}</span>
              <span style={{ fontSize: '0.75rem', padding: '2px 6px', borderRadius: '4px', backgroundColor: unit.active ? '#10b98120' : '#ef444420', color: unit.active ? '#10b981' : '#ef4444', border: `1px solid ${unit.active ? '#10b981' : '#ef4444'}` }}>
                {unit.subState}
              </span>
            </div>
            <span style={{ fontSize: '0.8rem', color: '#64748b' }}>Uptime: {unit.uptime}</span>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button onClick={() => handleAction(unit.name, 'restart')} style={{ backgroundColor: '#334155', color: '#f8fafc', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>Restart</button>
            <button onClick={() => handleAction(unit.name, unit.active ? 'stop' : 'start')} style={{ backgroundColor: unit.active ? '#ef4444' : '#10b981', color: '#0f172a', fontWeight: 'bold', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>
              {unit.active ? 'Stop' : 'Start'}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}