/**
 * prefs.js — Full management UI for Gnome Agent.
 *
 * Pages:
 *   1. Status     — health check, runtime info, connect/disconnect
 *   2. Agents     — list agents, switch active, create, delete, edit model
 *   3. MCP Servers — list servers, add external, remove
 *   4. Tools      — searchable read-only tool browser
 *   5. Connection — server URL, API key, context toggles
 */

import Adw from 'gi://Adw';
import Gtk from 'gi://Gtk';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import Soup from 'gi://Soup?version=3.0';
import GObject from 'gi://GObject';
import {
    ExtensionPreferences,
    gettext as _,
} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

// ── HTTP helper ───────────────────────────────────────────────────────────────

function buildSession() {
    const s = new Soup.Session();
    s.timeout = 5;
    return s;
}

function fetchJson(url, apiKey = '', method = 'GET', body = null) {
    const session = buildSession();
    let uri;
    try { uri = GLib.Uri.parse(url, GLib.UriFlags.NONE); }
    catch { return null; }

    const msg = new Soup.Message({ method, uri });
    if (apiKey) msg.request_headers.append('Authorization', `Bearer ${apiKey}`);
    if (body) {
        const encoded = new TextEncoder().encode(JSON.stringify(body));
        msg.set_request_body_from_bytes('application/json', new GLib.Bytes(encoded));
    }

    try {
        const bytes = session.send_and_read(msg, null);
        const text = new TextDecoder().decode(bytes.get_data());
        return JSON.parse(text);
    } catch {
        return null;
    }
}

// ── Status badge ──────────────────────────────────────────────────────────────

function statusBadge(ok) {
    const label = new Gtk.Label({
        label: ok ? '● Online' : '● Offline',
        css_classes: ok ? ['success'] : ['error'],
    });
    return label;
}

// ── Base page helper ──────────────────────────────────────────────────────────

function scrollPage(child) {
    const scroll = new Gtk.ScrolledWindow({
        hscrollbar_policy: Gtk.PolicyType.NEVER,
        vscrollbar_policy: Gtk.PolicyType.AUTOMATIC,
        vexpand: true,
    });
    scroll.set_child(child);
    return scroll;
}

// ═════════════════════════════════════════════════════════════════════════════

export default class GnomeAgentPreferences extends ExtensionPreferences {

    fillPreferencesWindow(window) {
        this._settings = this.getSettings();
        this._window = window;
        window.set_default_size(700, 600);
        window.set_title(_('Gnome Agent'));

        window.add(this._buildStatusPage());
        window.add(this._buildLlmConfigPage());
        window.add(this._buildMcpPage());
        window.add(this._buildToolsPage());
        window.add(this._buildConnectionPage());
        window.add(this._buildAppearancePage());
    }

    get _baseUrl() { return this._settings.get_string('server-url'); }
    get _apiKey() { return this._settings.get_string('api-key'); }
    _fetch(path, method = 'GET', body = null) {
        return fetchJson(`${this._baseUrl}${path}`, this._apiKey, method, body);
    }

    // ── 1. STATUS ─────────────────────────────────────────────────────────────

    _buildStatusPage() {
        const page = new Adw.PreferencesPage({
            title: _('Status'),
            icon_name: 'network-transmit-receive-symbolic',
        });

        const group = new Adw.PreferencesGroup({ title: _('Runtime Health') });

        // Status rows — filled by _refreshStatus
        this._statusRows = {};
        const fields = ['status', 'version', 'tools_loaded', 'sessions', 'mcp_servers'];
        const labels = {
            status: 'Connection', version: 'Runtime Version',
            tools_loaded: 'Tools Loaded', sessions: 'Sessions',
            mcp_servers: 'Active MCP Servers',
        };

        for (const key of fields) {
            const row = new Adw.ActionRow({ title: _(labels[key]) });
            const val = new Gtk.Label({ label: '—', xalign: 1 });
            row.add_suffix(val);
            this._statusRows[key] = val;
            group.add(row);
        }

        const refreshBtn = new Gtk.Button({
            label: _('↺ Refresh'),
            css_classes: ['suggested-action'],
            halign: Gtk.Align.END,
            margin_top: 8,
        });
        refreshBtn.connect('clicked', () => this._refreshStatus());

        page.add(group);

        const btnGroup = new Adw.PreferencesGroup();
        const btnRow = new Adw.ActionRow({ title: '' });
        btnRow.add_suffix(refreshBtn);
        btnGroup.add(btnRow);
        page.add(btnGroup);

        // Auto-refresh on open
        GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => { this._refreshStatus(); return GLib.SOURCE_REMOVE; });

        return page;
    }

    _refreshStatus() {
        const data = this._fetch('/health');
        if (!data) {
            this._statusRows['status'].label = '● Offline';
            this._statusRows['status'].css_classes = ['error'];
            return;
        }
        const set = (key, val) => { if (this._statusRows[key]) this._statusRows[key].label = String(val ?? '—'); };
        set('status', data.status === 'ok' ? '● Online' : '● Degraded');
        set('version', data.version);
        set('tools_loaded', data.tools_loaded);
        set('sessions', data.sessions);
        set('mcp_servers', Array.isArray(data.mcp_servers) ? data.mcp_servers.join(', ') : data.mcp_servers);
        if (this._statusRows['status']) {
            this._statusRows['status'].css_classes = data.status === 'ok' ? ['success'] : ['warning'];
        }
    }

    // ── 2. LLM CONFIGURATION ───────────────────────────────────────────────────

    _buildLlmConfigPage() {
        const page = new Adw.PreferencesPage({
            title: _('LLM Config'),
            icon_name: 'preferences-system-symbolic',
        });

        const group = new Adw.PreferencesGroup({ title: _('Global LLM Settings') });

        // Provider Dropdown
        this._providerRow = new Adw.ComboRow({ title: _('Provider') });
        const providerModel = new Gtk.StringList();
        ['ollama', 'openai', 'anthropic', 'google_genai', 'groq', 'openai_compatible'].forEach(p => providerModel.append(p));
        this._providerRow.model = providerModel;

        this._modelRow = new Adw.EntryRow({ title: _('Model Name') });
        this._baseUrlRow = new Adw.EntryRow({ title: _('Base URL (for Ollama/Compatible)') });
        this._apiKeyRow = new Adw.PasswordEntryRow({ title: _('API Key') });
        this._systemPromptRow = new Adw.EntryRow({ title: _('System Prompt') });
        this._temperatureRow = new Adw.SpinRow({
            title: _('Temperature'),
            adjustment: new Gtk.Adjustment({ lower: 0.0, upper: 2.0, step_increment: 0.1, page_increment: 0.5 })
        });
        this._temperatureRow.digits = 2;

        this._maxIterationsRow = new Adw.SpinRow({
            title: _('Max Agent Iterations'),
            adjustment: new Gtk.Adjustment({ lower: 1, upper: 20, step_increment: 1, page_increment: 5 })
        });

        const saveBtn = new Gtk.Button({
            label: _('Save Configuration'),
            css_classes: ['suggested-action'],
            halign: Gtk.Align.END,
            margin_top: 12,
        });
        saveBtn.connect('clicked', () => this._saveLlmConfig());

        group.add(this._providerRow);
        group.add(this._modelRow);
        group.add(this._baseUrlRow);
        group.add(this._apiKeyRow);
        group.add(this._systemPromptRow);
        group.add(this._temperatureRow);
        group.add(this._maxIterationsRow);

        const btnRow = new Adw.ActionRow({ title: '' });
        btnRow.add_suffix(saveBtn);
        group.add(btnRow);

        page.add(group);

        // Load current config
        GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => { this._loadLlmConfig(); return GLib.SOURCE_REMOVE; });

        return page;
    }

    _loadLlmConfig() {
        const config = this._fetch('/config/llm');
        if (!config) return;

        // Set provider dropdown
        for (let i = 0; i < this._providerRow.model.get_n_items(); i++) {
            if (this._providerRow.model.get_string(i) === config.provider) {
                this._providerRow.selected = i;
                break;
            }
        }

        this._modelRow.text = config.model || '';
        this._baseUrlRow.text = config.base_url || '';
        this._apiKeyRow.text = config.api_key || '';
        this._systemPromptRow.text = config.system_prompt || '';
        this._temperatureRow.value = config.temperature ?? 0.7;
        this._maxIterationsRow.value = config.max_iterations ?? 6;
    }

    _saveLlmConfig() {
        const providerStr = this._providerRow.model.get_string(this._providerRow.selected);
        const body = {
            provider: providerStr,
            model: this._modelRow.text,
            base_url: this._baseUrlRow.text,
            api_key: this._apiKeyRow.text,
            system_prompt: this._systemPromptRow.text,
            temperature: this._temperatureRow.value,
            max_iterations: this._maxIterationsRow.value,
        };

        const res = this._fetch('/config/llm', 'PUT', body);
        if (res) {
            // Flash success
            const btn = this._providerRow.get_parent().get_last_child().get_last_child(); // The save button
            const oldLabel = btn.label;
            btn.label = _('✓ Saved');
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
                if (btn) btn.label = oldLabel;
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    // ── 3. MCP SERVERS ────────────────────────────────────────────────────────

    _buildMcpPage() {
        const page = new Adw.PreferencesPage({
            title: _('MCP Servers'),
            icon_name: 'preferences-system-network-symbolic',
        });

        this._mcpGroup = new Adw.PreferencesGroup({ title: _('Registered MCP Servers') });
        page.add(this._mcpGroup);

        // Add external server
        const addGroup = new Adw.PreferencesGroup({ title: _('Add External MCP Server') });

        this._mcpName = new Adw.EntryRow({ title: _('Name (unique)') });
        this._mcpTransport = new Adw.ComboRow({ title: _('Transport') });
        const transportModel = new Gtk.StringList();
        ['http', 'stdio'].forEach(t => transportModel.append(t));
        this._mcpTransport.model = transportModel;

        this._mcpEndpoint = new Adw.EntryRow({ title: _('HTTP URL (for http transport)') });
        this._mcpCommand = new Adw.EntryRow({ title: _('Command (for stdio transport)') });
        this._mcpArgs = new Adw.EntryRow({ title: _('Args (space-separated)') });

        const addBtn = new Gtk.Button({
            label: _('＋ Register Server'),
            css_classes: ['suggested-action'],
            halign: Gtk.Align.END,
            margin_top: 4,
        });
        addBtn.connect('clicked', () => this._addMcpServer());

        addGroup.add(this._mcpName);
        addGroup.add(this._mcpTransport);
        addGroup.add(this._mcpEndpoint);
        addGroup.add(this._mcpCommand);
        addGroup.add(this._mcpArgs);
        const addRow = new Adw.ActionRow({ title: '' });
        addRow.add_suffix(addBtn);
        addGroup.add(addRow);
        page.add(addGroup);

        GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => { this._refreshMcp(); return GLib.SOURCE_REMOVE; });

        return page;
    }

    _refreshMcp() {
        if (!this._mcpRows) this._mcpRows = [];
        this._mcpRows.forEach(row => this._mcpGroup.remove(row));
        this._mcpRows = [];

        const data = this._fetch('/mcp/servers');
        const servers = Array.isArray(data) ? data : [];

        if (!servers.length) { this._mcpGroup.description = _('No servers found'); return; }
        this._mcpGroup.description = null;

        for (const s of servers) {
            const row = new Adw.ActionRow({
                title: s.name,
                subtitle: `${s.transport} ${s.endpoint ?? s.command ?? ''}`.trim(),
            });

            const statusIcon = new Gtk.Image({
                icon_name: s.builtin ? 'security-high-symbolic' : 'network-server-symbolic',
                tooltip_text: s.builtin ? 'Built-in' : 'External',
            });
            row.add_prefix(statusIcon);

            // Refresh tools count if available
            if (s.tool_count !== undefined) {
                row.add_suffix(new Gtk.Label({
                    label: `${s.tool_count} tools`,
                    css_classes: ['dim-label'],
                }));
            }

            // Remove non-builtins
            if (!s.builtin) {
                const delBtn = new Gtk.Button({
                    icon_name: 'user-trash-symbolic',
                    css_classes: ['destructive-action', 'flat'],
                    valign: Gtk.Align.CENTER,
                });
                delBtn.connect('clicked', () => {
                    this._fetch(`/mcp/servers/${s.name}`, 'DELETE');
                    this._refreshMcp();
                });
                row.add_suffix(delBtn);
            }

            this._mcpRows.push(row);
            this._mcpGroup.add(row);
        }
    }

    _addMcpServer() {
        const name = this._mcpName.text.trim();
        if (!name) return;

        const transport = this._mcpTransport.selected === 0 ? 'http' : 'stdio';
        const body = { name, transport };
        if (transport === 'http') {
            body.endpoint = this._mcpEndpoint.text.trim();
        } else {
            body.command = this._mcpCommand.text.trim();
            const args = this._mcpArgs.text.trim();
            if (args) body.args = args.split(/\s+/);
        }
        this._fetch('/mcp/servers', 'POST', body);
        this._mcpName.text = '';
        this._refreshMcp();
    }

    // ── 4. TOOLS ──────────────────────────────────────────────────────────────

    _buildToolsPage() {
        const page = new Adw.PreferencesPage({
            title: _('Tools'),
            icon_name: 'utilities-terminal-symbolic',
        });

        this._toolsGroup = new Adw.PreferencesGroup({ title: _('Available Tools') });

        // Search bar
        const searchGroup = new Adw.PreferencesGroup();
        this._toolSearch = new Adw.EntryRow({ title: _('Search tools…') });
        this._toolSearch.connect('changed', () => this._filterTools());
        searchGroup.add(this._toolSearch);

        const refreshBtn = new Gtk.Button({
            label: _('↺ Reload'),
            css_classes: ['flat'],
            halign: Gtk.Align.END,
        });
        refreshBtn.connect('clicked', () => this._refreshTools());
        const rfRow = new Adw.ActionRow({ title: '' });
        rfRow.add_suffix(refreshBtn);
        searchGroup.add(rfRow);

        page.add(searchGroup);
        page.add(this._toolsGroup);

        GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => { this._refreshTools(); return GLib.SOURCE_REMOVE; });

        return page;
    }

    _refreshTools() {
        if (!this._toolRows) this._toolRows = [];
        this._toolRows.forEach(row => this._toolsGroup.remove(row));
        this._toolRows = [];

        const tools = this._fetch('/tools');
        this._allTools = Array.isArray(tools) ? tools : [];
        this._renderTools(this._allTools);
    }

    _filterTools() {
        const q = this._toolSearch.text.trim().toLowerCase();
        const filtered = q
            ? this._allTools.filter(t =>
                t.name?.toLowerCase().includes(q) ||
                t.description?.toLowerCase().includes(q))
            : this._allTools;

        let child = this._toolsGroup.get_first_child();
        while (child) { const next = child.get_next_sibling(); this._toolsGroup.remove(child); child = next; }
        this._renderTools(filtered);
    }

    _renderTools(tools) {
        this._toolsGroup.description = tools.length ? null : _('No tools found');
        for (const tool of tools) {
            const row = new Adw.ExpanderRow({
                title: tool.name ?? '—',
                subtitle: (tool.description ?? '').slice(0, 80),
            });

            // Full description
            if (tool.description) {
                const descRow = new Adw.ActionRow({ title: _('Description') });
                const desc = new Gtk.Label({
                    label: tool.description,
                    wrap: true,
                    xalign: 0,
                    margin_top: 4,
                    margin_bottom: 4,
                    css_classes: ['dim-label'],
                });
                descRow.set_child(desc);
                row.add_row(descRow);
            }

            // Parameters
            const schema = tool.inputSchema ?? tool.args_schema ?? {};
            const props = schema?.properties ?? {};
            if (Object.keys(props).length) {
                const paramRow = new Adw.ActionRow({ title: _('Parameters') });
                const params = Object.entries(props).map(([k, v]) =>
                    `${k}: ${v.type ?? 'any'}`
                ).join(', ');
                paramRow.subtitle = params;
                row.add_row(paramRow);
            }

            // Source MCP server tag
            if (tool.server) {
                const srcRow = new Adw.ActionRow({ title: _('MCP Server'), subtitle: tool.server });
                row.add_row(srcRow);
            }

            this._toolRows.push(row);
            this._toolsGroup.add(row);
        }
    }

    // ── 5. CONNECTION ─────────────────────────────────────────────────────────

    _buildConnectionPage() {
        const page = new Adw.PreferencesPage({
            title: _('Connection'),
            icon_name: 'network-server-symbolic',
        });

        const connGroup = new Adw.PreferencesGroup({ title: _('Backend') });
        const urlRow = new Adw.EntryRow({ title: _('Server URL') });
        this._settings.bind('server-url', urlRow, 'text', 0);
        const keyRow = new Adw.PasswordEntryRow({ title: _('API Key (optional)') });
        this._settings.bind('api-key', keyRow, 'text', 0);
        const agentRow = new Adw.EntryRow({ title: _('Default Agent ID') });
        this._settings.bind('agent-id', agentRow, 'text', 0);
        connGroup.add(urlRow);
        connGroup.add(keyRow);
        connGroup.add(agentRow);
        page.add(connGroup);

        const ctxGroup = new Adw.PreferencesGroup({
            title: _('Context Injection'),
            description: _('What desktop context is sent with each message'),
        });
        for (const [key, label] of [
            ['inject-active-app', _('Active application name')],
            ['inject-window-title', _('Focused window title')],
            ['inject-clipboard', _('Clipboard content')],
        ]) {
            const row = new Adw.SwitchRow({ title: label });
            this._settings.bind(key, row, 'active', 0);
            ctxGroup.add(row);
        }
        page.add(ctxGroup);

        return page;
    }

    // ── 6. APPEARANCE ─────────────────────────────────────────────────────────

    _buildAppearancePage() {
        const page = new Adw.PreferencesPage({
            title: _('Appearance'),
            icon_name: 'preferences-desktop-appearance-symbolic',
        });

        const grp = new Adw.PreferencesGroup({ title: _('Panel & Text Styling') });

        const fontRow = new Adw.SpinRow({
            title: _('Message Font Size (px)'),
            adjustment: new Gtk.Adjustment({ lower: 8, upper: 24, step_increment: 1 }),
        });
        this._settings.bind('font-size', fontRow, 'value', 0);

        const marginRow = new Adw.SpinRow({
            title: _('Panel Margin (px)'),
            subtitle: _('Distance from screen edge'),
            adjustment: new Gtk.Adjustment({ lower: 0, upper: 80, step_increment: 1 }),
        });
        this._settings.bind('margin', marginRow, 'value', 0);

        const opacRow = new Adw.SpinRow({
            title: _('Panel Opacity (%)'),
            subtitle: _('Requires extension reload to fully apply'),
            adjustment: new Gtk.Adjustment({ lower: 20, upper: 100, step_increment: 1 }),
        });
        this._settings.bind('opacity', opacRow, 'value', 0);

        grp.add(fontRow);
        grp.add(marginRow);
        grp.add(opacRow);
        page.add(grp);

        return page;
    }
}
