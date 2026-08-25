/**
 * @file src/components/DevLogToolbar.tsx
 * @description Toolbar for the DevLog editor supporting markdown, dynamic mentions, and text scaling.
 */
import React from 'react';

interface DevLogToolbarProps {
  onInsertSymbol: (prefix: string, suffix?: string) => void;
  onTriggerMention: () => void;
  onTriggerDocMention: () => void;
  onIncreaseTextSize?: () => void;
  onDecreaseTextSize?: () => void;
  disableIncrease?: boolean;
  disableDecrease?: boolean;
}

export function DevLogToolbar({
  onInsertSymbol,
  onTriggerMention,
  onTriggerDocMention,
  onIncreaseTextSize,
  onDecreaseTextSize,
  disableIncrease = false,
  disableDecrease = false,
}: DevLogToolbarProps) {
  const toolbarBtnStyle: React.CSSProperties = {
    backgroundColor: '#1e293b',
    color: '#cbd5e1',
    border: '1px solid #475569',
    borderRadius: '4px',
    padding: '0.2rem 0.5rem',
    cursor: 'pointer',
    fontSize: '0.75rem',
    fontWeight: 'bold',
  };

  return (
    <div
      style={{
        display: 'flex',
        gap: '0.4rem',
        backgroundColor: '#0f172a',
        padding: '0.4rem',
        border: '1px solid #334155',
        borderBottom: 'none',
        borderRadius: '6px 6px 0 0',
        alignItems: 'center',
        flexWrap: 'wrap',
      }}
    >
      {/* Standard Markdown Formatting */}
      <button type="button" onClick={() => onInsertSymbol('**', '**')} style={toolbarBtnStyle} title="Bold">B</button>
      <button type="button" onClick={() => onInsertSymbol('*', '*')} style={{ ...toolbarBtnStyle, fontStyle: 'italic' }} title="Italic">I</button>

      <div style={{ width: '1px', height: '16px', backgroundColor: '#334155', margin: '0 4px' }} />

      <button type="button" onClick={() => onInsertSymbol('## ', '')} style={toolbarBtnStyle} title="Heading 2">H2</button>
      <button type="button" onClick={() => onInsertSymbol('### ', '')} style={toolbarBtnStyle} title="Heading 3">H3</button>

      <div style={{ width: '1px', height: '16px', backgroundColor: '#334155', margin: '0 4px' }} />

      <button type="button" onClick={() => onInsertSymbol('- ', '')} style={toolbarBtnStyle} title="Bullet List">• List</button>
      <button type="button" onClick={() => onInsertSymbol('[', '](#document-id)')} style={toolbarBtnStyle} title="Internal Link">🔗 Link</button>

      {/* Inline Code format support */}
      <button type="button" onClick={() => onInsertSymbol('`', '`')} style={{ ...toolbarBtnStyle, color: '#38bdf8' }} title="Inline Code">` Code `</button>

      <div style={{ width: '1px', height: '16px', backgroundColor: '#334155', margin: '0 4px' }} />

      <button type="button" onClick={() => onInsertSymbol('```bash\n', '\n```')} style={toolbarBtnStyle} title="Bash Block">Bash</button>
      <button type="button" onClick={() => onInsertSymbol('```python\n', '\n```')} style={toolbarBtnStyle} title="Python Block">Py</button>
      <button type="button" onClick={() => onInsertSymbol('```json\n', '\n```')} style={toolbarBtnStyle} title="JSON Block">JSON</button>

      {/* Spacer to push UI controls and mention triggers to the right */}
      <div style={{ flex: 1 }} />

      {/* UI Controls: Text Size Group */}
      {onIncreaseTextSize && onDecreaseTextSize && (
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <button
            type="button"
            onClick={onDecreaseTextSize}
            disabled={disableDecrease}
            style={{
              ...toolbarBtnStyle,
              color: disableDecrease ? '#475569' : '#a7f3d0',
              borderColor: disableDecrease ? '#334155' : '#059669',
              borderRight: 'none',
              borderRadius: '4px 0 0 4px',
              cursor: disableDecrease ? 'not-allowed' : 'pointer',
            }}
            title="Decrease Text Size"
          >
            T-
          </button>
          <button
            type="button"
            onClick={onIncreaseTextSize}
            disabled={disableIncrease}
            style={{
              ...toolbarBtnStyle,
              color: disableIncrease ? '#475569' : '#a7f3d0',
              borderColor: disableIncrease ? '#334155' : '#059669',
              borderRadius: '0 4px 4px 0',
              cursor: disableIncrease ? 'not-allowed' : 'pointer',
            }}
            title="Increase Text Size"
          >
            T+
          </button>
        </div>
      )}

      <div style={{ width: '1px', height: '16px', backgroundColor: '#334155', margin: '0 4px' }} />

      {/* Mention Triggers */}
      <button
        type="button"
        onClick={onTriggerMention}
        style={{ ...toolbarBtnStyle, backgroundColor: '#eab30820', color: '#facc15', borderColor: '#ca8a04' }}
        title="Mention Ticket (#)"
      >
        # Ticket
      </button>
      <button
        type="button"
        onClick={onTriggerDocMention}
        style={{ ...toolbarBtnStyle, backgroundColor: '#c084fc20', color: '#c084fc', borderColor: '#9333ea' }}
        title="Mention Doc (@)"
      >
        @ Doc
      </button>
    </div>
  );
}