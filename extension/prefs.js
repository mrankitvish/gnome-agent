/**
 * prefs.js — GNOME Shell extension preferences UI.
 *
 * Shown in: GNOME Extensions app → Gnome Agent → Settings.
 * Uses Adw (libadwaita) widgets available in GNOME 45+.
 */

import Adw from 'gi://Adw';
import Gtk from 'gi://Gtk';
import { ExtensionPreferences, gettext as _ } from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class GnomeAgentPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();

        // ── Connection page ───────────────────────────────────────────────────
        const page = new Adw.PreferencesPage({
            title: _('Connection'),
            icon_name: 'network-server-symbolic',
        });

        const group = new Adw.PreferencesGroup({
            title: _('Gnome Agent Runtime'),
            description: _('Configure how the extension connects to the local AI backend.'),
        });

        // Server URL row
        const urlRow = new Adw.EntryRow({ title: _('Server URL') });
        settings.bind('server-url', urlRow, 'text', 0 /* DEFAULT */);
        group.add(urlRow);

        // API key row
        const keyRow = new Adw.PasswordEntryRow({ title: _('API Key (optional)') });
        settings.bind('api-key', keyRow, 'text', 0);
        group.add(keyRow);

        // Agent ID row
        const agentRow = new Adw.EntryRow({ title: _('Default Agent ID') });
        settings.bind('agent-id', agentRow, 'text', 0);
        group.add(agentRow);

        page.add(group);

        // ── Context page ──────────────────────────────────────────────────────
        const ctxPage = new Adw.PreferencesPage({
            title: _('Context'),
            icon_name: 'preferences-system-symbolic',
        });

        const ctxGroup = new Adw.PreferencesGroup({
            title: _('Desktop Context Injection'),
            description: _('Choose what desktop context is automatically sent with each message.'),
        });

        const ctxOptions = [
            ['inject-active-app', _('Active application name')],
            ['inject-window-title', _('Window title')],
            ['inject-clipboard', _('Clipboard content')],
        ];

        for (const [key, label] of ctxOptions) {
            const row = new Adw.SwitchRow({ title: label });
            settings.bind(key, row, 'active', 0);
            ctxGroup.add(row);
        }

        ctxPage.add(ctxGroup);

        window.add(page);
        window.add(ctxPage);
    }
}
