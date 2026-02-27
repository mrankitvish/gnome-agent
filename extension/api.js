/**
 * api.js — FastAPI + SSE client for the Gnome Agent runtime.
 *
 * Uses GLib/Gio for async network I/O since Soup3 in GJS requires careful
 * thread handling. All calls are non-blocking via GLib MainLoop.
 */

import Soup from 'gi://Soup?version=3.0';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';

/** Default base URL for the gnome-agent runtime. */
const DEFAULT_BASE_URL = 'http://127.0.0.1:8000';

/**
 * GnomeAgentAPI — thin wrapper around the FastAPI backend.
 *
 * Usage:
 *   const api = new GnomeAgentAPI({ baseUrl, apiKey });
 *   api.chat({ message, context, onEvent, onDone, onError });
 */
export class GnomeAgentAPI {
    constructor({ baseUrl = DEFAULT_BASE_URL, apiKey = '' } = {}) {
        this._baseUrl = baseUrl.replace(/\/$/, '');
        this._apiKey = apiKey;
        this._session = new Soup.Session();
        this._session.timeout = 0; // No timeout for streaming
    }

    /** Build common request headers. */
    _headers() {
        const hdrs = { 'Content-Type': 'application/json', Accept: 'text/event-stream' };
        if (this._apiKey) hdrs['Authorization'] = `Bearer ${this._apiKey}`;
        return hdrs;
    }

    /**
     * Check runtime health.
     * @returns {Promise<object>} Health response JSON.
     */
    async health() {
        return this._getJson('/health');
    }

    /**
     * List available agents.
     * @returns {Promise<object[]>}
     */
    async listAgents() {
        return this._getJson('/agents');
    }

    /**
     * Send a chat message and stream SSE events.
     *
     * @param {object} opts
     * @param {string}   opts.message          User message text.
     * @param {string}   [opts.agentId]        Agent ID (default: 'default').
     * @param {string}   [opts.sessionId]      Existing session ID to continue.
     * @param {object}   [opts.context]        Desktop context { active_app, current_path, clipboard }.
     * @param {Function} opts.onEvent          Called with (eventType, parsedData) for each SSE event.
     * @param {Function} [opts.onDone]         Called when stream ends.
     * @param {Function} [opts.onError]        Called with (errorMessage) on failure.
     * @returns {Function} cancel()  — call to abort the stream.
     */
    chat({ message, agentId = 'default', sessionId = null, context = {}, onEvent, onDone, onError }) {
        const body = JSON.stringify({
            message,
            agent_id: agentId,
            session_id: sessionId,
            context,
        });

        const msg = new Soup.Message({ method: 'POST', uri: GLib.Uri.parse(`${this._baseUrl}/chat`, GLib.UriFlags.NONE) });
        msg.set_request_body_from_bytes('application/json', new GLib.Bytes(new TextEncoder().encode(body)));

        const hdrs = this._headers();
        for (const [k, v] of Object.entries(hdrs)) {
            msg.request_headers.append(k, v);
        }

        let cancelled = false;
        let buffer = '';

        // Send and get the response stream
        this._session.send_async(msg, GLib.PRIORITY_DEFAULT, null, (session, result) => {
            try {
                const inputStream = session.send_finish(result);
                const dataStream = new Gio.DataInputStream({ base_stream: inputStream });

                const readNextLine = () => {
                    if (cancelled) return;
                    dataStream.read_line_async(GLib.PRIORITY_DEFAULT, null, (stream, lineResult) => {
                        if (cancelled) return;
                        try {
                            const [lineBytes] = stream.read_line_finish(lineResult);
                            if (lineBytes === null) {
                                // Stream ended
                                onDone?.();
                                return;
                            }
                            const line = new TextDecoder().decode(lineBytes);
                            this._parseSseLine(line, onEvent);
                            readNextLine();
                        } catch (e) {
                            if (!cancelled) onError?.(`Read error: ${e.message}`);
                        }
                    });
                };
                readNextLine();
            } catch (e) {
                if (!cancelled) onError?.(`Connection error: ${e.message}`);
            }
        });

        return () => { cancelled = true; };
    }

    /**
     * Parse a single SSE line and fire onEvent.
     * SSE format:
     *   event: <type>
     *   data: <json>
     *   (blank line = end of event)
     */
    _parseSseLine(line, onEvent) {
        if (!onEvent) return;
        // We accumulate event + data as properties of a static object between calls
        // For simplicity, parse minimally:
        if (line.startsWith('event: ')) {
            this._sseEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
            const raw = line.slice(6).trim();
            try {
                const data = JSON.parse(raw);
                onEvent(this._sseEvent || 'message', data);
            } catch {
                onEvent(this._sseEvent || 'message', { text: raw });
            }
            this._sseEvent = null;
        }
        // blank lines / comments are ignored
    }

    /** Internal GET → JSON helper. */
    async _getJson(path) {
        return new Promise((resolve, reject) => {
            const msg = new Soup.Message({ method: 'GET', uri: GLib.Uri.parse(`${this._baseUrl}${path}`, GLib.UriFlags.NONE) });
            for (const [k, v] of Object.entries(this._headers())) {
                msg.request_headers.append(k, v);
            }
            this._session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, null, (session, result) => {
                try {
                    const bytes = session.send_and_read_finish(result);
                    const text = new TextDecoder().decode(bytes.get_data());
                    resolve(JSON.parse(text));
                } catch (e) {
                    reject(e);
                }
            });
        });
    }

    destroy() {
        this._session.abort();
    }
}
