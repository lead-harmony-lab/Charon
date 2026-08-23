import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface Props {
  content: string;
}

export function MarkdownRenderer({ content }: Props) {
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
          code({ inline, className, children, ...props }: any) {
            const match = /language-(\w+)/.exec(className || '');
            return !inline && match ? (
              <SyntaxHighlighter
                style={oneDark as any}
                language={match[1]}
                PreTag="div"
                customStyle={{
                  margin: '0.75rem 0',
                  borderRadius: '6px',
                  border: '1px solid #334155',
                  fontSize: '0.85rem',
                  backgroundColor: '#0f172a'
                }}
                {...props}
              >
                {String(children).replace(/\n$/, '')}
              </SyntaxHighlighter>
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
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" style={{ color: '#38bdf8', textDecoration: 'none' }}>
              {children}
            </a>
          ),
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