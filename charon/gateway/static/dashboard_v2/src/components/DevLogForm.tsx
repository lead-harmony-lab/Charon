/**
 * @file src/components/DevLogForm.tsx
 * @description DevLog editor form with toolbar formatting, ticket linking, dynamic AST manual search, artifact management, and text-scaling.
 */
import React, { useState, useMemo, useRef, useEffect } from 'react';
import { JournalEntry, EntryType, TicketStatus, TicketPriority } from '../features/journal/types';
import { DocMentionItem, DocCategory } from '../features/docs/types';
import { useMentionAutocomplete, MentionCandidate } from '../hooks/useMentionAutocomplete';
import { DevLogToolbar } from './DevLogToolbar';

// Fallback category items if no dynamic docs are available
const DEFAULT_DOC_ITEMS: DocMentionItem[] = [
  { id: 'ADR-001', title: 'Architecture Decision Records', category: 'adr' },
  { id: 'SPEC-001', title: 'Technical Specifications', category: 'spec' },
];

// Define comfortable reading sizes for the editor
const FONT_SIZES = ['14px', '16px', '18px', '20px'];

interface DevLogFormProps {
  formData: Partial<JournalEntry>;
  setFormData: React.Dispatch<React.SetStateAction<Partial<JournalEntry>>>;
  isCreating: boolean;
  entries: JournalEntry[];
  availableTickets: JournalEntry[];
  availableDocs?: DocMentionItem[];
  onSave: () => void;
  onCancel: () => void;
}

export function DevLogForm({
  formData,
  setFormData,
  isCreating,
  entries,
  availableTickets,
  availableDocs = [],
  onSave,
  onCancel,
}: DevLogFormProps) {
  const [artifactInput, setArtifactInput] = useState('');
  const [ticketToLink, setTicketToLink] = useState('');

  // State for tracking text size
  const [sizeIndex, setSizeIndex] = useState(0);

  const menuContainerRef = useRef<HTMLDivElement | null>(null);

  const effectiveDocs = useMemo(
    () => (availableDocs.length > 0 ? availableDocs : DEFAULT_DOC_ITEMS),
    [availableDocs]
  );

  const {
    textareaRef,
    mentionQuery,
    mentionCategory,
    mentionTrigger,
    mentionSelectedIndex,
    setMentionSelectedIndex,
    handleContentChange,
    handleKeyDown,
    insertMention,
  } = useMentionAutocomplete(
    formData.content || '',
    (content: string) => setFormData((prev) => ({ ...prev, content })),
    (itemId: string) => {
      setFormData((prev) => ({
        ...prev,
        linkedTickets: Array.from(new Set([...(prev.linkedTickets || []), itemId])),
      }));
    },
    (itemId: string) => {
      setFormData((prev) => ({
        ...prev,
        linkedDocs: Array.from(new Set([...(prev.linkedDocs || []), itemId])),
      }));
    }
  );

  // Dismiss mention popup when clicking outside the editor container
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        menuContainerRef.current &&
        !menuContainerRef.current.contains(event.target as Node) &&
        mentionQuery !== null
      ) {
        textareaRef.current?.dispatchEvent(
          new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })
        );
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [mentionQuery, textareaRef]);

  // Filter tickets (#)
  const ticketCandidates = useMemo(() => {
    if (mentionQuery === null || mentionTrigger !== '#') return [];
    const q = mentionQuery.toLowerCase();
    return entries.filter(
      (e) => e.id.toLowerCase().includes(q) || e.title.toLowerCase().includes(q)
    );
  }, [entries, mentionQuery, mentionTrigger]);

  // Filter docs (@) - Stage 1 (Categories) & Stage 2 (Real Manual Nodes)
  const docCandidates = useMemo(() => {
    if (mentionQuery === null || mentionTrigger !== '@') return [];
    const q = mentionQuery.toLowerCase();

    // Stage 1: Choose Category
    if (!mentionCategory) {
      return ['ADR', 'Spec', 'Manual']
        .filter((c) => c.toLowerCase().includes(q))
        .map((c) => ({ _isCategory: true, name: c } as MentionCandidate));
    }

    // Stage 2: Filter dynamic flattened Manual nodes by ID or Title
    return effectiveDocs.filter(
      (d) =>
        (d.category || 'manual').toLowerCase() === mentionCategory.toLowerCase() &&
        (d.id.toLowerCase().includes(q) || d.title.toLowerCase().includes(q))
    );
  }, [effectiveDocs, mentionQuery, mentionTrigger, mentionCategory]);

  const activeCandidates = mentionTrigger === '@' ? docCandidates : ticketCandidates;

  // handleInsertSymbol forces a native React change event
  const handleInsertSymbol = (prefix: string, suffix: string = '') => {
    if (!textareaRef.current) return;
    const textarea = textareaRef.current;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const currentContent = formData.content || '';

    const selectedText = currentContent.substring(start, end);
    const newContent =
      currentContent.substring(0, start) +
      prefix +
      selectedText +
      suffix +
      currentContent.substring(end);

    // Use native setter to trigger React's onChange properly
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      'value'
    )?.set;

    if (nativeSetter) {
      nativeSetter.call(textarea, newContent);
    }

    // Update cursor BEFORE dispatching so the hook reads the correct cursor position
    textarea.focus();
    textarea.setSelectionRange(start + prefix.length, end + prefix.length);

    // Dispatch 'input' so useMentionAutocomplete picks it up and updates state synchronously
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  };

  const handleTriggerMention = () => handleInsertSymbol('#');
  const handleTriggerDocMention = () => handleInsertSymbol('@');

  // NEW: Explicit increment/decrement handlers with bounds checking
  const handleIncreaseTextSize = () => {
    setSizeIndex((prev) => Math.min(prev + 1, FONT_SIZES.length - 1));
  };

  const handleDecreaseTextSize = () => {
    setSizeIndex((prev) => Math.max(prev - 1, 0));
  };

  const handleAddLinkedTicket = () => {
    if (!ticketToLink || (formData.linkedTickets || []).includes(ticketToLink)) return;
    setFormData((prev) => ({
      ...prev,
      linkedTickets: [...(prev.linkedTickets || []), ticketToLink],
    }));
    setTicketToLink('');
  };

  const handleRemoveLinkedTicket = (ticketId: string) => {
    setFormData((prev) => ({
      ...prev,
      linkedTickets: (prev.linkedTickets || []).filter((id) => id !== ticketId),
    }));
  };

  const handleAddArtifact = () => {
    if (!artifactInput.trim()) return;
    setFormData((prev) => ({
      ...prev,
      linkedArtifacts: [...(prev.linkedArtifacts || []), artifactInput.trim()],
    }));
    setArtifactInput('');
  };

  const handleRemoveArtifact = (index: number) => {
    setFormData((prev) => ({
      ...prev,
      linkedArtifacts: (prev.linkedArtifacts || []).filter((_, i) => i !== index),
    }));
  };

  const getBadgeStyle = (category: DocCategory | string): React.CSSProperties => {
    switch (category.toLowerCase()) {
      case 'adr':
        return { backgroundColor: '#3b82f620', color: '#60a5fa', border: '1px solid #1d4ed8' };
      case 'spec':
        return { backgroundColor: '#10b98120', color: '#34d399', border: '1px solid #047857' };
      case 'manual':
        return { backgroundColor: '#f59e0b20', color: '#fbbf24', border: '1px solid #b45309' };
      default:
        return { backgroundColor: '#64748b20', color: '#94a3b8', border: '1px solid #475569' };
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {/* Header Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #334155', paddingBottom: '0.75rem' }}>
        <h3 style={{ margin: 0, color: '#f8fafc' }}>
          {isCreating ? 'New Dev Log Entry' : `Edit ${formData.id}`}
        </h3>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button onClick={onCancel} style={{ backgroundColor: '#334155', color: '#f8fafc', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>
            Cancel
          </button>
          <button onClick={onSave} style={{ backgroundColor: '#10b981', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', fontSize: '0.85rem' }}>
            Save Post
          </button>
        </div>
      </div>

      {/* Title Input */}
      <input
        type="text"
        placeholder="Post Title"
        value={formData.title || ''}
        onChange={(e) => setFormData((prev) => ({ ...prev, title: e.target.value }))}
        style={{ width: '100%', backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', padding: '0.6rem', borderRadius: '6px', fontWeight: 'bold', fontSize: '1rem', boxSizing: 'border-box' }}
      />

      {/* Metadata Configuration Options */}
      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <label style={{ color: '#94a3b8', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          Type:
          <select
            value={formData.type || 'observation'}
            onChange={(e) => setFormData((prev) => ({ ...prev, type: e.target.value as EntryType }))}
            style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', padding: '0.4rem', borderRadius: '4px' }}
          >
            <option value="observation">Observation</option>
            <option value="session">Session</option>
            <option value="defect">Defect</option>
            <option value="feature">Feature</option>
            <option value="architecture">Architecture</option>
            <option value="runbook">Runbook (Build)</option>
          </select>
        </label>

        <label style={{ color: '#94a3b8', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          Track on Board:
          <select
            value={formData.status || 'none'}
            onChange={(e) => setFormData((prev) => ({ ...prev, status: e.target.value === 'none' ? null : (e.target.value as TicketStatus) }))}
            style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', padding: '0.4rem', borderRadius: '4px' }}
          >
            <option value="none">No (Log Entry Only)</option>
            <option value="todo">To Do</option>
            <option value="in_progress">In Progress</option>
            <option value="blocked">Blocked</option>
            <option value="done">Done</option>
          </select>
        </label>

        {formData.status && (
          <label style={{ color: '#94a3b8', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            Priority:
            <select
              value={formData.priority || 'medium'}
              onChange={(e) => setFormData((prev) => ({ ...prev, priority: e.target.value as TicketPriority }))}
              style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f8fafc', padding: '0.4rem', borderRadius: '4px' }}
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </label>
        )}
      </div>

      {/* Board Ticket Linking Panel */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', backgroundColor: '#0f172a', padding: '0.75rem', borderRadius: '6px', border: '1px solid #854d0e' }}>
        <span style={{ fontSize: '0.8rem', color: '#facc15', fontWeight: 'bold' }}>📌 Link Active Board Tickets</span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <select
            value={ticketToLink}
            onChange={(e) => setTicketToLink(e.target.value)}
            style={{ flex: 1, backgroundColor: '#1e293b', border: '1px solid #334155', color: '#f8fafc', padding: '0.4rem 0.6rem', borderRadius: '4px', fontSize: '0.85rem' }}
          >
            <option value="">Select a ticket on the board...</option>
            {availableTickets.map((ticket) => (
              <option key={ticket.id} value={ticket.id}>
                [{ticket.id}] {ticket.title} ({ticket.status})
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={handleAddLinkedTicket}
            disabled={!ticketToLink}
            style={{ backgroundColor: ticketToLink ? '#eab308' : '#334155', color: '#0f172a', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', fontWeight: 'bold', cursor: ticketToLink ? 'pointer' : 'not-allowed', fontSize: '0.85rem' }}
          >
            + Link Ticket
          </button>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.25rem' }}>
          {formData.linkedTickets?.map((ticketId) => {
            const targetTicket = entries.find((e) => e.id === ticketId);
            return (
              <span key={ticketId} style={{ backgroundColor: '#1e293b', color: '#facc15', border: '1px solid #854d0e', padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                📌 [{ticketId}] {targetTicket ? targetTicket.title : ticketId}
                <button type="button" onClick={() => handleRemoveLinkedTicket(ticketId)} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', padding: 0 }}>✕</button>
              </span>
            );
          })}
        </div>
      </div>

      {/* Telemetry & Artifacts Panel */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', backgroundColor: '#0f172a', padding: '0.75rem', borderRadius: '6px', border: '1px solid #334155' }}>
        <span style={{ fontSize: '0.8rem', color: '#cbd5e1', fontWeight: 'bold' }}>Linked Telemetry & Artifacts</span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            type="text"
            placeholder="e.g. trace-9f8a-4b2c"
            value={artifactInput}
            onChange={(e) => setArtifactInput(e.target.value)}
            style={{ flex: 1, backgroundColor: '#1e293b', border: '1px solid #334155', color: '#f8fafc', padding: '0.4rem 0.6rem', borderRadius: '4px', fontSize: '0.85rem' }}
          />
          <button type="button" onClick={handleAddArtifact} style={{ backgroundColor: '#334155', color: '#f8fafc', border: 'none', padding: '0.4rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>
            + Link
          </button>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.25rem' }}>
          {formData.linkedArtifacts?.map((art, i) => (
            <span key={i} style={{ backgroundColor: '#1e293b', color: '#38bdf8', border: '1px solid #0284c7', padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              🔗 {art}
              <button type="button" onClick={() => handleRemoveArtifact(i)} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', padding: 0 }}>✕</button>
            </span>
          ))}
        </div>
      </div>

      {/* Markdown Toolbar & Autocomplete Textarea */}
      <div ref={menuContainerRef} style={{ display: 'flex', flexDirection: 'column', width: '100%', position: 'relative' }}>

        {/* NEW: Explicit Increase/Decrease Handlers with disabled states */}
        <DevLogToolbar
          onInsertSymbol={handleInsertSymbol}
          onTriggerMention={handleTriggerMention}
          onTriggerDocMention={handleTriggerDocMention}
          onIncreaseTextSize={handleIncreaseTextSize}
          onDecreaseTextSize={handleDecreaseTextSize}
          disableIncrease={sizeIndex === FONT_SIZES.length - 1}
          disableDecrease={sizeIndex === 0}
        />

        <textarea
          ref={textareaRef}
          placeholder="Type '#' for tickets or '@' for docs (ADR, SPEC, MANUAL)..."
          value={formData.content || ''}
          onChange={handleContentChange}
          onKeyDown={(e) => handleKeyDown(e, activeCandidates)}
          rows={14}
          style={{
            width: '100%',
            backgroundColor: '#0f172a',
            border: '1px solid #334155',
            color: '#e2e8f0',
            padding: '0.8rem',
            borderBottomLeftRadius: '6px',
            borderBottomRightRadius: '6px',
            borderTopLeftRadius: 0,
            borderTopRightRadius: 0,
            fontFamily: 'monospace',
            fontSize: FONT_SIZES[sizeIndex],
            boxSizing: 'border-box',
          }}
        />

        {/* Autocomplete Dropdown Popup */}
        {mentionQuery !== null && (
          <div
            style={{
              position: 'absolute',
              bottom: '1.5rem',
              left: '1rem',
              backgroundColor: '#0f172a',
              border: mentionTrigger === '@' ? '1px solid #c084fc' : '1px solid #eab308',
              borderRadius: '6px',
              boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)',
              maxHeight: '220px',
              overflowY: 'auto',
              zIndex: 10,
              width: '380px',
            }}
          >
            <div style={{ padding: '0.4rem 0.6rem', borderBottom: '1px solid #334155', fontSize: '0.7rem', color: mentionTrigger === '@' ? '#c084fc' : '#eab308', fontWeight: 'bold', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>
                {mentionTrigger === '@'
                  ? mentionCategory
                    ? `Search ${mentionCategory.toUpperCase()} Nodes`
                    : 'Select Document Category'
                  : 'Mention Ticket (#)'}
              </span>
            </div>

            {/* Empty state check */}
            {activeCandidates.length === 0 && (
              <div style={{ padding: '0.75rem', fontSize: '0.8rem', color: '#64748b', textAlign: 'center' }}>
                No matching {mentionCategory ? `${mentionCategory} pages` : 'items'} found.
              </div>
            )}

            {/* Ticket Candidates Dropdown (#) */}
            {mentionTrigger === '#' &&
              (activeCandidates as JournalEntry[]).map((entry, idx) => (
                <div
                  key={entry.id}
                  onClick={() => insertMention(entry)}
                  onMouseEnter={() => setMentionSelectedIndex(idx)}
                  style={{
                    padding: '0.5rem 0.75rem',
                    cursor: 'pointer',
                    backgroundColor: idx === mentionSelectedIndex ? '#1e293b' : 'transparent',
                    color: idx === mentionSelectedIndex ? '#facc15' : '#e2e8f0',
                    fontSize: '0.8rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    borderLeft: idx === mentionSelectedIndex ? '3px solid #eab308' : '3px solid transparent',
                  }}
                >
                  <span style={{ fontWeight: 'bold', fontFamily: 'monospace' }}>[{entry.id}]</span>
                  <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginLeft: '0.5rem', flex: 1 }}>{entry.title}</span>
                </div>
              ))}

            {/* Doc Categories Dropdown (@ Stage 1) */}
            {mentionTrigger === '@' && !mentionCategory &&
              (activeCandidates as { _isCategory: true; name: string }[]).map((cat, idx) => (
                <div
                  key={cat.name}
                  onClick={() => insertMention(cat)}
                  onMouseEnter={() => setMentionSelectedIndex(idx)}
                  style={{
                    padding: '0.5rem 0.75rem',
                    cursor: 'pointer',
                    backgroundColor: idx === mentionSelectedIndex ? '#1e293b' : 'transparent',
                    color: idx === mentionSelectedIndex ? '#c084fc' : '#e2e8f0',
                    fontSize: '0.85rem',
                    display: 'flex',
                    alignItems: 'center',
                    borderLeft: idx === mentionSelectedIndex ? '3px solid #c084fc' : '3px solid transparent',
                  }}
                >
                  <span style={{ fontWeight: 'bold' }}>{cat.name}</span>
                  <span style={{ marginLeft: '0.5rem', color: '#64748b', fontSize: '0.75rem' }}>- Search manual AST tree...</span>
                </div>
              ))}

            {/* Manual AST Nodes Dropdown (@ Stage 2) */}
            {mentionTrigger === '@' && mentionCategory &&
              (activeCandidates as DocMentionItem[]).map((doc, idx) => (
                <div
                  key={doc.id}
                  onClick={() => insertMention(doc)}
                  onMouseEnter={() => setMentionSelectedIndex(idx)}
                  style={{
                    padding: '0.5rem 0.75rem',
                    cursor: 'pointer',
                    backgroundColor: idx === mentionSelectedIndex ? '#1e293b' : 'transparent',
                    color: idx === mentionSelectedIndex ? '#c084fc' : '#e2e8f0',
                    fontSize: '0.8rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    borderLeft: idx === mentionSelectedIndex ? '3px solid #c084fc' : '3px solid transparent',
                  }}
                >
                  <span
                    style={{
                      fontSize: '0.65rem',
                      fontWeight: 'bold',
                      padding: '1px 5px',
                      borderRadius: '3px',
                      textTransform: 'uppercase',
                      marginRight: '0.5rem',
                      ...getBadgeStyle(doc.category),
                    }}
                  >
                    [{doc.category}]
                  </span>
                  <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1, fontWeight: 'bold' }}>{doc.title}</span>
                  <span style={{ fontSize: '0.7rem', color: '#64748b', fontFamily: 'monospace', marginLeft: '0.5rem' }}>{doc.id}</span>
                </div>
              ))}
          </div>
        )}
      </div>
    </div>
  );
}