import React, { useState, useEffect } from 'react';
import { authFetch } from '../../core/api/client';

interface CreateDocModalProps {
  isOpen: boolean;
  onClose: () => void;
  docType: 'adr' | 'spec';
  onSuccess: () => void;
}

interface FormErrors {
  id?: string;
  titleOrName?: string;
  statusOrVersion?: string;
  summary?: string;
  content?: string;
}

const SEMVER_REGEX = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const ID_REGEX = /^[A-Z0-9_-]+$/i;

export function CreateDocModal({ isOpen, onClose, docType, onSuccess }: CreateDocModalProps) {
  const [id, setId] = useState('');
  const [titleOrName, setTitleOrName] = useState('');
  const [statusOrVersion, setStatusOrVersion] = useState('');
  const [summary, setSummary] = useState('');
  const [content, setContent] = useState('');

  const [errors, setErrors] = useState<FormErrors>({});
  const [statusMsg, setStatusMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Reset defaults on modal toggle or docType change
  useEffect(() => {
    if (isOpen) {
      setId(docType === 'adr' ? 'ADR-' : 'SPEC-');
      setTitleOrName('');
      setStatusOrVersion(docType === 'adr' ? 'PROPOSED' : '1.0.0');
      setSummary('');
      setContent('');
      setErrors({});
      setStatusMsg('');
    }
  }, [isOpen, docType]);

  if (!isOpen) return null;

  const validate = (): boolean => {
    const newErrors: FormErrors = {};

    // 1. ID Validation
    if (!id.trim()) {
      newErrors.id = 'ID is required.';
    } else if (!ID_REGEX.test(id)) {
      newErrors.id = 'ID must contain only letters, numbers, hyphens, and underscores.';
    } else if (docType === 'adr' && !id.toUpperCase().startsWith('ADR-')) {
      newErrors.id = 'ADR ID should begin with "ADR-" (e.g. ADR-001).';
    } else if (docType === 'spec' && !id.toUpperCase().startsWith('SPEC-')) {
      newErrors.id = 'Spec ID should begin with "SPEC-" (e.g. SPEC-001).';
    }

    // 2. Title / Name Validation
    if (!titleOrName.trim()) {
      newErrors.titleOrName = `${docType === 'adr' ? 'Title' : 'Name'} is required.`;
    } else if (titleOrName.trim().length < 3) {
      newErrors.titleOrName = 'Title must be at least 3 characters.';
    }

    // 3. Status / Version Validation
    if (docType === 'spec') {
      if (!statusOrVersion.trim()) {
        newErrors.statusOrVersion = 'Version is required.';
      } else if (!SEMVER_REGEX.test(statusOrVersion)) {
        newErrors.statusOrVersion = 'Must follow Semantic Versioning (e.g. 1.0.0).';
      }
    }

    // 4. Summary Validation (ADR only)
    if (docType === 'adr' && summary.trim() && summary.trim().length < 5) {
      newErrors.summary = 'Summary must be at least 5 characters if provided.';
    }

    // 5. Content Validation
    if (!content.trim()) {
      newErrors.content = 'Content is required.';
    } else if (content.trim().length < 10) {
      newErrors.content = 'Document content must be at least 10 characters.';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    setStatusMsg('Creating document...');

    const endpoint = docType === 'adr' ? '/v1/docs/adrs' : '/v1/docs/specs';
    const body =
      docType === 'adr'
        ? {
            id: id.trim(),
            title: titleOrName.trim(),
            status: statusOrVersion,
            date: new Date().toISOString().split('T')[0],
            summary: summary.trim(),
            content: content.trim(),
          }
        : {
            id: id.trim(),
            name: titleOrName.trim(),
            version: statusOrVersion.trim(),
            content: content.trim(),
          };

    try {
      const res = await authFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (res.ok) {
        setStatusMsg('Created successfully!');
        onSuccess();
        onClose();
      } else {
        const data = await res.json().catch(() => ({}));
        setStatusMsg(data.error || 'Failed to create document.');
      }
    } catch (err) {
      setStatusMsg('Network error creating document.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}>
      <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '1.5rem', width: '520px', maxWidth: '90vw', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <h3 style={{ margin: 0, color: '#f8fafc', fontSize: '1.1rem' }}>
          Create New {docType === 'adr' ? 'Architecture Decision Record' : 'System Spec'}
        </h3>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
          {/* Document ID */}
          <div>
            <input
              type="text"
              placeholder={docType === 'adr' ? 'ID (e.g. ADR-001)' : 'ID (e.g. SPEC-001)'}
              value={id}
              onChange={(e) => setId(e.target.value)}
              style={{ width: '100%', backgroundColor: '#0f172a', border: `1px solid ${errors.id ? '#ef4444' : '#334155'}`, color: '#f8fafc', padding: '0.5rem 0.75rem', borderRadius: '4px', boxSizing: 'border-box' }}
            />
            {errors.id && <span style={{ color: '#ef4444', fontSize: '0.75rem', marginTop: '2px', display: 'block' }}>{errors.id}</span>}
          </div>

          {/* Title or Spec Name */}
          <div>
            <input
              type="text"
              placeholder={docType === 'adr' ? 'Title' : 'Spec Name'}
              value={titleOrName}
              onChange={(e) => setTitleOrName(e.target.value)}
              style={{ width: '100%', backgroundColor: '#0f172a', border: `1px solid ${errors.titleOrName ? '#ef4444' : '#334155'}`, color: '#f8fafc', padding: '0.5rem 0.75rem', borderRadius: '4px', boxSizing: 'border-box' }}
            />
            {errors.titleOrName && <span style={{ color: '#ef4444', fontSize: '0.75rem', marginTop: '2px', display: 'block' }}>{errors.titleOrName}</span>}
          </div>

          {/* Status (ADR) or Version (Spec) */}
          <div>
            {docType === 'adr' ? (
              <select
                value={statusOrVersion}
                onChange={(e) => setStatusOrVersion(e.target.value)}
                style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#38bdf8', padding: '0.5rem 0.75rem', borderRadius: '4px', boxSizing: 'border-box' }}
              >
                <option value="PROPOSED">PROPOSED</option>
                <option value="ACCEPTED">ACCEPTED</option>
                <option value="DEPRECATED">DEPRECATED</option>
              </select>
            ) : (
              <input
                type="text"
                placeholder="Version (e.g. 1.0.0)"
                value={statusOrVersion}
                onChange={(e) => setStatusOrVersion(e.target.value)}
                style={{ width: '100%', backgroundColor: '#0f172a', border: `1px solid ${errors.statusOrVersion ? '#ef4444' : '#334155'}`, color: '#f8fafc', padding: '0.5rem 0.75rem', borderRadius: '4px', boxSizing: 'border-box' }}
              />
            )}
            {errors.statusOrVersion && <span style={{ color: '#ef4444', fontSize: '0.75rem', marginTop: '2px', display: 'block' }}>{errors.statusOrVersion}</span>}
          </div>

          {/* Summary (ADR Only) */}
          {docType === 'adr' && (
            <div>
              <input
                type="text"
                placeholder="Summary (optional)"
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                style={{ width: '100%', backgroundColor: '#0f172a', border: `1px solid ${errors.summary ? '#ef4444' : '#334155'}`, color: '#94a3b8', padding: '0.5rem 0.75rem', borderRadius: '4px', boxSizing: 'border-box' }}
              />
              {errors.summary && <span style={{ color: '#ef4444', fontSize: '0.75rem', marginTop: '2px', display: 'block' }}>{errors.summary}</span>}
            </div>
          )}

          {/* Markdown Content */}
          <div>
            <textarea
              placeholder="Document Content (Markdown supported)..."
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={8}
              style={{ width: '100%', backgroundColor: '#0f172a', border: `1px solid ${errors.content ? '#ef4444' : '#334155'}`, color: '#38bdf8', padding: '0.5rem 0.75rem', borderRadius: '4px', fontFamily: 'monospace', fontSize: '0.85rem', boxSizing: 'border-box' }}
            />
            {errors.content && <span style={{ color: '#ef4444', fontSize: '0.75rem', marginTop: '2px', display: 'block' }}>{errors.content}</span>}
          </div>

          {statusMsg && <span style={{ fontSize: '0.8rem', color: statusMsg.includes('successfully') ? '#10b981' : '#ef4444' }}>{statusMsg}</span>}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
            <button type="button" onClick={onClose} style={{ backgroundColor: '#334155', color: '#f8fafc', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer' }}>
              Cancel
            </button>
            <button type="submit" disabled={submitting} style={{ backgroundColor: '#38bdf8', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer' }}>
              {submitting ? 'Creating...' : 'Create Document'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}