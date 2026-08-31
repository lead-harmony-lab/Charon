// ui.js
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Pango from 'gi://Pango';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';
import * as DND from 'resource:///org/gnome/shell/ui/dnd.js';
import * as ModalDialog from 'resource:///org/gnome/shell/ui/modalDialog.js';

export class CharonUI {
    constructor(extension) {
        this.ext = extension;
        this._logMaxLines = 4;
        this._logQueue = [];
        this._lastTaskState = 'Idle';
        this._lastResponseText = '';
        this._avatarSubprocess = null;
        this._isDestroying = false;

        this.indicator = new PanelMenu.Button(0.0, 'Charon Concierge', false);
        this.statusLabel = new St.Label({
            text: '👔 Charon: Standby',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'charon-panel-label'
        });
        this.indicator.add_child(this.statusLabel);

        this._setupDND();
        this._buildMenu();
    }

    _setupDND() {
        this.indicator._delegate = {
            handleDragOver: () => DND.DragMotionResult.COPY_DROP,
            acceptDrop: (source) => {
                let uris = typeof source.getUris === 'function' ? source.getUris() : (source.isUriList ? source.getUris() : []);
                if (uris && uris.length > 0) {
                    this._handleDroppedUri(uris[0]);
                    return true;
                }
                return false;
            }
        };
    }

    _buildMenu() {
        let headerItem = new PopupMenu.PopupMenuItem('Charon Mechatronics Concierge', { reactive: false });
        headerItem.label.style = 'font-weight: bold; color: #888;';
        this.indicator.menu.addMenuItem(headerItem);
        this.indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this.overseerHeader = new PopupMenu.PopupMenuItem('⚙️ Overseer: Initializing...', { reactive: false });
        this.overseerHeader.label.style = 'font-size: 0.9em; color: #3584e4; font-weight: bold;';
        this.indicator.menu.addMenuItem(this.overseerHeader);

        this.overseerDetails = new PopupMenu.PopupMenuItem('  Queue: 0 | Engine: Checking...', { reactive: false });
        this.overseerDetails.label.style = 'font-size: 0.8em; color: #aaa;';
        this.indicator.menu.addMenuItem(this.overseerDetails);
        this.indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        let currentSettings = this.ext.readOverlaySettings();
        let shouldShowAvatar = currentSettings.show_avatar === true;

        this.avatarAction = new PopupMenu.PopupBaseMenuItem();
        let avatarActionBox = new St.BoxLayout({ x_expand: true, vertical: false });
        let avatarActionLabel = new St.Label({ text: 'Display Avatar', y_align: Clutter.ActorAlign.CENTER, x_expand: true });

        this.avatarStatusPill = new St.Label({
            text: '',
            y_align: Clutter.ActorAlign.CENTER,
        });

        avatarActionBox.add_child(avatarActionLabel);
        avatarActionBox.add_child(this.avatarStatusPill);
        this.avatarAction.add_child(avatarActionBox);

        this._updateAvatarActionUI(shouldShowAvatar);

        this.avatarAction.connect('activate', () => {
            let isCurrentlyShowing = this.ext.readOverlaySettings().show_avatar === true;
            let newState = !isCurrentlyShowing;

            if (!this._isDestroying) {
                let data = this.ext.readOverlaySettings();
                data.show_avatar = newState;
                this.ext.writeOverlaySettings(data);
            }

            this._updateAvatarActionUI(newState);
            this._toggleAvatar(newState);
        });

        this.indicator.menu.addMenuItem(this.avatarAction);
        this.indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        let responseCardItem = new PopupMenu.PopupBaseMenuItem({ reactive: false });
        let cardBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style: 'max-width: 400px; padding: 6px; background-color: rgba(255,255,255,0.05); border-radius: 6px;'
        });

        let responseTitle = new St.Label({ text: '💬 Latest Response:', style: 'font-weight: bold; font-size: 0.85em; color: #3584e4; margin-bottom: 4px;' });
        cardBox.add_child(responseTitle);

        this.responseTextLabel = new St.Label({ text: 'No active response.', x_expand: true, style: 'font-size: 0.85em; color: #eee; max-width: 380px;' });
        this.responseTextLabel.clutter_text.line_wrap = true;
        this.responseTextLabel.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
        cardBox.add_child(this.responseTextLabel);

        let btnRow = new St.BoxLayout({ vertical: false, x_expand: true, style: 'margin-top: 8px;' });
        let copyBtn = new St.Button({ label: '📋 Copy Response', style_class: 'button', can_focus: true, x_expand: true, style: 'padding: 4px 8px; font-size: 0.8em; margin-right: 4px;' });
        copyBtn.connect('clicked', () => this._copyResponseToClipboard());

        let openLogBtn = new St.Button({ label: '📂 Open Log', style_class: 'button', can_focus: true, x_expand: true, style: 'padding: 4px 8px; font-size: 0.8em;' });
        openLogBtn.connect('clicked', () => this._openChatLogFile());

        btnRow.add_child(copyBtn);
        btnRow.add_child(openLogBtn);
        cardBox.add_child(btnRow);

        responseCardItem.add_child(cardBox);
        this.indicator.menu.addMenuItem(responseCardItem);
        this.indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this.logSection = new PopupMenu.PopupMenuSection();
        this.indicator.menu.addMenuItem(this.logSection);
        this.indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        let entryItem = new PopupMenu.PopupBaseMenuItem({ reactive: false });
        this.entry = new St.Entry({ hint_text: 'Ask Charon (e.g. Slice current file...)', can_focus: true, x_expand: true, style_class: 'charon-prompt-entry', style: 'max-width: 400px;' });
        this.entry.clutter_text.connect('activate', () => {
            let text = this.entry.get_text();
            if (text.trim().length > 0) {
                this.ext.submitTask(text);
                this.entry.set_text('');
                this.indicator.menu.close();
            }
        });
        entryItem.add_child(this.entry);
        this.indicator.menu.addMenuItem(entryItem);
        this.indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        let pingItem = new PopupMenu.PopupMenuItem('🔄 Reconnect WebSocket');
        pingItem.connect('activate', () => this.ext.connectDaemon());
        this.indicator.menu.addMenuItem(pingItem);

        if (shouldShowAvatar) {
            GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                this._toggleAvatar(true);
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    _updateAvatarActionUI(isActive) {
        if (!this.avatarStatusPill) return;

        if (isActive) {
            this.avatarStatusPill.set_text('ON');
            this.avatarStatusPill.style = 'background-color: #3584e4; color: #ffffff; border-radius: 12px; padding: 2px 12px; font-weight: bold; font-size: 0.85em;';
        } else {
            this.avatarStatusPill.set_text('OFF');
            this.avatarStatusPill.style = 'background-color: rgba(255, 255, 255, 0.1); color: #aaaaaa; border-radius: 12px; padding: 2px 10px; font-weight: bold; font-size: 0.85em;';
        }
    }

    _toggleAvatar(enabled) {
        if (enabled) {
            if (this._avatarSubprocess) return;

            let mapWidth = global.stage.width.toString();
            let mapHeight = global.stage.height.toString();

            try {
                let homeDir = GLib.get_home_dir();
                let venvPython = GLib.getenv('CHARON_VENV_PATH') || `${homeDir}/Projects/Tools/Charon/.venv/bin/python`;

                this._avatarSubprocess = new Gio.Subprocess({
                    argv: [
                        venvPython, '-m', 'charon.client.overlay',
                        '--map-width', mapWidth,
                        '--map-height', mapHeight
                    ],
                    flags: Gio.SubprocessFlags.INHERIT_FDS,
                });
                this._avatarSubprocess.init(null);

                this._avatarSubprocess.wait_check_async(null, (proc, res) => {
                    try {
                        proc.wait_check_finish(res);
                    } catch (e) {}
                    this._avatarSubprocess = null;
                    this._updateAvatarActionUI(false);

                    if (!this._isDestroying) {
                        let data = this.ext.readOverlaySettings();
                        data.show_avatar = false;
                        this.ext.writeOverlaySettings(data);
                    }
                });

            } catch (err) {
                console.error(`[Charon] Failed to spawn Avatar overlay: ${err.message}`);
                this._avatarSubprocess = null;
                this._updateAvatarActionUI(false);
            }
        } else {
            if (this._avatarSubprocess) {
                try {
                    this._avatarSubprocess.force_exit();
                } catch (e) {}
                this._avatarSubprocess = null;
            }
        }
    }

    _getAgentIcon(agentName) {
        const CORE_ICONS = {
            'System': '⚙️',
            'Overseer': '👁️',
            'Gatekeeper': '🛡️',
            'Concierge': '👔'
        };
        return CORE_ICONS[agentName] || '🤖';
    }

    updateStatus(text, agentName = 'Concierge') {
        if (!this.statusLabel) return;
        let safeText = text.replace(/[\r\n]+/g, ' ').trim();
        if (safeText.length > 35) safeText = safeText.substring(0, 32) + '...';

        let icon = this._getAgentIcon(agentName);
        let displayName = agentName.replace('The_', '');
        this.statusLabel.set_text(`${icon} ${displayName}: ${safeText}`);
    }

    addLogLine(message) {
        let now = GLib.DateTime.new_now_local();
        let logItem = new PopupMenu.PopupMenuItem(`[${now.format('%H:%M:%S')}] ${message}`, { reactive: false });
        logItem.label.style = 'font-size: 0.75em; font-family: monospace; color: #999; margin-left: 10px; max-width: 380px;';
        logItem.label.clutter_text.line_wrap = true;
        logItem.label.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;

        this.logSection.addMenuItem(logItem, 0);
        this._logQueue.unshift(logItem);
        if (this._logQueue.length > this._logMaxLines) {
            let popped = this._logQueue.pop();
            if (popped) popped.destroy();
        }
    }

    routeWebSocketEvent(payload) {
        const eventType = payload.event_type || payload.type;
        const data = payload.data || {};
        const activeAgent = data.agent_name || payload.agent_name || 'Concierge';

        switch (eventType) {
            case 'desktop_ipc':
                this._handleDesktopIPC(payload.payload, payload.client_id);
                break;

            case 'overseer_report': this._updateOverseerTelemetry(data); break;
            case 'system_alert': this._handleSystemAlert(data); break;
            case 'gatekeeper_request':
            case 'gatekeeper_intercept':
            case 'GatekeeperIntercept':
                this._handleGatekeeperIntercept(data);
                break;
            case 'telemetry_trace': this._handleTelemetryTrace(data); break;
            case 'task_progress':
            case 'task_heartbeat':
            case 'agent_status':
                let progressMsg = data.step || data.status_message || data.message || payload.message || 'Processing...';
                this.updateStatus(progressMsg, activeAgent);
                this.addLogLine(`[${activeAgent}] ${progressMsg}`);
                break;
            case 'task_complete':
            case 'TaskCompleted':
            case 'agent_response':
            case 'concierge_suggestion':
                this.updateStatus('Standby', 'Concierge');
                this.addLogLine('🟢 Sys: Task execution finished.');
                this._handleTaskComplete(data, payload);
                break;
            case 'status_change':
            case 'status':
                let statusText = data.status || payload.message || 'Processing';
                this.updateStatus(statusText, activeAgent);
                break;
        }
    }

    _handleDesktopIPC(ipcPayload, senderId) {
        if (!ipcPayload) return;

        if (ipcPayload.target === 'hud') {
            if (ipcPayload.command === 'show_notification') {
                const title = ipcPayload.title || '👔 Charon IPC';
                const message = ipcPayload.message || 'Empty message received.';
                Main.notify(title, message);
                console.debug(`[Charon UI] Notification displayed. Sent by: ${senderId}`);
            }
            else if (ipcPayload.command === 'toggle_avatar') {
                let isCurrentlyShowing = this.ext.readOverlaySettings().show_avatar === true;
                let newState = !isCurrentlyShowing;

                if (!this._isDestroying) {
                    let data = this.ext.readOverlaySettings();
                    data.show_avatar = newState;
                    this.ext.writeOverlaySettings(data);
                }

                this._updateAvatarActionUI(newState);
                this._toggleAvatar(newState);
            }
            else {
                console.warn(`[Charon UI] Unknown HUD command: ${ipcPayload.command}`);
            }
        }
    }

    _updateOverseerTelemetry(data) {
        const engineOnline = data.engine_online ?? false;
        const engineStatus = engineOnline ? '🟢 Online' : '🔴 Offline';
        const currentTask = (data.current_task && data.current_task !== 'Idle') ? data.current_task : 'Idle';

        if (this.overseerHeader) this.overseerHeader.label.set_text(`⚙️ Overseer: ${engineOnline ? 'Nominal' : 'DEGRADED'}`);
        if (this.overseerDetails) this.overseerDetails.label.set_text(`  Engine: ${engineStatus} | Queue: ${data.queue_depth ?? 0} | ${currentTask}`);

        if (currentTask !== this._lastTaskState) {
            this.addLogLine(currentTask === 'Idle' ? 'Sys: Engine returned to Idle.' : `Exec: ${currentTask}`);
            this._lastTaskState = currentTask;
        }
    }

    _handleTelemetryTrace(traceData) {
        const traceType = traceData.event_type || 'UNKNOWN';
        const agent = traceData.agent_name || 'System';
        if (traceType === 'THINKING') return;

        let logMsg = '';
        switch (traceType) {
            case 'INITIALIZATION': logMsg = `Initializing...`; this.updateStatus(logMsg, agent); break;
            case 'NEGOTIATION': logMsg = `Checking capabilities...`; this.updateStatus(logMsg, agent); break;
            case 'HANDOFF':
                logMsg = `Routing to ${traceData.details?.target_agent || 'Unknown'}`;
                this.updateStatus(`↪️ ${logMsg}`, agent); break;
            case 'EXECUTION':
            case 'EXECUTION_START':
                logMsg = `Executing: ${traceData.action}`; this.updateStatus(logMsg, agent); break;
            case 'FAILED': logMsg = `Step failed!`; this.updateStatus(logMsg, agent); break;
        }
        if (logMsg) this.addLogLine(`[${agent}] ${logMsg}`);
    }

    _handleSystemAlert(alert) {
        this.updateStatus(`⚠️ Alert: ${alert.title || 'System Alert'}`, 'System');
        const source = new MessageTray.Source('Charon Overseer', 'dialog-warning-symbolic');
        Main.messageTray.add(source);
        const notification = new MessageTray.Notification(source, `⚠️ Overseer: ${alert.title}`, alert.message || 'Inspection required.');
        if (alert.severity === 'CRITICAL') notification.setUrgency(MessageTray.Urgency.CRITICAL);
        source.addNotification(notification);
    }

    _handleGatekeeperIntercept(data) {
        this.updateStatus('Approval Needed', 'Gatekeeper');

        const approvalId = data.approval_id || 'unknown_id';
        const actionText = data.intent_summary || data.action || data.manifest || 'Restricted Operation';

        let dialog = new ModalDialog.ModalDialog();

        let title = new St.Label({
            text: '👔 Charon: Management Approval Required',
            style: 'font-weight: bold; font-size: 1.2em; margin-bottom: 12px; color: #e01b24;'
        });

        let description = new St.Label({
            text: `Gatekeeper intercepted a restricted operation:\n\n${actionText}`,
            style: 'margin-bottom: 24px;'
        });
        description.clutter_text.line_wrap = true;

        dialog.contentLayout.add_child(title);
        dialog.contentLayout.add_child(description);

        dialog.setButtons([
            {
                label: 'Rescind',
                action: () => {
                    this.ext.api.respondGatekeeperAsync(approvalId, 'rescind', 'Resolved via GNOME ModalDialog');
                    this.updateStatus('Decision Sent', 'Gatekeeper');
                    dialog.close();
                },
                key: Clutter.KEY_Escape
            },
            {
                label: 'Approve (Proceed)',
                action: () => {
                    this.ext.api.respondGatekeeperAsync(approvalId, 'proceed', 'Resolved via GNOME ModalDialog');
                    this.updateStatus('Decision Sent', 'Gatekeeper');
                    dialog.close();
                }
            }
        ]);

        dialog.open();
    }

    _handleTaskComplete(data, payload) {
        const summary = data.summary || payload.summary || data.response || payload.response || data.text || 'Task executed successfully.';
        this._lastResponseText = summary;
        if (this.responseTextLabel) this.responseTextLabel.set_text(summary);

        const source = new MessageTray.Source('Charon', 'emblem-ok-symbolic');
        Main.messageTray.add(source);
        const notification = new MessageTray.Notification(source, '👔 Charon: Response Received', summary);

        if (data.next_step) {
            notification.addButton('concierge-next-step', 'Execute Next Step');
            notification.connect('action-invoked', () => this.ext.submitTask(data.next_step));
        }
        source.addNotification(notification);
    }

    _handleDroppedUri(fileUri) {
        try {
            let [filePath] = GLib.filename_from_uri(fileUri.trim());
            if (filePath) {
                let actionIntent = 'Analyze this file.';

                if (filePath.endsWith('.stl') || filePath.endsWith('.step')) {
                    actionIntent = 'Slice this 3D model and prepare the printer.';
                } else if (filePath.endsWith('.pdf')) {
                    actionIntent = 'Index this document into project memory.';
                }

                this.ext.submitTask(`${actionIntent}\nTarget file: ${filePath}`);
            }
        } catch (e) {
            console.error(`[Charon] Failed to parse dropped URI: ${e.message}`);
        }
    }

    _copyResponseToClipboard() {
        if (this._lastResponseText) {
            St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, this._lastResponseText);
            Main.notify('👔 Charon', 'Response text copied to clipboard.');
        }
    }

    _openChatLogFile() {
        try {
            let logFilePath = GLib.build_filenamev([GLib.get_user_state_dir(), 'charon', 'logs', 'main.log']);
            let file = Gio.File.new_for_path(logFilePath);
            if (!file.query_exists(null)) logFilePath = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'state', 'charon', 'logs', 'main.log']);
            Gio.AppInfo.launch_default_for_uri(`file://${logFilePath}`, null);
        } catch (e) {
            Main.notify('👔 Charon Error', 'Could not open log file.');
        }
    }

    destroy() {
        this._isDestroying = true;
        this._toggleAvatar(false);

        if (this.indicator) {
            this.indicator._delegate = null;
            this.indicator.destroy();
            this.indicator = null;
        }
        this._logQueue.forEach(item => { if (item && typeof item.destroy === 'function') item.destroy(); });
        this._logQueue = [];
    }
}