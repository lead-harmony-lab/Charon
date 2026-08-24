/**
 * @file src/features/docs/SpecRenderer.tsx
 * @description Specification viewer with OpenAPI 3.0 YAML export, global/local line wrapping, line numbers, JSON syntax highlighting, search term highlighting, and copy controls.
 */
import React, { useState, useMemo, useEffect } from 'react';

interface InboundAction {
  action: string;
  aliases?: string[];
  description?: string;
  payload?: any;
  responseEvent?: any;
}

interface OutboundSchema {
  description?: string;
  schema?: any;
}

interface AuthMechanism {
  location: string;
  key: string;
  format?: string;
}

interface SpecData {
  id?: string;
  name?: string;
  version?: string;
  status?: string;
  lastUpdated?: string;
  description?: string;
  endpoints?: string[];
  authentication?: {
    type?: string;
    mechanisms?: AuthMechanism[];
    unauthorizedCloseCode?: number;
  };
  protocol?: {
    transport?: string;
    format?: string;
    encoding?: string;
  };
  channels?: {
    inboundActions?: (InboundAction | string)[];
    outboundEventSchemas?: Record<string, OutboundSchema>;
  };
}

/** Converts JavaScript object structures into valid YAML strings without external dependencies */
function jsonToYaml(obj: any, indentLevel = 0): string {
  const indent = '  '.repeat(indentLevel);
  if (obj === null || obj === undefined) return 'null';
  if (typeof obj === 'boolean' || typeof obj === 'number') return String(obj);
  if (typeof obj === 'string') {
    if (obj.includes('\n') || obj.includes(':') || obj.includes('#') || obj.trim() === '') {
      return `"${obj.replace(/"/g, '\\"')}"`;
    }
    return obj;
  }

  if (Array.isArray(obj)) {
    if (obj.length === 0) return '[]';
    return obj
      .map((item) => {
        if (typeof item === 'object' && item !== null) {
          const innerYaml = jsonToYaml(item, indentLevel + 1).trimStart();
          return `${indent}- ${innerYaml}`;
        }
        return `${indent}- ${jsonToYaml(item, indentLevel + 1)}`;
      })
      .join('\n');
  }

  if (typeof obj === 'object') {
    const keys = Object.keys(obj).filter((k) => obj[k] !== undefined);
    if (keys.length === 0) return '{}';
    return keys
      .map((key) => {
        const val = obj[key];
        if (typeof val === 'object' && val !== null && !Array.isArray(val) && Object.keys(val).length > 0) {
          return `${indent}${key}:\n${jsonToYaml(val, indentLevel + 1)}`;
        }
        if (Array.isArray(val) && val.length > 0) {
          return `${indent}${key}:\n${jsonToYaml(val, indentLevel + 1)}`;
        }
        return `${indent}${key}: ${jsonToYaml(val, indentLevel + 1)}`;
      })
      .join('\n');
  }

  return String(obj);
}

/** Maps internal SpecData into an OpenAPI 3.0.3 spec object */
function convertSpecToOpenApi3(spec: SpecData) {
  const openapi: Record<string, any> = {
    openapi: '3.0.3',
    info: {
      title: spec.name || 'API Specification',
      version: spec.version || '1.0.0',
      description: spec.description || ''
    },
    servers: (spec.endpoints || []).map((ep) => ({ url: ep })),
    paths: {},
    components: {
      schemas: {}
    }
  };

  if (spec.channels?.inboundActions) {
    spec.channels.inboundActions.forEach((item) => {
      const act = typeof item === 'string' ? { action: item } : item;
      const pathName = `/action/${act.action}`;

      openapi.paths[pathName] = {
        post: {
          summary: act.description || `Trigger action: ${act.action}`,
          operationId: act.action,
          ...(act.payload
            ? {
                requestBody: {
                  required: true,
                  content: {
                    'application/json': {
                      schema: act.payload
                    }
                  }
                }
              }
            : {}),
          responses: {
            '200': {
              description: 'Action execution response',
              ...(act.responseEvent
                ? {
                    content: {
                      'application/json': {
                        schema: act.responseEvent
                      }
                    }
                  }
                : {})
            }
          }
        }
      };
    });
  }

  if (spec.channels?.outboundEventSchemas) {
    Object.entries(spec.channels.outboundEventSchemas).forEach(([schemaName, schemaData]) => {
      openapi.components.schemas[schemaName] = schemaData.schema || {
        type: 'object',
        description: schemaData.description || ''
      };
    });
  }

  return openapi;
}

/** Highlights matching query terms within a string token */
function renderHighlightedText(text: string, query: string) {
  if (!query.trim()) return text;

  const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = text.split(new RegExp(`(${escapedQuery})`, 'gi'));

  return parts.map((part, i) =>
    part.toLowerCase() === query.toLowerCase() ? (
      <mark
        key={i}
        style={{
          backgroundColor: '#f59e0b',
          color: '#0f172a',
          borderRadius: '2px',
          padding: '0 2px',
          fontWeight: 'bold'
        }}
      >
        {part}
      </mark>
    ) : (
      part
    )
  );
}

/** Tokenizes JSON strings and renders syntax-highlighted React elements */
function renderSyntaxHighlightedJson(jsonString: string, searchQuery: string = '') {
  const tokenRegex = /("(?:\\.|[^"\\])*")(?=\s*:)|("(?:\\.|[^"\\])*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(true|false|null)|([{}[\],:])|(\s+)|([^"{}[\],:\s]+)/g;

  const elements: React.ReactNode[] = [];
  let match: RegExpExecArray | null;
  let keyIdx = 0;

  while ((match = tokenRegex.exec(jsonString)) !== null) {
    const [fullMatch, jsonKey, jsonStringVal, jsonNum, jsonBoolNull, jsonPunct] = match;

    let color = '#e2e8f0';

    if (jsonKey !== undefined) {
      color = '#7dd3fc';
    } else if (jsonStringVal !== undefined) {
      color = '#34d399';
    } else if (jsonNum !== undefined) {
      color = '#fb7185';
    } else if (jsonBoolNull !== undefined) {
      color = '#fbbf24';
    } else if (jsonPunct !== undefined) {
      color = '#94a3b8';
    }

    elements.push(
      <span key={keyIdx++} style={{ color }}>
        {renderHighlightedText(fullMatch, searchQuery)}
      </span>
    );
  }

  return elements;
}

function CollapsibleJsonBlock({
  title,
  data,
  defaultExpanded = false,
  forceExpanded = false,
  searchQuery = '',
  globalWrapLines = false
}: {
  title: string;
  data: any;
  defaultExpanded?: boolean;
  forceExpanded?: boolean;
  searchQuery?: string;
  globalWrapLines?: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [copied, setCopied] = useState(false);
  const [wrapLines, setWrapLines] = useState(globalWrapLines);
  const activeExpanded = forceExpanded || isExpanded;

  useEffect(() => {
    setWrapLines(globalWrapLines);
  }, [globalWrapLines]);

  if (!data || (typeof data === 'object' && Object.keys(data).length === 0)) {
    return (
      <div style={{ color: '#64748b', fontSize: '0.75rem', fontStyle: 'italic', marginTop: '0.25rem' }}>
        {title}: None
      </div>
    );
  }

  const jsonString = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
  const lineCount = jsonString.split('\n').length;

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(jsonString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const toggleWrap = (e: React.MouseEvent) => {
    e.stopPropagation();
    setWrapLines((prev) => !prev);
  };

  return (
    <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '4px', overflow: 'hidden', marginTop: '0.4rem' }}>
      <div
        onClick={() => setIsExpanded(!activeExpanded)}
        style={{
          width: '100%',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: '#0f172a',
          borderBottom: activeExpanded ? '1px solid #334155' : 'none',
          padding: '0.4rem 0.6rem',
          color: '#cbd5e1',
          fontSize: '0.75rem',
          cursor: 'pointer',
          fontFamily: 'monospace',
          userSelect: 'none'
        }}
      >
        <span>
          <strong style={{ color: '#38bdf8' }}>{activeExpanded ? '▼' : '►'}</strong> {title}{' '}
          <span style={{ color: '#64748b' }}>({lineCount} {lineCount === 1 ? 'line' : 'lines'})</span>
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <button
            type="button"
            onClick={toggleWrap}
            style={{
              backgroundColor: wrapLines ? '#38bdf820' : '#1e293b',
              color: wrapLines ? '#38bdf8' : '#94a3b8',
              border: `1px solid ${wrapLines ? '#38bdf8' : '#334155'}`,
              borderRadius: '3px',
              padding: '0.15rem 0.4rem',
              fontSize: '0.68rem',
              cursor: 'pointer',
              transition: 'all 0.15s ease'
            }}
          >
            {wrapLines ? 'Unwrap' : 'Wrap'}
          </button>
          <button
            type="button"
            onClick={handleCopy}
            style={{
              backgroundColor: copied ? '#10b98120' : '#1e293b',
              color: copied ? '#10b981' : '#38bdf8',
              border: `1px solid ${copied ? '#10b981' : '#334155'}`,
              borderRadius: '3px',
              padding: '0.15rem 0.4rem',
              fontSize: '0.68rem',
              cursor: 'pointer',
              transition: 'all 0.15s ease'
            }}
          >
            {copied ? '✓ Copied' : 'Copy'}
          </button>
          <span style={{ color: '#94a3b8', fontSize: '0.7rem' }}>{activeExpanded ? 'Collapse' : 'Expand'}</span>
        </div>
      </div>

      {activeExpanded && (
        <div style={{ display: 'flex', backgroundColor: '#0b1329', padding: '0.6rem', overflowX: wrapLines ? 'hidden' : 'auto', fontFamily: 'monospace', fontSize: '0.75rem', lineHeight: '1.45' }}>
          <div
            style={{
              paddingRight: '0.75rem',
              marginRight: '0.75rem',
              borderRight: '1px solid #1e293b',
              color: '#475569',
              textAlign: 'right',
              userSelect: 'none',
              minWidth: '2.2rem',
              flexShrink: 0
            }}
          >
            {Array.from({ length: lineCount }, (_, i) => (
              <div key={i}>{i + 1}</div>
            ))}
          </div>

          <pre
            style={{
              margin: 0,
              padding: 0,
              overflowX: wrapLines ? 'hidden' : 'auto',
              fontFamily: 'monospace',
              fontSize: '0.75rem',
              lineHeight: '1.45',
              whiteSpace: wrapLines ? 'pre-wrap' : 'pre',
              wordBreak: wrapLines ? 'break-word' : 'normal',
              flex: 1
            }}
          >
            {renderSyntaxHighlightedJson(jsonString, searchQuery)}
          </pre>
        </div>
      )}
    </div>
  );
}

export function SpecRenderer({ jsonContent }: { jsonContent: string }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [expandAll, setExpandAll] = useState(false);
  const [globalWrapLines, setGlobalWrapLines] = useState(false);

  let spec: SpecData = {};
  try {
    const initialParse = typeof jsonContent === 'string' ? JSON.parse(jsonContent) : jsonContent;
    if (initialParse?.content && typeof initialParse.content === 'string') {
      try {
        spec = JSON.parse(initialParse.content);
      } catch {
        spec = initialParse;
      }
    } else {
      spec = initialParse;
    }
  } catch {
    return (
      <div style={{ color: '#ef4444', backgroundColor: '#451a1a', padding: '1rem', borderRadius: '6px', fontSize: '0.85rem' }}>
        Malformed JSON specification payload.
      </div>
    );
  }

  const query = searchQuery.trim().toLowerCase();
  const isSearching = query.length > 0;

  const handleExportOpenApiYaml = () => {
    const openApiObj = convertSpecToOpenApi3(spec);
    const yamlContent = jsonToYaml(openApiObj);

    const blob = new Blob([yamlContent], { type: 'text/yaml;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const filename = `${(spec.name || 'api-spec').toLowerCase().replace(/[^a-z0-9]/g, '-')}-openapi3.yaml`;

    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const filteredInboundActions = useMemo(() => {
    if (!spec.channels?.inboundActions) return [];
    if (!isSearching) return spec.channels.inboundActions;

    return spec.channels.inboundActions.filter((item) => {
      const act = typeof item === 'string' ? { action: item } : item;
      const actionNameMatch = act.action.toLowerCase().includes(query);
      const aliasMatch = act.aliases?.some((a) => a.toLowerCase().includes(query));
      const descMatch = act.description?.toLowerCase().includes(query);
      const payloadMatch = act.payload && JSON.stringify(act.payload).toLowerCase().includes(query);
      const responseMatch = act.responseEvent && JSON.stringify(act.responseEvent).toLowerCase().includes(query);

      return actionNameMatch || aliasMatch || descMatch || payloadMatch || responseMatch;
    });
  }, [spec.channels?.inboundActions, query, isSearching]);

  const filteredOutboundSchemas = useMemo(() => {
    if (!spec.channels?.outboundEventSchemas) return [];
    const entries = Object.entries(spec.channels.outboundEventSchemas);
    if (!isSearching) return entries;

    return entries.filter(([schemaName, schemaData]) => {
      const nameMatch = schemaName.toLowerCase().includes(query);
      const descMatch = schemaData.description?.toLowerCase().includes(query);
      const schemaMatch = schemaData.schema && JSON.stringify(schemaData.schema).toLowerCase().includes(query);

      return nameMatch || descMatch || schemaMatch;
    });
  }, [spec.channels?.outboundEventSchemas, query, isSearching]);

  const getStatusColor = (status?: string) => {
    switch (status?.toUpperCase()) {
      case 'APPROVED': return '#10b981';
      case 'PROPOSED': return '#f59e0b';
      case 'DEPRECATED': return '#ef4444';
      default: return '#38bdf8';
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', color: '#f8fafc', fontSize: '0.875rem' }}>

      {/* Search Bar & Global Controls Header */}
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap', backgroundColor: '#0f172a', padding: '0.75rem', borderRadius: '6px', border: '1px solid #334155' }}>
        <input
          type="text"
          placeholder="Filter actions, payloads, response fields, or schemas..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            flex: 1,
            minWidth: '220px',
            backgroundColor: '#1e293b',
            border: `1px solid ${isSearching ? '#38bdf8' : '#334155'}`,
            color: '#f8fafc',
            padding: '0.45rem 0.75rem',
            borderRadius: '4px',
            fontSize: '0.8rem',
            outline: 'none'
          }}
        />

        {searchQuery && (
          <button
            type="button"
            onClick={() => setSearchQuery('')}
            style={{ backgroundColor: 'transparent', color: '#94a3b8', border: 'none', cursor: 'pointer', fontSize: '0.75rem' }}
          >
            Clear Filter
          </button>
        )}

        <button
          type="button"
          onClick={handleExportOpenApiYaml}
          style={{
            backgroundColor: '#10b98120',
            color: '#10b981',
            border: '1px solid #10b981',
            padding: '0.4rem 0.6rem',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '0.75rem',
            fontWeight: 'bold',
            transition: 'all 0.15s ease'
          }}
        >
          ⬇ Export OpenAPI 3.0 YAML
        </button>

        <button
          type="button"
          onClick={() => setGlobalWrapLines(!globalWrapLines)}
          style={{
            backgroundColor: globalWrapLines ? '#38bdf820' : '#334155',
            color: globalWrapLines ? '#38bdf8' : '#cbd5e1',
            border: `1px solid ${globalWrapLines ? '#38bdf8' : '#334155'}`,
            padding: '0.4rem 0.6rem',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '0.75rem',
            transition: 'all 0.15s ease'
          }}
        >
          {globalWrapLines ? 'Unwrap All' : 'Wrap All'}
        </button>

        <button
          type="button"
          onClick={() => setExpandAll(!expandAll)}
          style={{ backgroundColor: '#334155', color: '#38bdf8', border: 'none', padding: '0.4rem 0.6rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}
        >
          {expandAll ? 'Collapse All' : 'Expand All'}
        </button>
      </div>

      {/* Status Badges */}
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {spec.status && (
          <span style={{ backgroundColor: `${getStatusColor(spec.status)}20`, color: getStatusColor(spec.status), border: `1px solid ${getStatusColor(spec.status)}`, padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 'bold' }}>
            {spec.status}
          </span>
        )}
        {spec.protocol?.transport && (
          <span style={{ backgroundColor: '#0f172a', color: '#38bdf8', border: '1px solid #334155', padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: '0.75rem', fontFamily: 'monospace' }}>
            {spec.protocol.transport} ({spec.protocol.format || 'JSON'})
          </span>
        )}
      </div>

      {spec.description && (
        <p style={{ color: '#cbd5e1', lineHeight: '1.5', margin: 0 }}>{spec.description}</p>
      )}

      {/* Endpoints & Auth Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
        {spec.endpoints && spec.endpoints.length > 0 && (
          <div style={{ backgroundColor: '#0f172a', padding: '1rem', borderRadius: '6px', border: '1px solid #334155' }}>
            <strong style={{ color: '#38bdf8', fontSize: '0.8rem', display: 'block', marginBottom: '0.5rem', letterSpacing: '0.05em' }}>ENDPOINTS</strong>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {spec.endpoints.map((ep, idx) => (
                <div key={idx} style={{ fontFamily: 'monospace', color: '#10b981', fontSize: '0.8rem' }}>
                  {renderHighlightedText(ep, searchQuery)}
                </div>
              ))}
            </div>
          </div>
        )}

        {spec.authentication && (
          <div style={{ backgroundColor: '#0f172a', padding: '1rem', borderRadius: '6px', border: '1px solid #334155' }}>
            <strong style={{ color: '#38bdf8', fontSize: '0.8rem', display: 'block', marginBottom: '0.5rem', letterSpacing: '0.05em' }}>AUTHENTICATION ({spec.authentication.type})</strong>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {spec.authentication.mechanisms?.map((mech, idx) => (
                <div key={idx} style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                  <span style={{ color: '#f8fafc', fontWeight: 'bold' }}>{mech.location}:</span> <code style={{ color: '#38bdf8' }}>{mech.key}</code> {mech.format && `(${mech.format})`}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Inbound Actions */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <strong style={{ color: '#38bdf8', fontSize: '0.85rem', letterSpacing: '0.05em' }}>
            INBOUND ACTIONS ({filteredInboundActions.length})
          </strong>
        </div>

        {filteredInboundActions.length === 0 ? (
          <div style={{ color: '#64748b', fontSize: '0.8rem', fontStyle: 'italic', padding: '0.5rem 0' }}>
            No inbound actions match filter "{searchQuery}".
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {filteredInboundActions.map((item, idx) => {
              const act = typeof item === 'string' ? { action: item } : item;
              const matchesPayload = isSearching && act.payload && JSON.stringify(act.payload).toLowerCase().includes(query);
              const matchesResponse = isSearching && act.responseEvent && JSON.stringify(act.responseEvent).toLowerCase().includes(query);

              return (
                <div key={idx} style={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '6px', padding: '0.85rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
                    <code style={{ color: '#10b981', fontWeight: 'bold', fontSize: '0.9rem' }}>
                      {renderHighlightedText(act.action, searchQuery)}
                    </code>
                    {act.aliases?.map((alias, aIdx) => (
                      <span key={aIdx} style={{ fontSize: '0.7rem', backgroundColor: '#1e293b', color: '#94a3b8', padding: '0.1rem 0.4rem', borderRadius: '3px' }}>
                        alias: {renderHighlightedText(alias, searchQuery)}
                      </span>
                    ))}
                  </div>
                  {act.description && (
                    <p style={{ color: '#94a3b8', margin: '0 0 0.5rem 0', fontSize: '0.8rem' }}>
                      {renderHighlightedText(act.description, searchQuery)}
                    </p>
                  )}

                  <CollapsibleJsonBlock
                    title="Payload Schema"
                    data={act.payload}
                    defaultExpanded={expandAll}
                    forceExpanded={isSearching && matchesPayload}
                    searchQuery={searchQuery}
                    globalWrapLines={globalWrapLines}
                  />
                  <CollapsibleJsonBlock
                    title="Response Event"
                    data={act.responseEvent}
                    defaultExpanded={expandAll}
                    forceExpanded={isSearching && matchesResponse}
                    searchQuery={searchQuery}
                    globalWrapLines={globalWrapLines}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Outbound Event Schemas */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <strong style={{ color: '#38bdf8', fontSize: '0.85rem', letterSpacing: '0.05em' }}>
            OUTBOUND EVENT SCHEMAS ({filteredOutboundSchemas.length})
          </strong>
        </div>

        {filteredOutboundSchemas.length === 0 ? (
          <div style={{ color: '#64748b', fontSize: '0.8rem', fontStyle: 'italic', padding: '0.5rem 0' }}>
            No outbound event schemas match filter "{searchQuery}".
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {filteredOutboundSchemas.map(([schemaName, schemaData], idx) => {
              const matchesSchema = isSearching && schemaData.schema && JSON.stringify(schemaData.schema).toLowerCase().includes(query);

              return (
                <div key={idx} style={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '6px', padding: '0.85rem' }}>
                  <code style={{ color: '#f59e0b', fontWeight: 'bold', fontSize: '0.85rem', display: 'block', marginBottom: '0.4rem' }}>
                    {renderHighlightedText(schemaName, searchQuery)}
                  </code>
                  {schemaData.description && (
                    <p style={{ color: '#94a3b8', margin: '0 0 0.5rem 0', fontSize: '0.8rem' }}>
                      {renderHighlightedText(schemaData.description, searchQuery)}
                    </p>
                  )}

                  <CollapsibleJsonBlock
                    title="Schema Definition"
                    data={schemaData.schema}
                    defaultExpanded={expandAll}
                    forceExpanded={isSearching && matchesSchema}
                    searchQuery={searchQuery}
                    globalWrapLines={globalWrapLines}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}