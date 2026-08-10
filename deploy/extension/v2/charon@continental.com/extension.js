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

export default class CharonExtension extends Extension {
    enable() {
        // 1. Settings & API Init
        this.settings = this._loadSettingsSafely();
        this.api = new CharonAPI(this._getApiUrl(), this._getApiKey(), this._getApiKeyHeader());

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

    _getApiUrl() { return this.settings ? (this.settings.get_string('api-url') || DEFAULT_CHARON_API_URL) : DEFAULT_CHARON_API_URL; }
    _getApiKey() { return this.settings ? (this.settings.get_string('api-key') || DEFAULT_CHARON_API_KEY) : DEFAULT_CHARON_API_KEY; }
    _getApiKeyHeader() { return this.settings ? (this.settings.get_string('api-key-header') || DEFAULT_API_KEY_HEADER) : DEFAULT_API_KEY_HEADER; }

    submitTask(taskText, targetAgentOverride = null) {
        this.ui.updateStatus('Transmitting...', 'System');

        let activeWindow = global.display.get_focus_window();
        let contextObj = { origin: 'gnome_shell_panel' };
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

    _registerShortcuts() {
        if (!this.settings) return;
        this._unregisterShortcuts(); // Clear stale grabs

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
        } catch (e) {
            console.error(`[Charon] Keybinding error: ${e.message}`);
        }
    }

    _unregisterShortcuts() {
        try {
            Main.wm.removeKeybinding('toggle-shortcut');
            Main.wm.removeKeybinding('save-to-charon-shortcut');
        } catch (e) {}
    }

    disable() {
        this._unregisterShortcuts();

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

        this.settings = null;
    }
}