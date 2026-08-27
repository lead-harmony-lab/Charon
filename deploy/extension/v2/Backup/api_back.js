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
    }

    // --- REST API: Submit Task ---
    submitTaskAsync(prompt, agentOverride = null, contextObj = {}) {
        let message = Soup.Message.new('POST', `${this.apiUrl}/v1/task`);
        message.request_headers.append(this.apiKeyHeader, this.apiKey);

        let payload = JSON.stringify({
            prompt: prompt,
            client_id: CLIENT_ID,
            agent_override: agentOverride,
            context: contextObj
        });

        let bytes = new GLib.Bytes(new TextEncoder().encode(payload));
        message.set_request_body_from_bytes('application/json', bytes);

        return new Promise((resolve, reject) => {
            this.session.send_and_read_async(message, GLib.PRIORITY_DEFAULT, null, (session, res) => {
                try {
                    session.send_and_read_finish(res);
                    let statusCode = message.get_status();

                    // Libsoup 3 doesn't throw GError on HTTP status errors (4xx/5xx)
                    if (statusCode >= 200 && statusCode < 300) {
                        resolve(statusCode);
                    } else {
                        reject(new Error(`HTTP ${statusCode}: ${message.get_reason_phrase() || 'Server Error'}`));
                    }
                } catch (e) {
                    reject(e);
                }
            });
        });
    }

    // --- REST API: Gatekeeper Response ---
    respondGatekeeperAsync(approvalId, decision, notes = '') {
        let message = Soup.Message.new('POST', `${this.apiUrl}/v1/gatekeeper/respond`);
        message.request_headers.append(this.apiKeyHeader, this.apiKey);

        let payload = JSON.stringify({
            approval_id: approvalId,
            decision: decision,
            client_id: CLIENT_ID,
            notes: notes
        });

        let bytes = new GLib.Bytes(new TextEncoder().encode(payload));
        message.set_request_body_from_bytes('application/json', bytes);

        this.session.send_and_read_async(message, GLib.PRIORITY_DEFAULT, null, (s, r) => {
            try {
                s.send_and_read_finish(r);
            } catch (e) {
                console.error(`[Charon API] Gatekeeper response failed: ${e.message}`);
            }
        });
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
    }

    // --- WEBSOCKETS: Telemetry Upstream ---
    sendTelemetry(payload) {

        if (!this.wsConnection) {
            console.log("[Charon Telemetry] FAILED: WebSocket connection object is null.");
            return;
        }

        const state = this.wsConnection.get_state();
        if (state === Soup.WebsocketState.OPEN) {
            let textData = JSON.stringify(payload);
            this.wsConnection.send_text(textData);
            // console.log("[Charon Telemetry] Successfully pushed to socket."); // Uncomment if you want spam, but the attempt log is usually enough
        } else {
            console.log(`[Charon Telemetry] FAILED: Socket state is not OPEN. Current state: ${state}`);
        }
    }
}