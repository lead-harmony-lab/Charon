import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import St from 'gi://St';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import { CharonAPI } from './api.js';
import { CharonSearchProvider } from './searchProvider.js';
import { CharonUI } from './ui.js';

const DEFAULT_CHARON_API_URL = 'http://127.0.0.1:8000';
const DEFAULT_CHARON_API_KEY = 'charon-secret-key-change-me';
const DEFAULT_API_KEY_HEADER = 'X-API-Key';
const TELEMETRY_INTERVAL_MS = 33;
const SAVE_DEBOUNCE_MS = 500;

export default class CharonExtension extends Extension {
    enable() {
        this.settings = this._loadSettingsSafely();
        this.overlaySettingsFile = this._getOverlaySettingsFile();
        this.api = new CharonAPI(this._getApiUrl(), this._getApiKey(), this._getApiKeyHeader());

        this._lastSavedX = null;
        this._lastSavedY = null;
        this._trackedOverlayWindow = null;
        this._aboveSignalId = 0;
        this._positionSignalId = 0;
        this._savePositionDebounceId = 0;
        this._windowCreatedId = 0;
        this._gracePeriodTimeoutId = 0;

        this.ui = new CharonUI(this);
        Main.panel.addToStatusArea(this.uuid, this.ui.indicator);

        this.searchProvider = new CharonSearchProvider(this);
        if (Main.overview.searchController && Main.overview.searchController.addProvider) {
            Main.overview.searchController.addProvider(this.searchProvider);
        } else if (Main.overview.addSearchProvider) {
            Main.overview.addSearchProvider(this.searchProvider);
        }

        this._windowCreatedId = global.display.connect('window-created', (display, win) => {
            if (this._isOverlayWindow(win)) {
                try { win.skip_taskbar = true; win.skip_pager = true; } catch (e) {}
                this._attachOverlayWindowHooks(win);
            }
        });

        for (let actor of global.get_window_actors()) {
            let metaWin = actor.get_meta_window();
            if (metaWin && this._isOverlayWindow(metaWin)) {
                try { metaWin.skip_taskbar = true; metaWin.skip_pager = true; } catch (e) {}
                this._attachOverlayWindowHooks(metaWin);
            }
        }

        this._registerShortcuts();
        this.connectDaemon();
        this._startMouseTelemetry();
    }

    _loadSettingsSafely() {
        try {
            return this.getSettings();
        } catch (e) {
            try {
                const schemaDir = this.dir.get_child('schemas');
                let schemaSource = schemaDir.query_exists(null)
                    ? Gio.SettingsSchemaSource.new_from_directory(schemaDir.get_path(), Gio.SettingsSchemaSource.get_default(), false)
                    : Gio.SettingsSchemaSource.get_default();

                const schemaObj = schemaSource.lookup('org.gnome.shell.extensions.charon', true);
                return new Gio.Settings({ settings_schema: schemaObj });
            } catch (fallbackErr) {
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
            let file = clientDir.get_child('settings.json');
            return file;
        } catch (e) {
            let fallbackFile = this.dir.get_child('settings.json');
            return fallbackFile;
        }
    }

    readOverlaySettings() {
        if (!this.overlaySettingsFile) {
            return {};
        }
        if (!this.overlaySettingsFile.query_exists(null)) {
            return {};
        }

        try {
            let [success, contents] = this.overlaySettingsFile.load_contents(null);
            if (success) {
                let decoder = new TextDecoder('utf-8');
                let str = decoder.decode(contents).trim();
                let parsed = str ? JSON.parse(str) : {};
                return parsed;
            }
        } catch (e) {}
        return {};
    }

    writeOverlaySettings(data) {
        if (!this.overlaySettingsFile) return;
        try {
            let jsonString = JSON.stringify(data, null, 2);
            let encoder = new TextEncoder();
            let bytes = new GLib.Bytes(encoder.encode(jsonString));

            this.overlaySettingsFile.replace_contents_bytes_async(
                bytes, null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null,
                (file, res) => { try { file.replace_contents_finish(res); } catch (e) {} }
            );
        } catch (e) {}
    }

    _getApiUrl() { return this.settings ? (this.settings.get_string('api-url') || DEFAULT_CHARON_API_URL) : DEFAULT_CHARON_API_URL; }
    _getApiKey() { return this.settings ? (this.settings.get_string('api-key') || DEFAULT_CHARON_API_KEY) : DEFAULT_CHARON_API_KEY; }
    _getApiKeyHeader() { return this.settings ? (this.settings.get_string('api-key-header') || DEFAULT_API_KEY_HEADER) : DEFAULT_API_KEY_HEADER; }

    submitTask(taskText, targetAgentOverride = null) {
        this.ui.updateStatus('Transmitting...', 'System');
        let activeWindow = global.display.get_focus_window();
        let [x, y] = global.get_pointer();

        let contextObj = {
            origin: 'gnome_shell_panel',
            cursor: { x: Math.round(x), y: Math.round(y) }
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
                    this._handleIncomingWsEvent(payload);

                    if (this.ui && typeof this.ui.routeWebSocketEvent === 'function') {
                        this.ui.routeWebSocketEvent(payload);
                    }
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

    _handleIncomingWsEvent(eventData) {
        if (!eventData || typeof eventData !== 'object') return;

        const eventType = eventData.type || eventData.event_type;
        const payload = eventData.payload || eventData.data || {};

        if (eventType === 'window_moved') {
            const { x, y } = payload;
            if (typeof x === 'number' && typeof y === 'number') {
                this._moveOverlayWindow(Math.round(x), Math.round(y));
            }
        }
    }

    _moveOverlayWindow(x, y) {
        let targetWin = this._trackedOverlayWindow;

        if (!targetWin) {
            for (let actor of global.get_window_actors()) {
                let metaWin = actor.get_meta_window();
                if (metaWin && this._isOverlayWindow(metaWin)) {
                    targetWin = metaWin;
                    this._attachOverlayWindowHooks(metaWin);
                    break;
                }
            }
        }

        if (targetWin) {
            this._lastSavedX = x;
            this._lastSavedY = y;

            if (typeof targetWin.move_frame === 'function') {
                targetWin.move_frame(true, x, y);
            } else if (typeof targetWin.move_to_coordinate === 'function') {
                targetWin.move_to_coordinate(x, y);
            }

            let settingsData = this.readOverlaySettings();
            settingsData.x = x;
            settingsData.y = y;
            this.writeOverlaySettings(settingsData);
        }
    }

    _isOverlayWindow(metaWin) {
        if (!metaWin) return false;
        let wmClass = (metaWin.get_wm_class() || '').toLowerCase();
        let title = (metaWin.get_title() || '').toLowerCase();
        return title === 'charon concierge overlay' || wmClass === 'com.charon.concierge.overlay';
    }

    _attachOverlayWindowHooks(metaWin) {
        if (this._trackedOverlayWindow === metaWin) return;

        this._unhookOverlayWindow();
        this._trackedOverlayWindow = metaWin;

        let currentSettings = this.readOverlaySettings();
        let isCurrentlyAbove = metaWin.is_above ? metaWin.is_above() : metaWin.above;

        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
            if (this._trackedOverlayWindow !== metaWin) return GLib.SOURCE_REMOVE;

            if (currentSettings.always_on_top !== undefined) {
                if (currentSettings.always_on_top && !isCurrentlyAbove) metaWin.make_above();
                else if (!currentSettings.always_on_top && isCurrentlyAbove) metaWin.unmake_above();
            } else {
                currentSettings.always_on_top = isCurrentlyAbove;
                this.writeOverlaySettings(currentSettings);
            }

            if (typeof currentSettings.x === 'number' && typeof currentSettings.y === 'number') {
                let restoredX = Math.round(currentSettings.x);
                let restoredY = Math.round(currentSettings.y);

                this._lastSavedX = restoredX;
                this._lastSavedY = restoredY;

                if (typeof metaWin.move_frame === 'function') {
                    metaWin.move_frame(true, restoredX, restoredY);
                } else if (typeof metaWin.move_to_coordinate === 'function') {
                    metaWin.move_to_coordinate(restoredX, restoredY);
                }
            }

            return GLib.SOURCE_REMOVE;
        });

        this._aboveSignalId = metaWin.connect('notify::above', (win) => {
            let isAbove = win.is_above ? win.is_above() : win.above;
            let settingsData = this.readOverlaySettings();
            if (settingsData.always_on_top !== isAbove) {
                settingsData.always_on_top = isAbove;
                this.writeOverlaySettings(settingsData);
            }
        });

        this._ignorePositionSaves = true;
        if (this._gracePeriodTimeoutId) {
            GLib.source_remove(this._gracePeriodTimeoutId);
        }
        this._gracePeriodTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1500, () => {
            this._ignorePositionSaves = false;
            this._gracePeriodTimeoutId = 0;
            return GLib.SOURCE_REMOVE;
        });

        this._positionSignalId = metaWin.connect('position-changed', (win) => {
            if (!this._ignorePositionSaves) {
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

            if (this.api && typeof this.api.sendTelemetry === 'function') {
                this.api.sendTelemetry({
                    type: 'window_moved',
                    data: { x: currX, y: currY }
                });
            }

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
        if (this._gracePeriodTimeoutId) {
            GLib.source_remove(this._gracePeriodTimeoutId);
            this._gracePeriodTimeoutId = 0;
        }
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
        this._telemetryTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, TELEMETRY_INTERVAL_MS, () => {
            let [x, y] = global.get_pointer();
            x = Math.round(x); y = Math.round(y);
            let cursorMoved = (x !== this._latestCursor.x || y !== this._latestCursor.y);
            if (cursorMoved) this._latestCursor = { x: x, y: y };

            let wheatleyCenter = null;
            let windowPosition = null;

            for (let actor of global.get_window_actors()) {
                let metaWin = actor.get_meta_window();
                if (metaWin && this._isOverlayWindow(metaWin)) {
                    this._attachOverlayWindowHooks(metaWin);
                    let rect = metaWin.get_frame_rect();
                    windowPosition = { x: Math.round(rect.x), y: Math.round(rect.y) };
                    wheatleyCenter = { x: Math.round(rect.x + (rect.width / 2)), y: Math.round(rect.y + (rect.height / 2)) };
                    break;
                }
            }

            if (cursorMoved) {
                let payload = { event_type: 'pointer_telemetry', client_id: 'gnome_shell_extension', data: { action: 'motion', cursor: this._latestCursor } };
                if (wheatleyCenter) payload.data.window_center = wheatleyCenter;
                if (windowPosition) payload.data.window_position = windowPosition;
                if (this.api && typeof this.api.sendTelemetry === 'function') this.api.sendTelemetry(payload);
            }
            return GLib.SOURCE_CONTINUE;
        });
    }

    _stopMouseTelemetry() {
        if (this._telemetryTimerId) { GLib.source_remove(this._telemetryTimerId); this._telemetryTimerId = 0; }
        this._latestCursor = null;
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
                if (this.ui && this.ui.avatarSwitch) this.ui.avatarSwitch.toggle();
            });
        } catch (e) {}
    }

    _unregisterShortcuts() {
        try {
            Main.wm.removeKeybinding('toggle-shortcut');
            Main.wm.removeKeybinding('save-to-charon-shortcut');
            Main.wm.removeKeybinding('toggle-avatar-shortcut');
        } catch (e) {}
    }

    disable() {
        if (this._windowCreatedId) { global.display.disconnect(this._windowCreatedId); this._windowCreatedId = 0; }
        this._unregisterShortcuts();
        this._stopMouseTelemetry();
        this._unhookOverlayWindow();
        if (this._reconnectTimeout) { GLib.source_remove(this._reconnectTimeout); this._reconnectTimeout = null; }
        if (this.searchProvider) {
            if (Main.overview.searchController && Main.overview.searchController.removeProvider) Main.overview.searchController.removeProvider(this.searchProvider);
            else if (Main.overview.removeSearchProvider) Main.overview.removeSearchProvider(this.searchProvider);
            this.searchProvider = null;
        }
        if (this.api) { this.api.abort(); this.api = null; }
        if (this.ui) { this.ui.destroy(); this.ui = null; }
        this.overlaySettingsFile = null;
        this.settings = null;
    }
}