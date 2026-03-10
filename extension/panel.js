/**
 * panel.js — Modern top-bar indicator and floating chat popup.
 *
 * Features:
 *  - Animated open/close (slide + fade)
 *  - Typing indicator while waiting for response
 *  - Token counter display
 *  - Clear/new session button
 *  - Keyboard shortcut: Enter to send, Shift+Enter for newline
 *  - Message count badge on icon
 */

import St from 'gi://St';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {
    UserBubble,
    AssistantBubble,
    ToolCallBubble,
    SystemBubble,
    TypingIndicator,
} from './messages.js';

const DEFAULT_PANEL_WIDTH = 420;
const DEFAULT_PANEL_HEIGHT = 580;

export const GnomeAgentIndicator = GObject.registerClass(
    class GnomeAgentIndicator extends PanelMenu.Button {
        _init(api, getContext, settings, extensionPath) {
            super._init(0.5, 'Gnome Agent');
            this._api = api;
            this._getContext = getContext;
            this._settings = settings;
            this._extensionPath = extensionPath;
            this._sessionId = null;
            this._cancelStream = null;
            this._currentAssistantBubble = null;
            this._currentToolBubbles = {};
            this._typingIndicator = null;
            this._msgCount = 0;

            this._iconBox = new St.BoxLayout({ style: 'spacing: 4px; padding: 0 4px;' });

            let iconFile = Gio.File.new_for_path(this._extensionPath + '/icon.png');
            let gicon = new Gio.FileIcon({ file: iconFile });

            this._icon = new St.Icon({
                gicon: gicon,
                icon_size: 24,
                style_class: 'system-status-icon',
                style: 'color: #7ec8e3;',
            });
            this._iconBox.add_child(this._icon);
            this.add_child(this._iconBox);

            this._popup = this._buildPopup();

            // Fix click propagation on GNOME shell:
            this.connect('button-release-event', (actor, event) => {
                if (event.get_button() === 1) { // Left click
                    this._togglePopup();
                    return Clutter.EVENT_STOP;
                }
                return Clutter.EVENT_PROPAGATE;
            });

            this._settingsId = this._settings.connect('changed', () => this._applySettings());
            this._applySettings();

            // Suppress default PanelMenu dropdown
            this.menu.actor.hide();
        }

        _applySettings() {
            this.panelWidth = this._settings.get_int('window-width') || DEFAULT_PANEL_WIDTH;
            this.panelHeight = this._settings.get_int('window-height') || DEFAULT_PANEL_HEIGHT;

            const opac = (this._settings.get_int('opacity') || 95) / 100.0;
            const targetActor = this._popupContainer || this._popup;
            if (targetActor) {
                targetActor.style = `
                    background-color: rgba(14, 14, 24, ${opac});
                    border: 1px solid rgba(80, 100, 180, 0.3);
                    border-radius: 18px;
                    padding: 0;
                    width: ${this.panelWidth}px;
                `;
            }
            // Update input area as well to match opacity
            if (this._inputArea) {
                this._inputArea.style = `
                    background-color: rgba(20, 20, 36, ${opac});
                    border-top: 1px solid rgba(80,100,180,0.2);
                    border-radius: 0 0 18px 18px;
                    padding: 10px 12px;
                    spacing: 8px;
                `;
            }
            if (this._scrollView) {
                this._scrollView.style = `height: ${this.panelHeight - 160}px; padding: 8px 0;`;
            }
            if (this._historyPanel) {
                this._historyPanel.style = `
                    background-color: rgba(22, 22, 40, ${opac});
                    border-radius: 18px;
                    padding: 0;
                    width: ${this.panelWidth}px;
                    height: ${this.panelHeight}px;
                `;
            }
        }

        // ── Build popup ───────────────────────────────────────────────────────────

        _buildPopup() {
            this.panelWidth = this._settings.get_int('window-width') || DEFAULT_PANEL_WIDTH;
            this.panelHeight = this._settings.get_int('window-height') || DEFAULT_PANEL_HEIGHT;

            const panel = new St.BoxLayout({
                vertical: true,
                style: `
                border-radius: 18px;
                padding: 0;
                width: ${this.panelWidth}px;
            `,
                visible: false,
                opacity: 0,
            });

            // ── Header bar ───────────────────────────────────────────────────────
            const header = new St.BoxLayout({
                style: `
                background-color: rgba(22, 22, 40, 0.98);
                border-radius: 18px 18px 0 0;
                border-bottom: 1px solid rgba(80,100,180,0.2);
                padding: 12px 14px;
                spacing: 8px;
            `,
            });

            const agentIcon = new St.Label({ text: '✦', style: 'color: #7ec8e3; font-size: 16px;' });
            const titleCol = new St.BoxLayout({ vertical: true, x_expand: true });

            this._titleRow = new St.BoxLayout({
                x_expand: true,
                style: 'spacing: 6px;',
            });
            this._titleLabel = new St.Label({
                text: 'Gnome Agent',
                style: 'color: #e0e8ff; font-size: 13px; font-weight: bold;',
            });
            this._titleRow.add_child(this._titleLabel);

            this._subtitleLabel = new St.Label({
                text: 'Ready',
                style: 'color: rgba(120,140,200,0.7); font-size: 10px;',
            });
            titleCol.add_child(this._titleRow);
            titleCol.add_child(this._subtitleLabel);

            // Header action buttons
            const historyBtn = this._headerBtn('🕑', 'History', () => this._toggleHistory());
            const newBtn = this._headerBtn('↺', 'New chat', () => this._clearChat());
            const closeBtn = this._headerBtn('✕', 'Close', () => this._hidePopup());

            header.add_child(agentIcon);
            header.add_child(titleCol);
            header.add_child(historyBtn);
            header.add_child(newBtn);
            header.add_child(closeBtn);
            panel.add_child(header);

            // ── Scrollable message list ───────────────────────────────────────────
            this._scrollView = new St.ScrollView({
                style: `height: ${this.panelHeight - 160}px; padding: 8px 0;`,
                hscrollbar_policy: St.PolicyType.NEVER,
                vscrollbar_policy: St.PolicyType.AUTOMATIC,
            });
            this._messageBox = new St.BoxLayout({
                vertical: true,
                style: 'spacing: 6px; padding: 4px 0;',
                x_expand: true,
            });
            this._scrollView.set_child(this._messageBox);
            panel.add_child(this._scrollView);

            // ── Status / token counter ────────────────────────────────────────────
            const statusBar = new St.BoxLayout({
                style: 'padding: 2px 14px; spacing: 8px;',
            });
            this._statusLabel = new St.Label({
                text: '',
                style: 'color: rgba(120,140,200,0.55); font-size: 10px;',
                x_expand: true,
            });
            statusBar.add_child(this._statusLabel);
            panel.add_child(statusBar);

            // ── Input row ─────────────────────────────────────────────────────────
            this._inputArea = new St.BoxLayout({
                style: `
                border-radius: 0 0 18px 18px;
                padding: 10px 12px;
                spacing: 8px;
            `,
            });

            this._input = new St.Entry({
                hint_text: 'Ask your GNOME agent…',
                x_expand: true,
                style: `
                background-color: rgba(32, 32, 54, 0.95);
                border: 1px solid rgba(80,100,180,0.35);
                border-radius: 12px;
                color: #e0e0f8;
                padding: 9px 14px;
                font-size: 13px;
            `,
            });
            this._input.clutter_text.connect('key-press-event', (_, event) => {
                const sym = event.get_key_symbol();
                const shift = !!(event.get_state() & Clutter.ModifierType.SHIFT_MASK);
                if (sym === Clutter.KEY_Return && !shift) {
                    this._send();
                    return Clutter.EVENT_STOP;
                }
                return Clutter.EVENT_PROPAGATE;
            });

            this._sendBtn = new St.Button({
                style: `
                background-color: rgba(30, 100, 220, 0.88);
                border-radius: 12px;
                color: white;
                font-size: 17px;
                font-weight: bold;
                width: 40px; height: 40px;
                transition-duration: 100ms;
            `,
            });
            const sendIcon = new St.Label({ text: '↑', style: 'font-size: 18px;' });
            this._sendBtn.set_child(sendIcon);
            this._sendBtn.connect('clicked', () => this._send());

            this._inputArea.add_child(this._input);
            this._inputArea.add_child(this._sendBtn);
            panel.add_child(this._inputArea);

            Main.layoutManager.addChrome(panel, { affectsInputRegion: true });

            // Welcome message
            GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                this._addMessage(SystemBubble('New conversation started'));
                return GLib.SOURCE_REMOVE;
            });

            return panel;
        }

        _headerBtn(label, tooltip, callback) {
            const btn = new St.Button({
                label,
                style: `
                color: rgba(150,160,200,0.6);
                font-size: 13px;
                padding: 4px 8px;
                border-radius: 8px;
                background: none;
                transition-duration: 120ms;
            `,
            });
            btn.connect('enter-event', () => { btn.style = btn.style + 'color: rgba(200,210,255,0.9);'; });
            btn.connect('leave-event', () => { btn.style = btn.style.replace('color: rgba(200,210,255,0.9);', ''); });
            btn.connect('clicked', callback);
            return btn;
        }

        // ── History overlay ───────────────────────────────────────────────────────

        _buildHistoryPanel() {
            this._historyPanel = new St.BoxLayout({
                vertical: true,
                style: `
                    background-color: rgba(22, 22, 40, 0.98);
                    border-radius: 18px;
                    padding: 0;
                    width: ${PANEL_WIDTH}px;
                    height: ${PANEL_HEIGHT}px;
                `,
                visible: false,
                opacity: 0,
            });

            const header = new St.BoxLayout({
                style: `
                    border-bottom: 1px solid rgba(80,100,180,0.2);
                    padding: 12px 14px;
                    spacing: 8px;
                `,
            });
            const title = new St.Label({
                text: 'Conversation History',
                style: 'color: #e0e8ff; font-size: 14px; font-weight: bold;',
                x_expand: true,
            });
            const closeBtn = this._headerBtn('✕', 'Close History', () => this._hideHistory());

            header.add_child(title);
            header.add_child(closeBtn);
            this._historyPanel.add_child(header);

            this._historyScrollView = new St.ScrollView({
                style: `padding: 8px 0;`,
                hscrollbar_policy: St.PolicyType.NEVER,
                vscrollbar_policy: St.PolicyType.AUTOMATIC,
                x_expand: true,
                y_expand: true,
            });
            this._historyBox = new St.BoxLayout({
                vertical: true,
                style: 'spacing: 4px; padding: 4px 8px;',
            });
            this._historyScrollView.set_child(this._historyBox);
            this._historyPanel.add_child(this._historyScrollView);

            return this._historyPanel;
        }

        _toggleHistory() {
            if (this._historyPanel.visible) {
                this._hideHistory();
            } else {
                this._showHistory();
            }
        }

        _showHistory() {
            this._historyPanel.visible = true;
            this._historyPanel.ease({
                opacity: 255,
                duration: 200,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
            this._mainContainer.ease({
                opacity: 0,
                duration: 200,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                onComplete: () => { this._mainContainer.visible = false; }
            });
            this._loadHistory();
        }

        _hideHistory() {
            this._mainContainer.visible = true;
            this._mainContainer.ease({
                opacity: 255,
                duration: 200,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
            this._historyPanel.ease({
                opacity: 0,
                duration: 200,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                onComplete: () => { this._historyPanel.visible = false; }
            });
        }

        async _loadHistory() {
            this._historyBox.destroy_all_children();
            const loading = new St.Label({ text: 'Loading sessions...', style: 'color: gray; padding: 12px; text-align: center;' });
            this._historyBox.add_child(loading);

            try {
                const url = this._settings.get_string('server-url') + '/sessions';
                const apiKey = this._settings.get_string('api-key');
                let uri;
                try { uri = GLib.Uri.parse(url, GLib.UriFlags.NONE); } catch { return; }

                const Soup = (await import('gi://Soup?version=3.0')).default;
                const session = new Soup.Session();
                const msg = new Soup.Message({ method: 'GET', uri });
                if (apiKey) msg.request_headers.append('Authorization', `Bearer ${apiKey}`);

                const bytes = await session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, null);
                if (msg.status_code === 200) {
                    const text = new TextDecoder().decode(bytes.get_data());
                    const sessions = JSON.parse(text);
                    this._renderHistory(sessions);
                } else {
                    loading.text = 'Failed to load history';
                }
            } catch (e) {
                loading.text = 'Failed to load config';
            }
        }

        _renderHistory(sessions) {
            this._historyBox.destroy_all_children();
            if (!sessions || sessions.length === 0) {
                this._historyBox.add_child(new St.Label({ text: 'No conversation history found.', style: 'color: gray; padding: 12px; text-align: center;' }));
                return;
            }

            for (const s of sessions) {
                const d = new Date(s.created_at + 'Z');

                const btn = new St.Button({
                    style_class: 'button',
                    style: `
                        text-align: left;
                        padding: 10px 14px;
                        background-color: rgba(40,40,60,0.5);
                        border-radius: 8px;
                    `,
                    x_expand: true,
                });

                const box = new St.BoxLayout({ vertical: true });
                box.add_child(new St.Label({ text: `Session ${s.id.slice(0, 8)}`, style: 'font-weight: bold; color: #e0e8ff;' }));
                box.add_child(new St.Label({ text: d.toLocaleString(), style: 'font-size: 11px; color: gray;' }));
                btn.set_child(box);

                // Hover fx
                btn.connect('notify::hover', () => {
                    btn.style = btn.hover
                        ? `text-align: left; padding: 10px 14px; background-color: rgba(60,60,90,0.8); border-radius: 8px;`
                        : `text-align: left; padding: 10px 14px; background-color: rgba(40,40,60,0.5); border-radius: 8px;`;
                });

                btn.connect('clicked', () => this._resumeSession(s.id));
                this._historyBox.add_child(btn);
            }
        }

        async _resumeSession(sessionId) {
            this._clearChatUI();
            this._sessionId = sessionId;
            this._hideHistory();
            this._setBusy(true);
            this._setStatus('Loading messages...');

            try {
                const url = this._settings.get_string('server-url') + `/sessions/${sessionId}/messages`;
                const apiKey = this._settings.get_string('api-key');
                let uri;
                try { uri = GLib.Uri.parse(url, GLib.UriFlags.NONE); } catch { return; }

                const Soup = (await import('gi://Soup?version=3.0')).default;
                const session = new Soup.Session();
                const msg = new Soup.Message({ method: 'GET', uri });
                if (apiKey) msg.request_headers.append('Authorization', `Bearer ${apiKey}`);

                const bytes = await session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, null);
                if (msg.status_code === 200) {
                    const text = new TextDecoder().decode(bytes.get_data());
                    const messages = JSON.parse(text);
                    this._renderMessages(messages);
                } else {
                    this._addMessage(SystemBubble('Failed to load messages.', true));
                }
            } catch (e) {
                this._addMessage(SystemBubble('Failed to connect to server.', true));
            }
            this._setBusy(false);
            this._setStatus('');
        }

        _renderMessages(messages) {
            const opts = { fontSize: this._settings.get_int('font-size') || 13 };
            for (const msg of messages) {
                if (msg.role === 'user') {
                    // Extract text before TOON context if present
                    let txt = msg.content;
                    if (txt.includes('[Desktop Context — TOON]')) {
                        const parts = txt.split('\\n[User Message]\\n');
                        if (parts.length > 1) txt = parts[1];
                        else txt = "Included desktop context."; // Fallback
                    }
                    this._addMessage(UserBubble(txt.trim(), opts));
                } else if (msg.role === 'assistant') {
                    this._addMessage(AssistantBubble(msg.content, opts).actor);
                }
            }
            this._scrollToBottom();
        }

        // ── Popup show/hide with animation ────────────────────────────────────────

        _togglePopup() {
            // Re-wrap the main UI and history overlay into a stack-like structure
            if (!this._popupContainer) {
                this._popupContainer = new St.Widget({ layout_manager: new Clutter.BinLayout(), reactive: true });
                this._mainContainer = this._popup;
                this._historyPanel = this._buildHistoryPanel();

                this._popupContainer.add_child(this._mainContainer);
                this._popupContainer.add_child(this._historyPanel);

                // Add resize handle
                this._resizeHandle = new St.Icon({
                    icon_name: 'view-restore-symbolic',
                    icon_size: 16,
                    style: 'color: rgba(150, 160, 200, 0.6); margin-bottom: 2px; margin-right: 2px; cursor: se-resize;',
                    reactive: true,
                });

                // Position resize handle at bottom right
                const handleContainer = new St.Widget({
                    layout_manager: new Clutter.BinLayout(),
                    x_expand: true, y_expand: true,
                    x_align: Clutter.ActorAlign.END,
                    y_align: Clutter.ActorAlign.END,
                });
                handleContainer.add_child(this._resizeHandle);
                this._popupContainer.add_child(handleContainer);

                this._setupDragResize();

                // Keep references updated for Main.layoutManager tracking
                this._popup = this._popupContainer;
                this._applySettings();
            }

            if (this._popup.visible) {
                this._hidePopup();
            } else {
                this._showPopup();
            }
        }

        _setupDragResize() {
            let isDragging = false;
            let startX, startY;
            let startW, startH;

            this._resizeHandle.connect('button-press-event', (actor, event) => {
                const [bx, by] = event.get_button();
                if (bx !== 1) return Clutter.EVENT_PROPAGATE; // only left click
                isDragging = true;
                [startX, startY] = event.get_coords();
                startW = this.panelWidth;
                startH = this.panelHeight;
                Clutter.grab_pointer(actor);
                return Clutter.EVENT_STOP;
            });

            this._resizeHandle.connect('motion-event', (actor, event) => {
                if (!isDragging) return Clutter.EVENT_PROPAGATE;
                const [cx, cy] = event.get_coords();
                const dx = cx - startX;
                const dy = cy - startY;

                // Minimum sizes
                this.panelWidth = Math.max(300, startW + dx);
                this.panelHeight = Math.max(400, startH + dy);

                this._applySettings(); // Update inline styles with new dims
                this._repositionPopup();
                return Clutter.EVENT_STOP;
            });

            this._resizeHandle.connect('button-release-event', (actor, event) => {
                if (!isDragging) return Clutter.EVENT_PROPAGATE;
                isDragging = false;
                Clutter.ungrab_pointer();

                // Persist new sizes
                this._settings.set_int('window-width', this.panelWidth);
                this._settings.set_int('window-height', this.panelHeight);

                return Clutter.EVENT_STOP;
            });
        }

        _showPopup() {
            this._repositionPopup();
            this._popup.show();
            this._popup.ease({
                opacity: 255,
                duration: 180,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
            this._input.grab_key_focus();
            this._icon.style = 'color: #50d8ff;';
        }

        _hidePopup() {
            this._popup.ease({
                opacity: 0,
                duration: 150,
                mode: Clutter.AnimationMode.EASE_IN_QUAD,
                onComplete: () => this._popup.hide(),
            });
            this._icon.style = 'color: #7ec8e3;';
        }

        _repositionPopup() {
            const margin = this._settings.get_int('margin') ?? 6;
            const panelBox = Main.layoutManager.panelBox;
            const [px] = this.get_transformed_position();
            const x = Math.max(margin, Math.min(px, global.stage.width - this.panelWidth - margin));
            this._popup.set_position(x, panelBox.height + margin);
        }

        // ── Chat logic ────────────────────────────────────────────────────────────

        _send() {
            const message = this._input.get_text().trim();
            if (!message || this._cancelStream) return;

            this._input.set_text('');
            const opts = { fontSize: this._settings.get_int('font-size') || 13 };
            this._addMessage(UserBubble(message, opts));
            this._setBusy(true);
            this._showTyping();

            const ctx = this._getContext?.() ?? {};

            this._cancelStream = this._api.chat({
                message,
                sessionId: this._sessionId,
                context: ctx,
                onEvent: (type, data) => this._handleEvent(type, data),
                onDone: () => this._onStreamDone(),
                onError: (err) => {
                    this._hideTyping();
                    this._addMessage(SystemBubble(`Error: ${err}`, true));
                    this._onStreamDone();
                },
            });

        }

        _handleEvent(type, data) {
            switch (type) {

                case 'session':
                    this._sessionId = data.session_id;
                    break;

                case 'message': {
                    this._hideTyping();
                    if (!this._currentAssistantBubble) {
                        const opts = { fontSize: this._settings.get_int('font-size') || 13 };
                        this._currentAssistantBubble = AssistantBubble('', opts);
                        this._addMessage(this._currentAssistantBubble.actor);
                    }
                    if (data.text) this._currentAssistantBubble.appendText(data.text);
                    break;
                }

                case 'tool_call': {
                    this._hideTyping();
                    const bubble = ToolCallBubble(data.tool_name || data.name || 'tool');
                    this._currentToolBubbles[data.call_id] = bubble;
                    this._addMessage(bubble.actor);
                    this._setStatus(`⚙ calling ${data.tool_name || 'tool'}…`);
                    break;
                }

                case 'tool_result': {
                    const b = this._currentToolBubbles[data.call_id];
                    b?.setDone();
                    this._setStatus('');
                    break;
                }

                case 'final_answer': {
                    this._hideTyping();
                    if (data.text) {
                        if (this._currentAssistantBubble) {
                            this._currentAssistantBubble.setText(data.text);
                            this._currentAssistantBubble.finalize?.();
                        } else {
                            const opts = { fontSize: this._settings.get_int('font-size') || 13 };
                            const b = AssistantBubble(data.text, opts);
                            this._addMessage(b.actor);
                        }
                    }
                    break;
                }

                case 'error':
                    this._hideTyping();
                    this._addMessage(SystemBubble(data.message || 'Unknown error', true));
                    break;
            }

            this._scrollToBottom();
        }

        _onStreamDone() {
            this._currentAssistantBubble?.finalize?.();
            this._cancelStream = null;
            this._currentAssistantBubble = null;
            this._currentToolBubbles = {};
            this._setBusy(false);
            this._setStatus('');
            this._scrollToBottom();
        }

        _clearChat() {
            this._clearChatUI();
            this._sessionId = null;
            this._addMessage(SystemBubble('New conversation started'));
        }

        _clearChatUI() {
            this._cancelStream?.();
            this._cancelStream = null;
            this._currentAssistantBubble = null;
            this._currentToolBubbles = {};
            this._typingIndicator = null;
            this._messageBox.destroy_all_children();
            this._setBusy(false);
            this._setStatus('');
        }

        // ── Helpers ───────────────────────────────────────────────────────────────

        _showTyping() {
            if (this._typingIndicator) return;
            this._typingIndicator = TypingIndicator();
            this._addMessage(this._typingIndicator);
        }

        _hideTyping() {
            if (!this._typingIndicator) return;
            this._typingIndicator.destroy();
            this._typingIndicator = null;
        }

        _addMessage(actor) {
            this._messageBox.add_child(actor);
            this._scrollToBottom();
        }

        _setStatus(text) {
            this._statusLabel.text = text;
            this._subtitleLabel.text = text || 'Ready';
        }

        _setBusy(busy) {
            this._sendBtn.reactive = !busy;
            this._sendBtn.style = this._sendBtn.style.replace(
                busy ? 'rgba(30, 100, 220, 0.88)' : 'rgba(30,60,120,0.5)',
                busy ? 'rgba(30,60,120,0.5)' : 'rgba(30, 100, 220, 0.88)',
            );
        }



        _scrollToBottom() {
            GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                const adj = this._scrollView.get_vscroll_bar()?.get_adjustment();
                if (adj) adj.value = adj.upper;
                return GLib.SOURCE_REMOVE;
            });
        }

        destroy() {
            this._cancelStream?.();
            Main.layoutManager.removeChrome(this._popup);
            this._popup.destroy();
            super.destroy();
        }
    }
);
