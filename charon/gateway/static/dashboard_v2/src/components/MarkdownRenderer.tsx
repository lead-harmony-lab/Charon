/**
 * @file src/components/MarkdownRenderer.tsx
 * @description Markdown renderer component supporting syntax highlighting, ticket anchors, and doc mentions.
 */
import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Link, useNavigate } from 'react-router-dom';

interface Props {
  content: string;
  onInternalLinkClick?: (id: string) => void;
  onDocLinkClick?: (docId: string) => void;
}

export function MarkdownRenderer({ content, onInternalLinkClick, onDocLinkClick }: Props) {
  const navigate = useNavigate();

  return (
    <div style={{ color: '#e2e8f0', lineHeight: '1.6', fontSize: '0.9rem' }}>
      <ReactMarkdown
        components={{
          h1: ({ children }) => (
            <h1 style={{ color: '#f8fafc', fontSize: '1.3rem', borderBottom: '1px solid #334155', paddingBottom: '0.4rem', marginTop: '1.2rem' }}>
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 style={{ color: '#f8fafc', fontSize: '1.1rem', marginTop: '1rem', marginBottom: '0.5rem' }}>
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 style={{ color: '#38bdf8', fontSize: '0.95rem', marginTop: '0.8rem' }}>
              {children}
            </h3>
          ),
          code({ inline, className, children, node, ...props }: any) {
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : 'text';

            const isBlock = match || inline === false || String(children).includes('\n');

            return isBlock ? (
              <div style={{ margin: '0.75rem 0', borderRadius: '6px', border: '1px solid #334155', backgroundColor: '#0f172a', overflow: 'hidden' }}>
                {match && match[1] && (
                  <div style={{
                    backgroundColor: '#1e293b',
                    padding: '0.25rem 0.75rem',
                    fontSize: '0.7rem',
                    color: '#94a3b8',
                    borderBottom: '1px solid #334155',
                    textTransform: 'uppercase',
                    fontWeight: 'bold',
                    letterSpacing: '0.05em'
                  }}>
                    {match[1]}
                  </div>
                )}
                <SyntaxHighlighter
                  style={oneDark as any}
                  language={language}
                  PreTag="div"
                  customStyle={{
                    margin: 0,
                    padding: '0.75rem',
                    backgroundColor: 'transparent',
                    fontSize: '0.85rem'
                  }}
                  {...props}
                >
                  {String(children).replace(/\n$/, '')}
                </SyntaxHighlighter>
              </div>
            ) : (
              <code style={{ backgroundColor: '#0f172a', color: '#38bdf8', padding: '0.2rem 0.4rem', borderRadius: '4px', fontSize: '0.85rem', border: '1px solid #334155' }} {...props}>
                {children}
              </code>
            );
          },
          blockquote: ({ children }) => (
            <blockquote style={{ borderLeft: '3px solid #38bdf8', paddingLeft: '1rem', color: '#94a3b8', margin: '0.75rem 0', fontStyle: 'italic' }}>
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => {
            // Intercept doc mentions (doc:<id>)
            if (href?.startsWith('doc:')) {
              const docId = href.replace(/^doc:/, '');
              return (
                <a
                  href={`/docs/manual/${docId}`}
                  onClick={(e) => {
                    e.preventDefault();
                    if (onDocLinkClick) {
                      onDocLinkClick(docId);
                    } else {
                      navigate(`/docs/manual/${docId}`);
                    }
                  }}
                  style={{ color: '#c084fc', textDecoration: 'underline', fontWeight: 'bold', cursor: 'pointer' }}
                >
                  {children}
                </a>
              );
            }

            // Intercept manual viewer absolute links (/docs/manual/<id>)
            if (href?.startsWith('/docs/manual/')) {
              const targetId = href.replace('/docs/manual/', '');
              return (
                <Link
                  to={href}
                  onClick={(e) => {
                    // Optional override if the parent still needs to intercept
                    if (onInternalLinkClick) {
                      onInternalLinkClick(targetId);
                    }
                  }}
                  style={{ color: '#38bdf8', textDecoration: 'underline', cursor: 'pointer' }}
                >
                  {children}
                </Link>
              );
            }

            // Intercept legacy internal anchor ticket links (#<id>)
            if (href?.startsWith('#')) {
              const targetId = href.slice(1);
              return (
                <a
                  href={href}
                  onClick={(e) => {
                    e.preventDefault();
                    if (onInternalLinkClick) {
                      onInternalLinkClick(targetId);
                    } else {
                      navigate(`?logId=${targetId}`);
                    }
                  }}
                  style={{ color: '#38bdf8', textDecoration: 'underline', cursor: 'pointer' }}
                >
                  {children}
                </a>
              );
            }

            // Standard external links
            return (
              <a href={href} target="_blank" rel="noreferrer" style={{ color: '#38bdf8', textDecoration: 'none' }}>
                {children}
              </a>
            );
          },
          ul: ({ children }) => <ul style={{ paddingLeft: '1.2rem', margin: '0.5rem 0' }}>{children}</ul>,
          ol: ({ children }) => <ol style={{ paddingLeft: '1.2rem', margin: '0.5rem 0' }}>{children}</ol>,
          li: ({ children }) => <li style={{ marginBottom: '0.25rem' }}>{children}</li>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}