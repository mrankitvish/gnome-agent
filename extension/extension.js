/**
 * extension.js — Main entry point for the Gnome Agent GNOME Shell extension.
 *
 * Responsibilities:
 *  - Load settings (base URL, API key) via Gio.Settings
 *  - Create the GnomeAgentAPI client
 *  - Create and register the panel indicator
 *  - Capture desktop context (active window, focused app, clipboard)
 *  - Clean up on disable()
 */

import { Extension, gettext as _ } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import Shell from 'gi://Shell';
import Meta from 'gi://Meta';
import St from 'gi://St';

import { GnomeAgentAPI } from './api.js';
import { GnomeAgentIndicator } from './panel.js';

export default class GnomeAgentExtension extends Extension {
    enable() {
        this._settings = this.getSettings();

        // Build API client from settings
        this._refreshClient();

        // Re-create client if settings change
        this._settingsChangedId = this._settings.connect('changed', () => {
            this._refreshClient();
            if (this._indicator) this._indicator._api = this._api;
        });

        // Register panel indicator
        this._indicator = new GnomeAgentIndicator(
            this._api,
            () => this._captureContext(),
            this._settings,
            this.path
        );
        Main.panel.addToStatusArea('gnome-agent', this._indicator);

        // Register Global Hotkey
        Main.wm.addKeybinding(
            'global-shortcut',
            this._settings,
            Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
            () => {
                this._indicator._togglePopup();
            }
        );
    }

    disable() {
        Main.wm.removeKeybinding('global-shortcut');
        this._settings?.disconnect(this._settingsChangedId);
        this._settingsChangedId = null;
        this._indicator?.destroy();
        this._indicator = null;
        this._api?.destroy();
        this._api = null;
        this._settings = null;
    }

    // ── Internal helpers ──────────────────────────────────────────────────────

    _refreshClient() {
        this._api?.destroy();
        this._api = new GnomeAgentAPI({
            baseUrl: this._settings.get_string('server-url'),
            apiKey: this._settings.get_string('api-key'),
        });
    }

    /**
     * Capture current GNOME desktop context to inject into chat requests.
     * @returns {{ active_app?: string, current_path?: string, clipboard?: string }}
     */
    _captureContext() {
        const ctx = {};

        // Active application name + window title
        try {
            const focusedWindow = global.display.get_focus_window();
            if (focusedWindow) {
                ctx.active_app = focusedWindow.get_wm_class() || focusedWindow.get_title();
                const title = focusedWindow.get_title();
                if (title && title !== ctx.active_app) {
                    ctx.window_title = title;
                }
            }
        } catch (_) { }

        // Current working directory from the tracker (best-effort)
        try {
            const tracker = Shell.WindowTracker.get_default();
            const app = tracker.focus_app;
            if (app) ctx.active_app = app.get_name();
        } catch (_) { }

        // Clipboard text (synchronous peek — may be empty if clipboard is empty)
        try {
            const clipboard = St.Clipboard.get_default();
            clipboard.get_text(St.ClipboardType.CLIPBOARD, (_, text) => {
                if (text) this._clipboardCache = text;
            });
            if (this._clipboardCache) ctx.clipboard = this._clipboardCache;
        } catch (_) { }

        return ctx;
    }
}
