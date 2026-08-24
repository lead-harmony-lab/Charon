/**
 * @file src/components/MarkdownToolbar.tsx
 * @description A reusable Markdown formatting toolbar that attaches to a textarea.
 */
import React, { RefObject } from 'react';

interface MarkdownToolbarProps {
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  content: string;
  setContent: (content: string) => void;
  hasError?: boolean;
}

export function MarkdownToolbar({ textareaRef, content, setContent, hasError = false }: MarkdownToolbarProps) {
  const handleFormat = (prefix: string, suffix: string = '') => {
    if (!textareaRef.current) return;

    const start = textareaRef.current.selectionStart;
    const end = textareaRef.current.selectionEnd;
    const selectedText = content.substring(start, end);

    const newText = content.substring(0, start) + prefix + selectedText + suffix + content.substring(end);
    setContent(newText);

    // Restore focus and set cursor inside the newly added markdown tags
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.focus();
        textareaRef.current.setSelectionRange(start + prefix.length, end + prefix.length);
      }
    }, 0);
  };

  const toolbarBtnStyle = {
    backgroundColor: '#1e293b',
    color: '#cbd5e1',
    border: '1px solid #475569',
    borderRadius: '4px',
    padding: '0.2rem 0.5rem',
    cursor: 'pointer',
    fontSize: '0.75rem',
    fontWeight: 'bold'
  };

  return (
    <div style={{
      display: 'flex',
      gap: '0.4rem',
      backgroundColor: '#0f172a',
      padding: '0.4rem',
      border: `1px solid ${hasError ? '#ef4444' : '#334155'}`,
      borderBottom: 'none',
      borderRadius: '4px 4px 0 0'
    }}>
      <button type="button" onClick={() => handleFormat('**', '**')} style={toolbarBtnStyle} title="Bold">B</button>
      <button type="button" onClick={() => handleFormat('*', '*')} style={{ ...toolbarBtnStyle, fontStyle: 'italic' }} title="Italic">I</button>
      <div style={{ width: '1px', backgroundColor: '#334155', margin: '0 4px' }} />
      <button type="button" onClick={() => handleFormat('## ', '')} style={toolbarBtnStyle} title="Heading 2">H2</button>
      <button type="button" onClick={() => handleFormat('### ', '')} style={toolbarBtnStyle} title="Heading 3">H3</button>
      <div style={{ width: '1px', backgroundColor: '#334155', margin: '0 4px' }} />
      <button type="button" onClick={() => handleFormat('- ', '')} style={toolbarBtnStyle} title="Bullet List">• List</button>
      <button type="button" onClick={() => handleFormat('[', '](#document-id)')} style={toolbarBtnStyle} title="Internal Link">🔗 Link</button>
      <button type="button" onClick={() => handleFormat('`', '`')} style={toolbarBtnStyle} title="Inline Code">`</button>
      <div style={{ width: '1px', backgroundColor: '#334155', margin: '0 4px' }} />
      <button type="button" onClick={() => handleFormat('```bash\n', '\n```')} style={toolbarBtnStyle} title="Bash Block">Bash</button>
      <button type="button" onClick={() => handleFormat('```python\n', '\n```')} style={toolbarBtnStyle} title="Python Block">Py</button>
      <button type="button" onClick={() => handleFormat('```json\n', '\n```')} style={toolbarBtnStyle} title="JSON Block">JSON</button>
    </div>
  );
}