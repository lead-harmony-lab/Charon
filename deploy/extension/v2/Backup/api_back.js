// api.js
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';

const CLIENT_ID = 'gnome_shell_extension';

export class CharonAPI {
    constructor(apiUrl, apiKey, apiKeyHeader) {
        this.apiUrl = apiUrl;
        this.apiKey = apiKey;
        this.apiKeyHeader = apiKeyHeader;
        this.session = new Soup.Session();
        this.wsConnection = null;

        // --- Offline Queues ---
        this._taskQueue = [];
        this._gatekeeperQueue = [];
        this._telemetryQueue = [];
    }

    // --- QUEUE MANAGEMENT ---
    flushQueues() {
        if (this._telemetryQueue.length > 0 && this.wsConnection && this.wsConnection.get_state() === Soup.WebsocketState.OPEN) {
            let tQueue = [...this._telemetryQueue];
            this._telemetryQueue = [];
            tQueue.forEach(payload => this.sendTelemetry(payload));
        }

        if (this._taskQueue.length > 0) {
            let tq = [...this._taskQueue];
            this._taskQueue = [];
            tq.forEach(retryFn => retryFn());
        }

        if (this._gatekeeperQueue.length > 0) {
            let gq = [...this._gatekeeperQueue];
            this._gatekeeperQueue = [];
            gq.forEach(retryFn => retryFn());
        }
    }

    // --- WEBSOCKET API: Submit Task ---
    submitTaskAsync(prompt, agentOverride = null, contextObj = {}) {
        return new Promise((resolve, reject) => {
            let payload = JSON.stringify({
                action: 'submit_task',
                client_id: CLIENT_ID,
                prompt: prompt,
                agent_override: agentOverride,
                context: contextObj
            });

            const attempt = () => {
                if (this.wsConnection && this.wsConnection.get_state() === Soup.WebsocketState.OPEN) {
                    try {
                        this.wsConnection.send_text(payload);
                        resolve(200); // Resolving to satisfy legacy UI promise chains
                    } catch (e) {
                        console.warn(`[Charon API] Task WS send failed, queuing offline: ${e.message}`);
                        this._taskQueue.push(attempt);
                    }
                } else {
                    console.warn(`[Charon API] Offline. Queuing task.`);
                    this._taskQueue.push(attempt);
                }
            };

            attempt();
        });
    }

    // --- WEBSOCKET API: Gatekeeper Response ---
    respondGatekeeperAsync(approvalId, decision, notes = '') {
        let payload = JSON.stringify({
            action: 'gatekeeper_respond',
            client_id: CLIENT_ID,
            approval_id: approvalId,
            decision: decision,
            notes: notes
        });

        const attempt = () => {
            if (this.wsConnection && this.wsConnection.get_state() === Soup.WebsocketState.OPEN) {
                try {
                    this.wsConnection.send_text(payload);
                } catch (e) {
                    console.warn(`[Charon API] Gatekeeper WS send failed, queuing offline: ${e.message}`);
                    this._gatekeeperQueue.push(attempt);
                }
            } else {
                console.warn(`[Charon API] Offline. Queuing gatekeeper response.`);
                this._gatekeeperQueue.push(attempt);
            }
        };

        attempt();
    }

    // --- WEBSOCKETS ---
    connectWebSocket(onMessageCallback, onClosedCallback) {
        if (this.wsConnection) return;

        const wsUrl = `${this.apiUrl.replace('http', 'ws')}/v1/ws?client_id=${CLIENT_ID}&api_key=${encodeURIComponent(this.apiKey)}`;
        let message = Soup.Message.new('GET', wsUrl);
        message.request_headers.append(this.apiKeyHeader, this.apiKey);

        this.session.websocket_connect_async(message, null, null, GLib.PRIORITY_DEFAULT, null, (session, res) => {
            try {
                this.wsConnection = session.websocket_connect_finish(res);

                // Flush queues now that we've established a connection
                this.flushQueues();

                this.wsConnection.connect('message', (ws, type, data) => {
                    if (type === Soup.WebsocketDataType.TEXT) {
                        let textMsg = new TextDecoder().decode(data.get_data());
                        onMessageCallback(JSON.parse(textMsg));
                    }
                });

                this.wsConnection.connect('closed', () => {
                    this.wsConnection = null;
                    onClosedCallback();
                });
            } catch (e) {
                console.error(`[Charon API] WS Connection failed: ${e.message}`);
                onClosedCallback(e);
            }
        });
    }

    abort() {
        if (this.wsConnection) {
            this.wsConnection.close(Soup.WebsocketCloseCode.NORMAL, 'Extension disabled');
            this.wsConnection = null;
        }
        if (this.session) {
            this.session.abort();
        }

        // Clear queues on hard abort to prevent memory leaks or stale closures on extension restart
        this._taskQueue = [];
        this._gatekeeperQueue = [];
        this._telemetryQueue = [];
    }

    // --- WEBSOCKETS: Telemetry Upstream ---
    sendTelemetry(payload) {
        if (!this.wsConnection || this.wsConnection.get_state() !== Soup.WebsocketState.OPEN) {
            // Queue telemetry silently when offline
            this._telemetryQueue.push(payload);
            return;
        }

        let textData = JSON.stringify(payload);
        this.wsConnection.send_text(textData);
    }
}