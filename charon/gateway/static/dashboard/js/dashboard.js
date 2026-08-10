/**
 * Charon Dashboard Control Interface
 * File: gateway/static/dashboard/js/dashboard.js
 */

// 1. Resolve API Key from URL query param, localStorage, or user prompt
function getApiKey() {
    const urlParams = new URLSearchParams(window.location.search);
    let apiKey = urlParams.get('api_key');

    if (apiKey) {
        localStorage.setItem('charon_api_key', apiKey);
        // Clean URL parameter to prevent exposing key in address bar / history
        const cleanUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
        window.history.replaceState({ path: cleanUrl }, '', cleanUrl);
    } else {
        apiKey = localStorage.getItem('charon_api_key');
    }

    if (!apiKey) {
        apiKey = prompt("Please enter your Charon API Key:");
        if (apiKey) {
            apiKey = apiKey.trim();
            localStorage.setItem('charon_api_key', apiKey);
        }
    }

    return apiKey || '';
}

const API_KEY = getApiKey();

// 2. Dynamic Host & Protocol Resolution
const HOST = window.location.host || 'localhost:8000';
const HTTP_PROTOCOL = window.location.protocol === 'https:' ? 'https:' : 'http:';
const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

const API_BASE = `${HTTP_PROTOCOL}//${HOST}/v1/router`;

// 3. Authenticated Fetch Helper
async function authFetch(url, options = {}) {
    const headers = {
        'X-API-Key': API_KEY,
        ...(options.headers || {})
    };

    const response = await fetch(url, { ...options, headers });

    if (response.status === 401) {
        localStorage.removeItem('charon_api_key');
        alert("Invalid or missing API key token. Page will reload to re-authenticate.");
        window.location.reload();
    }

    return response;
}

// 4. Authenticated WebSocket Connection
let ws;

function initWS() {
    const clientId = 'dashboard_ui';
    const wsUrl = `${WS_PROTOCOL}//${HOST}/v1/ws?client_id=${clientId}&api_key=${encodeURIComponent(API_KEY)}`;

    ws = new WebSocket(wsUrl);
    const badge = document.getElementById('ws-status');

    ws.onopen = () => {
        if (badge) {
            badge.textContent = 'WebSocket: Connected';
            badge.className = 'status-badge online';
        }
    };

    ws.onclose = () => {
        if (badge) {
            badge.textContent = 'WebSocket: Disconnected (Retrying...)';
            badge.className = 'status-badge offline';
        }
        setTimeout(initWS, 3000);
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.event_type === 'telemetry_trace' && msg.data?.event_type === 'TRIAGE_DECISION') {
                appendTriageLog(msg.data.details);
            } else if (msg.event_type === 'router_agent_updated' || msg.event_type === 'router_tool_toggled') {
                loadAgents();
            }
        } catch (err) {
            console.error("[Dashboard] Failed to parse WebSocket message:", err);
        }
    };
}

// 5. REST API Handlers
async function loadAgents() {
    try {
        const res = await authFetch(`${API_BASE}/agents`);
        if (!res.ok) return;

        const data = await res.json();
        const container = document.getElementById('agent-list');
        if (!container) return;
        container.innerHTML = '';

        Object.entries(data.agents || {}).forEach(([agentId, agent]) => {
            const card = document.createElement('div');
            card.className = 'agent-card';
            card.innerHTML = `
                <div class="agent-header">
                    <span class="agent-title">${agent.name || agentId}</span>
                    <label>Weight: 
                        <input type="number" step="0.1" min="0.1" max="5.0" value="${agent.priority_weight || 1.0}" 
                               class="weight-input" onchange="updateWeight('${agentId}', this.value)">
                    </label>
                </div>
                <p class="text-muted" style="font-size:0.85rem">${agent.description || ''}</p>
                <div class="tools-container">
                    <strong>Tools:</strong>
                    ${(agent.active_tools || []).map(t => `
                        <span class="tool-tag">
                            <input type="checkbox" ${t.enabled !== false ? 'checked' : ''} 
                                   onchange="toggleTool('${agentId}', '${t.name}', this.checked)">
                            ${t.name}
                        </span>
                    `).join('')}
                </div>
            `;
            container.appendChild(card);
        });
    } catch (err) {
        console.error("[Dashboard] Error loading agents:", err);
    }
}

async function updateWeight(agentId, weight) {
    await authFetch(`${API_BASE}/agents/${agentId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ priority_weight: parseFloat(weight) })
    });
}

async function toggleTool(agentId, toolName, enabled) {
    await authFetch(`${API_BASE}/agents/${agentId}/tools`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool_name: toolName, enabled })
    });
}

function appendTriageLog(details) {
    const stream = document.getElementById('triage-stream');
    if (!stream || !details) return;

    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `
        <div><strong>Prompt:</strong> "${details.prompt || ''}"</div>
        <div><strong>Selected:</strong> <span style="color:var(--accent)">${details.selected_agent || ''}</span> (Score: ${details.confidence_score ?? ''})</div>
        <div class="text-muted">Candidates: ${JSON.stringify(details.candidate_scores || {})}</div>
    `;
    stream.prepend(entry);
}

async function loadRules() {
    try {
        const res = await authFetch(`${API_BASE}/rules`);
        if (!res.ok) return;

        const data = await res.json();
        const tbody = document.getElementById('rules-list');
        if (!tbody) return;
        tbody.innerHTML = '';

        (data.rules || []).forEach(r => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><code>${r.trigger}</code></td>
                <td>${r.target_agent}</td>
                <td>${r.description || ''}</td>
                <td><button class="btn" style="background:var(--danger)" onclick="deleteRule('${r.rule_id}')">Delete</button></td>
            `;
            tbody.appendChild(row);
        });
    } catch (err) {
        console.error("[Dashboard] Error loading rules:", err);
    }
}

const ruleForm = document.getElementById('rule-form');
if (ruleForm) {
    ruleForm.onsubmit = async (e) => {
        e.preventDefault();
        const trigger = document.getElementById('rule-trigger').value;
        const target_agent = document.getElementById('rule-target').value;
        const description = document.getElementById('rule-desc').value;

        await authFetch(`${API_BASE}/rules`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trigger, target_agent, description })
        });

        e.target.reset();
        loadRules();
    };
}

async function deleteRule(ruleId) {
    await authFetch(`${API_BASE}/rules/${ruleId}`, { method: 'DELETE' });
    loadRules();
}

// Initialize components
initWS();
loadAgents();
loadRules();