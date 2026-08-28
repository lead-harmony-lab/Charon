// api.js
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';

const CLIENT_ID = 'gnome_shell_extension';
const MAX_QUEUE_SIZE = 1000;

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

        // --- Reconnection State ---
        this._reconnectDelay = 1000;
        this._maxReconnectDelay = 30000;
        this._reconnectTimeoutId = null;
        this._isAborting = false;
    }

    // --- QUEUE MANAGEMENT ---
    flushQueues() {
        if (!this.wsConnection || this.wsConnection.get_state() !== Soup.WebsocketState.OPEN) return;

        // Flush Telemetry
        let tQueue = [...this._telemetryQueue];
        this._telemetryQueue = [];
        tQueue.forEach(payload => this.sendTelemetry(payload));

        // Flush Tasks
        let tq = [...this._taskQueue];
        this._taskQueue = [];
        tq.forEach(payload => this._sendTextSafe(payload, this._taskQueue));

        // Flush Gatekeeper
        let gq = [...this._gatekeeperQueue];
        this._gatekeeperQueue = [];
        gq.forEach(payload => this._sendTextSafe(payload, this._gatekeeperQueue));
    }

    _sendTextSafe(payload, fallbackQueue) {
        if (this.wsConnection && this.wsConnection.get_state() === Soup.WebsocketState.OPEN) {
            try {
                this.wsConnection.send_text(payload);
            } catch (e) {
                console.warn(`[Charon API] WS send failed, queuing offline: ${e.message}`);
                this._enforceQueueLimit(fallbackQueue, payload);
            }
        } else {
            this._enforceQueueLimit(fallbackQueue, payload);
        }
    }

    _enforceQueueLimit(queue, item) {
        if (queue.length >= MAX_QUEUE_SIZE) queue.shift();
        queue.push(item);
    }

    // --- WEBSOCKET API: Submit Task ---
    submitTaskAsync(prompt, agentOverride = null, contextObj = {}) {
        return new Promise((resolve) => {
            let payload = JSON.stringify({
                action: 'submit_task',
                client_id: CLIENT_ID,
                prompt: prompt,
                agent_override: agentOverride,
                context: contextObj
            });

            if (this.wsConnection && this.wsConnection.get_state() === Soup.WebsocketState.OPEN) {
                try {
                    this.wsConnection.send_text(payload);
                    resolve(200); // Success
                } catch (e) {
                    console.warn(`[Charon API] Task WS send failed, queuing offline: ${e.message}`);
                    this._enforceQueueLimit(this._taskQueue, payload);
                    resolve(202); // 202 Accepted/Queued to prevent UI hanging
                }
            } else {
                console.warn(`[Charon API] Offline. Queuing task.`);
                this._enforceQueueLimit(this._taskQueue, payload);
                resolve(202); // 202 Accepted/Queued
            }
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

        this._sendTextSafe(payload, this._gatekeeperQueue);
    }

    // --- WEBSOCKETS ---
    connectWebSocket(onMessageCallback, onClosedCallback) {
        if (this.wsConnection) return;
        this._isAborting = false;

        const wsUrl = `${this.apiUrl.replace('http', 'ws')}/v1/ws?client_id=${CLIENT_ID}&api_key=${encodeURIComponent(this.apiKey)}`;
        console.log(`[Charon API DEBUG] Attempting to connect to: ${wsUrl}`);
        let message = Soup.Message.new('GET', wsUrl);
        message.request_headers.append(this.apiKeyHeader, this.apiKey);

        this.session.websocket_connect_async(message, null, null, GLib.PRIORITY_DEFAULT, null, (session, res) => {
            try {
                this.wsConnection = session.websocket_connect_finish(res);

                // Reset backoff delay on successful connection
                this._reconnectDelay = 1000;

                this.flushQueues();

                this.wsConnection.connect('message', (ws, type, data) => {
                    if (type === Soup.WebsocketDataType.TEXT) {
                        let textMsg = new TextDecoder().decode(data.get_data());
                        onMessageCallback(JSON.parse(textMsg));
                    }
                });

                this.wsConnection.connect('closed', () => {
                    this.wsConnection = null;
                    this._handleDisconnect(onMessageCallback, onClosedCallback);
                });
            } catch (e) {
                console.error(`[Charon API] WS Connection failed: ${e.message}`);
                this._handleDisconnect(onMessageCallback, onClosedCallback);
            }
        });
    }

    _handleDisconnect(onMessageCallback, onClosedCallback) {
        if (this._isAborting) {
            onClosedCallback();
            return;
        }

        console.warn(`[Charon API] Disconnected. Reconnecting in ${this._reconnectDelay}ms...`);

        if (this._reconnectTimeoutId) {
            GLib.source_remove(this._reconnectTimeoutId);
        }

        this._reconnectTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, this._reconnectDelay, () => {
            this._reconnectTimeoutId = null;
            this.connectWebSocket(onMessageCallback, onClosedCallback);
            return GLib.SOURCE_REMOVE;
        });

        // Increase backoff delay exponentially up to the max limit
        this._reconnectDelay = Math.min(this._reconnectDelay * 2, this._maxReconnectDelay);
    }

    abort() {
        this._isAborting = true;

        if (this._reconnectTimeoutId) {
            GLib.source_remove(this._reconnectTimeoutId);
            this._reconnectTimeoutId = null;
        }

        if (this.wsConnection) {
            this.wsConnection.close(Soup.WebsocketCloseCode.NORMAL, 'Extension disabled');
            this.wsConnection = null;
        }
        if (this.session) {
            this.session.abort();
        }

        this._taskQueue = [];
        this._gatekeeperQueue = [];
        this._telemetryQueue = [];
    }

    // --- WEBSOCKETS: Telemetry Upstream ---
    sendTelemetry(payload) {
        if (!this.wsConnection || this.wsConnection.get_state() !== Soup.WebsocketState.OPEN) {
            this._enforceQueueLimit(this._telemetryQueue, payload);
            return;
        }

        let textData = typeof payload === 'string' ? payload : JSON.stringify(payload);
        this._sendTextSafe(textData, this._telemetryQueue);
    }
}