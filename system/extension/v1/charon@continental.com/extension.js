import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import Soup from 'gi://Soup?version=3.0';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';

// Fallback configuration defaults
const DEFAULT_CHARON_API_URL = 'http://127.0.0.1:8000';
const DEFAULT_CHARON_API_KEY = 'charon-secret-key-change-me';
const DEFAULT_API_KEY_HEADER = 'X-API-Key';
const CLIENT_ID = 'gnome_shell_extension';

export default class CharonExtension extends Extension {
    enable() {
        this._indicator = new PanelMenu.Button(0.0, 'Charon Concierge', false);
        this._statusLabel = new St.Label({
            text: '👔 Charon: Standby',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'charon-panel-label'
        });

        this._indicator.add_child(this._statusLabel);
        Main.panel.addToStatusArea(this.uuid, this._indicator);

        this._session = new Soup.Session();
        this._wsConnection = null;

        // Load Extension Settings safely
        try {
            this._settings = this.getSettings();
        } catch (e) {
            console.warn(`[Charon] Could not load extension settings schema: ${e.message}`);
            this._settings = null;
        }

        // UI references for Overseer telemetry menu items
        this._overseerHeader = null;
        this._overseerDetails = null;

        this._buildMenu();
        this._initWebSocket();
        this._registerShortcut();
    }

    // --- Configuration Accessors ---
    _getApiUrl() {
        if (this._settings) {
            try { return this._settings.get_string('api-url') || DEFAULT_CHARON_API_URL; } catch (e) {}
        }
        return DEFAULT_CHARON_API_URL;
    }

    _getApiKey() {
        if (this._settings) {
            try { return this._settings.get_string('api-key') || DEFAULT_CHARON_API_KEY; } catch (e) {}
        }
        return DEFAULT_CHARON_API_KEY;
    }

    _getApiKeyHeader() {
        if (this._settings) {
            try { return this._settings.get_string('api-key-header') || DEFAULT_API_KEY_HEADER; } catch (e) {}
        }
        return DEFAULT_API_KEY_HEADER;
    }

    _registerShortcut() {
        try {
            if (!this._settings) {
                this._settings = this.getSettings();
            }
            Main.wm.addKeybinding(
                'toggle-shortcut',
                this._settings,
                Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
                Shell.ActionMode.ALL,
                () => { this._toggleMenuAndFocus(); }
            );
        } catch (e) {
            console.error(`[Charon] Failed to register keybinding: ${e.message}`);
        }
    }

    _unregisterShortcut() {
        if (this._settings) {
            Main.wm.removeKeybinding('toggle-shortcut');
        }
    }

    _toggleMenuAndFocus() {
        if (!this._indicator) return;
        this._indicator.menu.toggle();

        if (this._indicator.menu.isOpen && this._entry) {
            GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                this._entry.clutter_text.grab_key_focus();
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    _buildMenu() {
        // --- 1. HEADER SECTION ---
        let headerItem = new PopupMenu.PopupMenuItem('Charon Mechatronics Concierge', { reactive: false });
        headerItem.label.style = 'font-weight: bold; color: #888;';
        this._indicator.menu.addMenuItem(headerItem);
        this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // --- 2. OVERSEER TELEMETRY SECTION ---
        this._overseerHeader = new PopupMenu.PopupMenuItem('⚙️ Overseer: Initializing...', { reactive: false });
        this._overseerHeader.label.style = 'font-size: 0.9em; color: #3584e4; font-weight: bold;';
        this._indicator.menu.addMenuItem(this._overseerHeader);

        this._overseerDetails = new PopupMenu.PopupMenuItem('  Queue: 0 | Engine: Checking...', { reactive: false });
        this._overseerDetails.label.style = 'font-size: 0.8em; color: #aaa;';
        this._indicator.menu.addMenuItem(this._overseerDetails);

        this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // --- 3. COMMAND ENTRY SECTION ---
        let entryItem = new PopupMenu.PopupBaseMenuItem({ reactive: false });
        this._entry = new St.Entry({
            hint_text: 'Ask Charon a question or command...',
            can_focus: true,
            x_expand: true,
            style_class: 'charon-prompt-entry'
        });

        this._entry.clutter_text.connect('activate', () => {
            let text = this._entry.get_text();
            if (text.trim().length > 0) {
                this._submitTask(text);
                this._entry.set_text('');
                this._indicator.menu.close();
            }
        });

        entryItem.add_child(this._entry);
        this._indicator.menu.addMenuItem(entryItem);
        this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // --- 4. CONTROLS SECTION ---
        let pingItem = new PopupMenu.PopupMenuItem('🔄 Reconnect WebSocket');
        pingItem.connect('activate', () => this._initWebSocket());
        this._indicator.menu.addMenuItem(pingItem);
    }

    _initWebSocket() {
        if (this._wsConnection) return;

        const apiUrl = this._getApiUrl();
        const apiKey = this._getApiKey();
        const apiHeader = this._getApiKeyHeader();

        const wsUrl = `${apiUrl.replace('http', 'ws')}/v1/ws?client_id=${CLIENT_ID}&api_key=${encodeURIComponent(apiKey)}`;
        let message = Soup.Message.new('GET', wsUrl);
        message.request_headers.append(apiHeader, apiKey);

        this._session.websocket_connect_async(message, null, null, GLib.PRIORITY_DEFAULT, null, (session, res) => {
            try {
                this._wsConnection = session.websocket_connect_finish(res);
                this._updateStatus('👔 Charon: Online');

                this._wsConnection.connect('message', (ws, type, data) => {
                    if (type !== Soup.WebsocketDataType.TEXT) return;

                    let textMsg = new TextDecoder().decode(data.toArray());
                    this._handleWebSocketMessage(JSON.parse(textMsg));
                });

                this._wsConnection.connect('closed', () => {
                    this._wsConnection = null;
                    this._updateStatus('⚠️ Charon: WS Disconnected');
                    if (this._overseerHeader) {
                        this._overseerHeader.label.set_text('⚙️ Overseer: Disconnected');
                    }
                });
            } catch (e) {
                this._updateStatus('⚠️ Charon: Offline');
                console.error(`[Charon] WS Connection failed: ${e.message}`);
            }
        });
    }

    _handleWebSocketMessage(payload) {
        const eventType = payload.event_type || payload.type;
        const data = payload.data || {};

        switch (eventType) {
            case 'overseer_report':
                this._updateOverseerTelemetry(data);
                break;

            case 'system_alert':
                this._handleSystemAlert(data);
                break;

            case 'gatekeeper_intercept':
            case 'GatekeeperIntercept':
                this._handleGatekeeperIntercept(data);
                break;

            case 'task_complete':
            case 'TaskCompleted':
                this._updateStatus('👔 Charon: Standby');
                this._handleTaskComplete(data, payload);
                break;

            case 'status_change':
            case 'status':
                let statusText = data.status || payload.message || 'Processing';
                this._updateStatus(`👔 Charon: ${statusText}`);
                break;

            case 'agent_log':
                break;

            default:
                console.log(`[Charon] Unhandled WS Event Type: ${eventType}`);
        }
    }

    _updateOverseerTelemetry(data) {
        const engineOnline = data.engine_online ?? false;
        const engineStatus = engineOnline ? '🟢 Online' : '🔴 Offline';
        const queueDepth = data.queue_depth ?? 0;
        const currentTask = (data.current_task && data.current_task !== 'Idle') ? `Task: ${data.current_task}` : 'Idle';

        if (this._overseerHeader) {
            this._overseerHeader.label.set_text(`⚙️ Overseer: ${engineOnline ? 'Nominal' : 'DEGRADED'}`);
        }

        if (this._overseerDetails) {
            this._overseerDetails.label.set_text(`  Engine: ${engineStatus} | Queue: ${queueDepth} | ${currentTask}`);
        }

        if (this._statusLabel) {
            let currentLabelText = this._statusLabel.get_text();
            if (!engineOnline) {
                this._updateStatus('⚠️ Charon: Engine Offline');
            } else if (currentLabelText === '⚠️ Charon: Engine Offline') {
                this._updateStatus('👔 Charon: Standby');
            }
        }
    }

    _handleSystemAlert(alert) {
        const title = `⚠️ Overseer Alert: ${alert.title || 'Attention Required'}`;
        const message = alert.message || 'System condition requires inspection.';

        this._updateStatus(`⚠️ Alert: ${alert.title || 'System Alert'}`);

        const source = new MessageTray.Source('Charon Overseer', 'dialog-warning-symbolic');
        Main.messageTray.add(source);

        const notification = new MessageTray.Notification(source, title, message);
        if (alert.severity === 'CRITICAL') {
            notification.setUrgency(MessageTray.Urgency.CRITICAL);
        }

        source.showNotification(notification);
    }

    _submitTask(taskText) {
        this._updateStatus('🔄 Charon: Transmitting...');

        try {
            let message = Soup.Message.new('POST', `${this._getApiUrl()}/v1/task`);
            message.request_headers.append(this._getApiKeyHeader(), this._getApiKey());

            let payload = JSON.stringify({
                prompt: taskText,
                client_id: CLIENT_ID,
                context: { origin: 'gnome_shell_panel' }
            });

            let encoder = new TextEncoder();
            let uint8array = encoder.encode(payload);
            let bytes = new GLib.Bytes(uint8array);

            message.set_request_body_from_bytes('application/json', bytes);

            this._session.send_and_read_async(message, GLib.PRIORITY_DEFAULT, null, (session, res) => {
                try {
                    session.send_and_read_finish(res);
                    let status = message.get_status();

                    if (status === Soup.Status.OK || status === Soup.Status.ACCEPTED) {
                        this._updateStatus('🔄 Charon: Queued');
                    } else {
                        this._updateStatus('⚠️ Task Rejected');
                        Main.notify('👔 Charon Error', `HTTP ${status}`);
                    }
                } catch (e) {
                    this._updateStatus('⚠️ API Unreachable');
                    console.error(`[Charon] Async request failed: ${e.message}`);
                }
            });
        } catch (e) {
            this._updateStatus('⚠️ Internal Error');
            console.error(`[Charon] Task submission error: ${e.message}`);
        }
    }

    _handleGatekeeperIntercept(data) {
        this._updateStatus('⚠️ Gatekeeper: Approval Needed');

        const approvalId = data.approval_id || 'unknown_id';
        const actionText = data.action || data.manifest || 'Restricted Operation';

        const source = new MessageTray.Source('Charon Gatekeeper', 'dialog-warning-symbolic');
        Main.messageTray.add(source);

        const notification = new MessageTray.Notification(
            source,
            '👔 Charon: Management Approval Required',
            `Gatekeeper intercepted action:\n${actionText}`
        );

        notification.setUrgency(MessageTray.Urgency.CRITICAL);
        notification.addButton('approve-btn', 'Approve (Proceed)');
        notification.addButton('deny-btn', 'Rescind');

        notification.connect('action-invoked', (notif, actionId) => {
            if (actionId === 'approve-btn') {
                this._respondGatekeeper(approvalId, 'proceed', 'Approved via GNOME Panel');
            } else {
                this._respondGatekeeper(approvalId, 'rescind', 'Rescinded via GNOME Panel');
            }
        });

        source.showNotification(notification);
    }

    _respondGatekeeper(approvalId, decision, notes = '') {
        this._updateStatus('🔄 Gatekeeper: Transmitting...');

        try {
            let message = Soup.Message.new('POST', `${this._getApiUrl()}/v1/gatekeeper/respond`);
            message.request_headers.append(this._getApiKeyHeader(), this._getApiKey());

            let payload = JSON.stringify({
                approval_id: approvalId,
                decision: decision,
                client_id: CLIENT_ID,
                notes: notes
            });

            let encoder = new TextEncoder();
            let bytes = new GLib.Bytes(encoder.encode(payload));
            message.set_request_body_from_bytes('application/json', bytes);

            this._session.send_and_read_async(message, GLib.PRIORITY_DEFAULT, null, (session, res) => {
                try {
                    session.send_and_read_finish(res);
                    if (message.get_status() === Soup.Status.OK) {
                        this._updateStatus('👔 Charon: Decision Sent');
                    }
                } catch (e) {
                    console.error(`[Charon] Gatekeeper response error: ${e.message}`);
                }
            });
        } catch (e) {
            console.error(`[Charon] Gatekeeper dispatch exception: ${e.message}`);
        }
    }

    _handleTaskComplete(data, payload) {
        const summary = data.summary || payload.summary || 'Task executed successfully.';
        const recommendation = data.recommendation || data.phrase;
        const nextStep = data.next_step || data.suggested_prompt;

        const source = new MessageTray.Source('Charon', 'emblem-ok-symbolic');
        Main.messageTray.add(source);

        let bodyText = summary;
        if (recommendation) {
            bodyText += `\n\n💡 Concierge: ${recommendation}`;
        }

        const notification = new MessageTray.Notification(source, '👔 Charon: Task Complete', bodyText);

        if (nextStep) {
            notification.addButton('concierge-next-step', 'Execute Next Step');
            notification.connect('action-invoked', (notif, actionId) => {
                if (actionId === 'concierge-next-step') {
                    this._submitTask(nextStep);
                }
            });
        }

        source.showNotification(notification);
    }

    _updateStatus(text) {
        if (this._statusLabel) {
            this._statusLabel.set_text(text);
        }
    }

    disable() {
        this._unregisterShortcut();

        if (this._wsConnection) {
            this._wsConnection.close(Soup.WebsocketCloseCode.NORMAL, 'Extension disabled');
            this._wsConnection = null;
        }

        if (this._session) {
            this._session.abort();
            this._session = null;
        }

        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }

        this._settings = null;
        this._overseerHeader = null;
        this._overseerDetails = null;
    }
}