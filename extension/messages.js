/**
 * messages.js — Message bubbles with Pango markdown rendering.
 *
 * Exports:
 *   UserBubble(text)        — right-aligned bubble
 *   AssistantBubble()       — left-aligned bubble with streaming + markdown
 *   ToolCallBubble(name)    — tool status chip
 *   SystemBubble(text)      — centered hint/error
 *   TypingIndicator()       — animated "..." bubble
 */

import St from 'gi://St';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';

// ── Markdown → Pango markup ──────────────────────────────────────────────────

/**
 * Convert a subset of Markdown to Pango markup understood by St.Label.
 * Handles: headers, bold, italic, inline code, bullet lists, numbered lists,
 * horizontal rules, and basic escaping.
 */
export function markdownToPango(text) {
    if (!text) return '';

    // 1. Escape Pango special chars before applying any tags
    let s = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // 2. Fenced code blocks (``` ... ```) → monospace block
    s = s.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, code) => {
        const escaped = code.trimEnd();
        return `\n<span font_family="monospace" size="small" foreground="#a8d8a8" background="rgba(0,0,0,0)">${escaped}</span>\n`;
    });

    // 3. Headers  # / ## / ###
    s = s.replace(/^### (.+)$/gm, '<b><span size="medium">$1</span></b>');
    s = s.replace(/^## (.+)$/gm, '<b><span size="large">$1</span></b>');
    s = s.replace(/^# (.+)$/gm, '<b><span size="x-large">$1</span></b>');

    // 4. Bold **text** and __text__
    s = s.replace(/\*\*(.+?)\*\*/gs, '<b>$1</b>');
    s = s.replace(/__(.+?)__/gs, '<b>$1</b>');

    // 5. Italic *text* and _text_ (avoid matching inside words)
    s = s.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<i>$1</i>');
    s = s.replace(/(?<!_)_(?!_)(.+?)(?<!_)_(?!_)/g, '<i>$1</i>');

    // 6. Inline code `text`
    s = s.replace(/`([^`]+)`/g,
        '<span font_family="monospace" foreground="#a8d8ea" background="rgba(0,0,0,0)">$1</span>');

    // 7. Bullet lists  - item  or  * item
    s = s.replace(/^[-*] (.+)$/gm, '  <span foreground="#7ec8e3">•</span> $1');

    // 8. Numbered lists  1. item
    s = s.replace(/^(\d+)\. (.+)$/gm,
        '<span foreground="#7ec8e3">$1.</span> $2');

    // 9. Horizontal rule
    s = s.replace(/^---+$/gm, '<span foreground="#444">──────────────</span>');

    return s;
}

// ── Bubble factory helpers ───────────────────────────────────────────────────

function _now() {
    const d = new Date();
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

function _makeLabel(markup, opts = {}) {
    const fontSize = opts.fontSize || 13;
    const label = new St.Label({
        style: `font-size: ${fontSize}px; line-height: 1.5;`,
        x_expand: true,
    });
    label.clutter_text.line_wrap = true;
    label.clutter_text.line_wrap_mode = 2; // WORD_CHAR
    label.clutter_text.ellipsize = 0;      // NONE
    label.clutter_text.use_markup = true;
    label.clutter_text.set_markup(markup || '');
    return label;
}

function _timestamp() {
    return new St.Label({
        text: _now(),
        style: 'color: rgba(150,150,180,0.5); font-size: 10px; margin-top: 2px;',
    });
}

function _setSafeMarkup(label, markup, rawText = '') {
    try {
        label.clutter_text.set_markup(markup);
    } catch (e) {
        // If Pango fails to parse the markup, fallback to safe plain text
        const safe = GLib.markup_escape_text(rawText || '', -1);
        label.clutter_text.set_markup(safe);
        console.warn(`[Gnome Agent] Pango markup error: ${e.message}`);
    }
}

// ── Public bubble constructors ───────────────────────────────────────────────

/** User message bubble — right-aligned, blue. */
export function UserBubble(text, opts = {}) {
    const outer = new St.BoxLayout({
        vertical: false,
        x_align: Clutter.ActorAlign.END,
        style: 'padding: 2px 8px;',
    });

    const inner = new St.BoxLayout({
        vertical: true,
        style: `
            background-color: rgba(30, 110, 230, 0.88);
            border-radius: 16px 16px 4px 16px;
            padding: 9px 13px;
            max-width: 300px;
        `,
    });

    const label = _makeLabel(GLib.markup_escape_text(text, -1), opts);
    label.style += ' color: #ffffff;';

    inner.add_child(label);
    inner.add_child(_timestamp());
    outer.add_child(inner);

    // Fade-in
    outer.opacity = 0;
    GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
        outer.ease({ opacity: 255, duration: 200, mode: Clutter.AnimationMode.EASE_OUT_QUAD });
        return GLib.SOURCE_REMOVE;
    });

    return outer;
}

/**
 * Assistant message bubble — left-aligned with markdown support.
 * Returns { actor, appendText(str), setText(str), finalize() }
 */
export function AssistantBubble(initialText = '', opts = {}) {
    const outer = new St.BoxLayout({
        vertical: false,
        x_align: Clutter.ActorAlign.START,
        style: 'padding: 2px 8px;',
    });

    const inner = new St.BoxLayout({
        vertical: true,
        style: `
            background-color: rgba(38, 38, 62, 0.92);
            border-radius: 16px 16px 16px 4px;
            padding: 9px 13px;
            max-width: 320px;
        `,
    });

    const label = _makeLabel('', opts);
    label.style += ' color: #dde0f8;';
    _setSafeMarkup(label, markdownToPango(initialText) || '<i><span foreground="#666">…</span></i>', initialText);

    // Copy button
    const copyBtn = new St.Button({
        style_class: 'message-copy-button',
        child: new St.Icon({
            icon_name: 'edit-copy-symbolic',
            icon_size: 14,
        }),
        x_align: Clutter.ActorAlign.END,
    });

    let _rawText = initialText;

    copyBtn.connect('clicked', () => {
        St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, _rawText);
        // Visual feedback
        const oldIcon = copyBtn.child.icon_name;
        copyBtn.child.icon_name = 'emblem-ok-symbolic';
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
            copyBtn.child.icon_name = oldIcon;
            return GLib.SOURCE_REMOVE;
        });
    });

    inner.add_child(label);
    inner.add_child(copyBtn);
    inner.add_child(_timestamp());
    outer.add_child(inner);

    outer.opacity = 0;
    GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
        outer.ease({ opacity: 255, duration: 200, mode: Clutter.AnimationMode.EASE_OUT_QUAD });
        return GLib.SOURCE_REMOVE;
    });

    let _accumulated = initialText;

    return {
        actor: outer,
        appendText(chunk) {
            _accumulated += chunk;
            _rawText = _accumulated;
            _setSafeMarkup(label, markdownToPango(_accumulated), _accumulated);
        },
        setText(text) {
            _rawText = text;
            _accumulated = text;
            _setSafeMarkup(label, markdownToPango(text), text);
        },
        finalize() {
            // Re-render final text with full markdown pass
            _setSafeMarkup(label, markdownToPango(_accumulated), _accumulated);
        },
    };
}

/** Animated typing indicator — three bouncing dots. */
export function TypingIndicator() {
    const outer = new St.BoxLayout({
        x_align: Clutter.ActorAlign.START,
        style: 'padding: 2px 8px;',
    });
    const bubble = new St.BoxLayout({
        style: `
            background-color: rgba(38,38,62,0.85);
            border-radius: 16px;
            padding: 10px 16px;
            spacing: 4px;
        `,
    });

    const dots = [0, 1, 2].map(i => {
        const dot = new St.Label({
            text: '●',
            style: 'color: rgba(100,120,200,0.6); font-size: 10px;',
        });
        // Staggered bounce animation
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, i * 200, () => {
            dot.ease({
                opacity: 255,
                duration: 400,
                mode: Clutter.AnimationMode.EASE_IN_OUT_SINE,
                onComplete: () => {
                    dot.ease({ opacity: 80, duration: 400, mode: Clutter.AnimationMode.EASE_IN_OUT_SINE });
                },
            });
            return GLib.SOURCE_REMOVE;
        });
        bubble.add_child(dot);
        return dot;
    });

    outer.add_child(bubble);
    return outer;
}

/** Tool call status chip. */
export function ToolCallBubble(toolName) {
    const outer = new St.BoxLayout({
        x_align: Clutter.ActorAlign.START,
        style: 'padding: 1px 8px;',
    });

    const chip = new St.BoxLayout({
        style: `
            background-color: rgba(20, 70, 50, 0.80);
            border: 1px solid rgba(40,140,80,0.35);
            border-radius: 8px;
            padding: 4px 10px;
            spacing: 6px;
        `,
    });

    const spinnerLabel = new St.Label({ text: '⚙', style: 'color: #50d090; font-size: 11px;' });
    const nameLabel = new St.Label({ text: toolName, style: 'color: #90d8b0; font-size: 11px;' });
    const statusLabel = new St.Label({ text: 'running…', style: 'color: #60b880; font-size: 10px;' });

    chip.add_child(spinnerLabel);
    chip.add_child(nameLabel);
    chip.add_child(statusLabel);
    outer.add_child(chip);

    // Rotate the spinner glyph
    let _frame = 0;
    const FRAMES = ['⚙', '◌', '○', '◉'];
    const _timerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
        spinnerLabel.text = FRAMES[_frame++ % FRAMES.length];
        return GLib.SOURCE_CONTINUE;
    });

    return {
        actor: outer,
        setDone() {
            GLib.source_remove(_timerId);
            spinnerLabel.text = '✓';
            spinnerLabel.style = 'color: #50d090; font-size: 11px;';
            statusLabel.text = 'done';
            chip.style = chip.style.replace('rgba(20, 70, 50, 0.80)', 'rgba(20,50,70,0.78)');
        },
        setError(msg) {
            GLib.source_remove(_timerId);
            spinnerLabel.text = '✗';
            spinnerLabel.style = 'color: #e06060; font-size: 11px;';
            statusLabel.text = msg || 'error';
            chip.style = chip.style.replace('rgba(20, 70, 50, 0.80)', 'rgba(80,20,20,0.78)');
        },
    };
}

/** System / hint / error notice. */
export function SystemBubble(text, isError = false) {
    const color = isError ? 'rgba(180,30,30,0.15)' : 'rgba(50,50,70,0.5)';
    const tcolor = isError ? '#f08080' : '#888';
    const outer = new St.BoxLayout({
        x_align: Clutter.ActorAlign.CENTER,
        style: 'padding: 2px 16px;',
    });
    const label = new St.Label({
        text,
        style: `
            color: ${tcolor};
            background-color: ${color};
            border-radius: 8px;
            padding: 4px 12px;
            font-size: 11px;
        `,
    });
    label.clutter_text.line_wrap = true;
    outer.add_child(label);
    return outer;
}
