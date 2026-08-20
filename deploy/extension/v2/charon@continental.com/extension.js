import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import St from 'gi://St';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import Clutter from 'gi://Clutter';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import { CharonAPI } from './api.js';
import { CharonSearchProvider } from './searchProvider.js';
import { CharonUI } from './ui.js';

const DEFAULT_CHARON_API_URL = 'http://127.0.0.1:8000';
const DEFAULT_CHARON_API_KEY = 'charon-secret-key-change-me';
const DEFAULT_API_KEY_HEADER = 'X-API-Key';
const TELEMETRY_INTERVAL_MS = 33; // ~30Hz sampling rate
const SAVE_DEBOUNCE_MS = 500; // Delay disk write until dragging stops

export default class CharonExtension extends Extension {
    enable() {
        // 1. Settings, JSON File Handle & API Init
        this.settings = this._loadSettingsSafely();
        this.overlaySettingsFile = this._getOverlaySettingsFile();
        this.api = new CharonAPI(this._getApiUrl(), this._getApiKey(), this._getApiKeyHeader());

        this._lastSavedX = null;
        this._lastSavedY = null;
        this._trackedOverlayWindow = null;
        this._aboveSignalId = 0;
        this._positionSignalId = 0;
        this._savePositionDebounceId = 0;
        this._isProgrammaticMove = false;

        // 2. View Initialization
        this.ui = new CharonUI(this);
        Main.panel.addToStatusArea(this.uuid, this.ui.indicator);

        // 3. Search Provider
        this.searchProvider = new CharonSearchProvider(this);
        if (Main.overview.searchController && Main.overview.searchController.addProvider) {
            Main.overview.searchController.addProvider(this.searchProvider);
        } else if (Main.overview.addSearchProvider) {
            Main.overview.addSearchProvider(this.searchProvider);
        }

        // 4. System Hooks
        this._registerShortcuts();
        this.connectDaemon();

        // 5. Start Telemetry
        this._startMouseTelemetry();
    }

    _loadSettingsSafely() {
        try {
            return this.getSettings();
        } catch (e) {
            console.warn(`[Charon] Native getSettings() failed, attempting local schema lookup...`);
            try {
                const schemaDir = this.dir.get_child('schemas');
                let schemaSource = schemaDir.query_exists(null)
                    ? Gio.SettingsSchemaSource.new_from_directory(schemaDir.get_path(), Gio.SettingsSchemaSource.get_default(), false)
                    : Gio.SettingsSchemaSource.get_default();

                const schemaObj = schemaSource.lookup('org.gnome.shell.extensions.charon', true);
                return new Gio.Settings({ settings_schema: schemaObj });
            } catch (fallbackErr) {
                console.error(`[Charon] Failed to load schema: ${fallbackErr.message}`);
                return null;
            }
        }
    }

    _getOverlaySettingsFile() {
        try {
            let clientDir = this.dir.get_child('charon').get_child('client');
            if (!clientDir.query_exists(null)) {
                clientDir.make_directory_with_parents(null);
            }
            return clientDir.get_child('settings.json');
        } catch (e) {
            console.error(`[Charon] Failed to locate settings.json: ${e.message}`);
            return this.dir.get_child('settings.json');
        }
    }

    readOverlaySettings() {
        if (!this.overlaySettingsFile || !this.overlaySettingsFile.query_exists(null)) {
            return {};
        }
        try {
            let [success, contents] = this.overlaySettingsFile.load_contents(null);
            if (success) {
                let decoder = new TextDecoder('utf-8');
                let str = decoder.decode(contents).trim();
                return str ? JSON.parse(str) : {};
            }
        } catch (e) {
            console.error(`[Charon] Error reading overlay settings.json: ${e.message}`);
        }
        return {};
    }

    writeOverlaySettings(data) {
        if (!this.overlaySettingsFile) return;
        try {
            let jsonString = JSON.stringify(data, null, 2);
            let encoder = new TextEncoder();
            let bytes = new GLib.Bytes(encoder.encode(jsonString));

            this.overlaySettingsFile.replace_contents_bytes_async(
                bytes,
                null,
                false,
                Gio.FileCreateFlags.REPLACE_DESTINATION,
                null,
                (file, res) => {
                    try {
                        file.replace_contents_finish(res);
                    } catch (e) {
                        console.error(`[Charon] Async write failed to complete: ${e.message}`);
                    }
                }
            );
        } catch (e) {
            console.error(`[Charon] Error initiating overlay settings write: ${e.message}`);
        }
    }

    _getApiUrl() { return this.settings ? (this.settings.get_string('api-url') || DEFAULT_CHARON_API_URL) : DEFAULT_CHARON_API_URL; }
    _getApiKey() { return this.settings ? (this.settings.get_string('api-key') || DEFAULT_CHARON_API_KEY) : DEFAULT_CHARON_API_KEY; }
    _getApiKeyHeader() { return this.settings ? (this.settings.get_string('api-key-header') || DEFAULT_API_KEY_HEADER) : DEFAULT_API_KEY_HEADER; }

    submitTask(taskText, targetAgentOverride = null) {
        this.ui.updateStatus('Transmitting...', 'System');

        let activeWindow = global.display.get_focus_window();
        let [x, y, mods] = global.get_pointer();

        let contextObj = {
            origin: 'gnome_shell_panel',
            cursor: {
                x: Math.round(x),
                y: Math.round(y)
            }
        };

        let windowContext = '';

        if (activeWindow) {
            let wmClass = activeWindow.get_wm_class() || 'unknown';
            let title = activeWindow.get_title() || 'unknown';
            contextObj.focused_app = wmClass;
            windowContext = `\n\n[Context: User focus is on app '${wmClass}', window: '${title}']`;
        }

        let finalPrompt = taskText + windowContext;

        this.api.submitTaskAsync(finalPrompt, targetAgentOverride, contextObj)
            .then(() => this.ui.updateStatus('Queued', 'System'))
            .catch(err => {
                this.ui.updateStatus('Unreachable', 'System');
                Main.notify('👔 Charon Error', err.message);
            });
    }

    connectDaemon(retryCount = 0) {
        if (!this.api) return;

        this.ui.updateStatus('Connecting...', 'System');

        this.api.connectWebSocket(
            (payload) => {
                GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                    this._retryCount = 0;
                    this.ui.routeWebSocketEvent(payload);
                    return GLib.SOURCE_REMOVE;
                });
            },
            (err) => {
                GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                    this.ui.updateStatus('Offline', 'System');
                    if (this.ui.overseerHeader) this.ui.overseerHeader.label.set_text('⚙️ Overseer: Disconnected');

                    this._retryCount = retryCount;
                    let backoffMs = Math.min(15000, 2000 * Math.pow(1.5, this._retryCount));
                    this._retryCount++;

                    if (this._reconnectTimeout) GLib.source_remove(this._reconnectTimeout);
                    this._reconnectTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, backoffMs, () => {
                        this.connectDaemon(this._retryCount);
                        this._reconnectTimeout = null;
                        return GLib.SOURCE_REMOVE;
                    });
                    return GLib.SOURCE_REMOVE;
                });
            }
        );
    }

    _isOverlayWindow(metaWin) {
        if (!metaWin) return false;
        let wmClass = (metaWin.get_wm_class() || '').toLowerCase();
        let title = (metaWin.get_title() || '').toLowerCase();
        let sandboxId = (metaWin.get_sandboxed_app_id ? (metaWin.get_sandboxed_app_id() || '') : '').toLowerCase();

        return (
            title === 'charon concierge overlay' ||
            wmClass === 'com.charon.concierge.overlay' ||
            sandboxId.includes('charon')
        );
    }

    _attachOverlayWindowHooks(metaWin) {
        if (this._trackedOverlayWindow === metaWin) return;

        this._unhookOverlayWindow();
        this._trackedOverlayWindow = metaWin;
        this._isProgrammaticMove = true;

        let currentSettings = this.readOverlaySettings();
        let actor = metaWin.get_compositor_private();

        if (actor && typeof currentSettings.x === 'number' && typeof currentSettings.y === 'number') {
            let firstFrameId = actor.connect('first-frame', () => {
                actor.disconnect(firstFrameId);

                if (this._trackedOverlayWindow === metaWin) {
                    metaWin.move_frame(true, currentSettings.x, currentSettings.y);
                    this._lastSavedX = currentSettings.x;
                    this._lastSavedY = currentSettings.y;

                    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250, () => {
                        this._isProgrammaticMove = false;
                        return GLib.SOURCE_REMOVE;
                    });
                }
            });
        } else {
            this._isProgrammaticMove = false;
        }

        let isCurrentlyAbove = metaWin.is_above ? metaWin.is_above() : metaWin.above;
        if (currentSettings.always_on_top !== undefined) {
            if (currentSettings.always_on_top && !isCurrentlyAbove) {
                metaWin.make_above();
            } else if (!currentSettings.always_on_top && isCurrentlyAbove) {
                metaWin.unmake_above();
            }
        } else {
            currentSettings.always_on_top = isCurrentlyAbove;
            this.writeOverlaySettings(currentSettings);
        }

        this._aboveSignalId = metaWin.connect('notify::above', (win) => {
            let isAbove = win.is_above ? win.is_above() : win.above;
            let settingsData = this.readOverlaySettings();
            if (settingsData.always_on_top !== isAbove) {
                settingsData.always_on_top = isAbove;
                this.writeOverlaySettings(settingsData);
            }
        });

        this._positionSignalId = metaWin.connect('position-changed', (win) => {
            if (!this._isProgrammaticMove) {
                this._syncOverlayPosition(win);
            }
        });
    }

    _syncOverlayPosition(metaWin) {
        let rect = metaWin.get_frame_rect();
        let currX = Math.round(rect.x);
        let currY = Math.round(rect.y);

        if (this._lastSavedX !== currX || this._lastSavedY !== currY) {
            this._lastSavedX = currX;
            this._lastSavedY = currY;

            if (this._savePositionDebounceId) {
                GLib.source_remove(this._savePositionDebounceId);
                this._savePositionDebounceId = 0;
            }

            this._savePositionDebounceId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, SAVE_DEBOUNCE_MS, () => {
                let currentData = this.readOverlaySettings();
                currentData.x = currX;
                currentData.y = currY;
                this.writeOverlaySettings(currentData);

                this._savePositionDebounceId = 0;
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    _unhookOverlayWindow() {
        if (this._savePositionDebounceId) {
            GLib.source_remove(this._savePositionDebounceId);
            this._savePositionDebounceId = 0;
        }

        if (this._trackedOverlayWindow) {
            if (this._aboveSignalId) {
                try { this._trackedOverlayWindow.disconnect(this._aboveSignalId); } catch (e) {}
                this._aboveSignalId = 0;
            }
            if (this._positionSignalId) {
                try { this._trackedOverlayWindow.disconnect(this._positionSignalId); } catch (e) {}
                this._positionSignalId = 0;
            }
            this._trackedOverlayWindow = null;
        }
    }

    _startMouseTelemetry() {
        this._latestCursor = { x: -1, y: -1 };
        this._telemetryTimerId = 0;

        this._telemetryTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, TELEMETRY_INTERVAL_MS, () => {
            let [x, y, mods] = global.get_pointer();
            x = Math.round(x);
            y = Math.round(y);

            let cursorMoved = (x !== this._latestCursor.x || y !== this._latestCursor.y);
            if (cursorMoved) {
                this._latestCursor = { x: x, y: y };
            }

            let wheatleyCenter = null;
            let windowPosition = null;

            for (let actor of global.get_window_actors()) {
                let metaWin = actor.get_meta_window();
                if (metaWin && this._isOverlayWindow(metaWin)) {
                    this._attachOverlayWindowHooks(metaWin);

                    let rect = metaWin.get_frame_rect();
                    windowPosition = { x: Math.round(rect.x), y: Math.round(rect.y) };
                    wheatleyCenter = {
                        x: Math.round(rect.x + (rect.width / 2)),
                        y: Math.round(rect.y + (rect.height / 2))
                    };
                    break;
                }
            }

            if (cursorMoved) {
                this._sendTelemetryPayload('motion', this._latestCursor, wheatleyCenter, windowPosition);
            }

            return GLib.SOURCE_CONTINUE;
        });
    }

    _stopMouseTelemetry() {
        if (this._telemetryTimerId) {
            GLib.source_remove(this._telemetryTimerId);
            this._telemetryTimerId = 0;
        }
        this._latestCursor = null;
    }

    _sendTelemetryPayload(action, cursorCoords, windowCenter = null, windowPosition = null) {
        let payload = {
            event_type: 'pointer_telemetry',
            client_id: 'gnome_shell_extension',
            data: {
                action: action,
                cursor: cursorCoords
            }
        };

        if (windowCenter) payload.data.window_center = windowCenter;
        if (windowPosition) payload.data.window_position = windowPosition;

        if (this.api && typeof this.api.sendTelemetry === 'function') {
            this.api.sendTelemetry(payload);
        }
    }

    _registerShortcuts() {
        if (!this.settings) return;
        this._unregisterShortcuts();

        try {
            Main.wm.addKeybinding('toggle-shortcut', this.settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT, Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW | Shell.ActionMode.POPUP, () => {
                if (this.ui.indicator && this.ui.indicator.menu) {
                    this.ui.indicator.menu.toggle();
                    if (this.ui.indicator.menu.isOpen && this.ui.entry) {
                        GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                            if (this.ui.entry.clutter_text) this.ui.entry.clutter_text.grab_key_focus();
                            return GLib.SOURCE_REMOVE;
                        });
                    }
                }
            });

            Main.wm.addKeybinding('save-to-charon-shortcut', this.settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT, Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW, () => {
                St.Clipboard.get_default().get_text(St.ClipboardType.CLIPBOARD, (clip, text) => {
                    if (text) {
                        this.submitTask(`Save this text to project memory:\n\n${text}`, 'The_Archivist');
                        Main.notify('👔 Charon', 'Clipboard passed to Archivist.');
                    }
                });
            });

            Main.wm.addKeybinding('toggle-avatar-shortcut', this.settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT, Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW, () => {
                if (this.ui && this.ui.avatarSwitch) {
                    this.ui.avatarSwitch.toggle();
                }
            });
        } catch (e) {
            console.error(`[Charon] Keybinding error: ${e.message}`);
        }
    }

    _unregisterShortcuts() {
        try {
            Main.wm.removeKeybinding('toggle-shortcut');
            Main.wm.removeKeybinding('save-to-charon-shortcut');
            Main.wm.removeKeybinding('toggle-avatar-shortcut');
        } catch (e) {}
    }

    disable() {
        this._unregisterShortcuts();
        this._stopMouseTelemetry();
        this._unhookOverlayWindow();

        if (this._reconnectTimeout) {
            GLib.source_remove(this._reconnectTimeout);
            this._reconnectTimeout = null;
        }

        if (this.searchProvider) {
            if (Main.overview.searchController && Main.overview.searchController.removeProvider) {
                Main.overview.searchController.removeProvider(this.searchProvider);
            } else if (Main.overview.removeSearchProvider) {
                Main.overview.removeSearchProvider(this.searchProvider);
            }
            this.searchProvider = null;
        }

        if (this.api) {
            this.api.abort();
            this.api = null;
        }

        if (this.ui) {
            this.ui.destroy();
            this.ui = null;
        }

        this.overlaySettingsFile = null;
        this.settings = null;
    }
}