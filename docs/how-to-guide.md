# 📖 How-To Guide

> Practical recipes and usage patterns for every **Gnome Agent** feature.

---

## Table of Contents

1. [Opening the Chat Panel](#1-opening-the-chat-panel)
2. [Sending a Message](#2-sending-a-message)
3. [Using the Global Hotkey](#3-using-the-global-hotkey)
4. [Resizing the Chat Window](#4-resizing-the-chat-window)
5. [Browsing Chat History](#5-browsing-chat-history)
6. [Switching LLM Provider](#6-switching-llm-provider)
7. [Using MCP Tools](#7-using-mcp-tools)
8. [Adding a Custom MCP Server](#8-adding-a-custom-mcp-server)
9. [Desktop Context Injection](#9-desktop-context-injection)
10. [Using the REST API Directly](#10-using-the-rest-api-directly)
11. [Checking Provider Capabilities](#11-checking-provider-capabilities)

---

## 1. Opening the Chat Panel

Click the **✦** icon in your GNOME top bar.

The panel slides in from the top-right with a smooth animation. Click it again (or press `Esc`) to close.

---

## 2. Sending a Message

- Type in the input box at the bottom of the panel
- Press **Enter** to send
- Press **Shift+Enter** to insert a newline without sending
- The assistant responds with real-time streaming (tokens appear as they are generated)

**Tool calls** are displayed as expandable cards between messages, showing the tool name, arguments, and result.

---

## 3. Using the Global Hotkey

Press **`Super + Space`** from anywhere on your desktop to instantly toggle the chat panel — even while another app is in focus.

### Changing the Hotkey

The hotkey is stored in GSettings. To change it:

```bash
gsettings set org.gnome.shell.extensions.gnome-agent global-shortcut "['<Super>a']"
```

Or update the default in `extension/schemas/org.gnome.shell.extensions.gnome-agent.gschema.xml` and reinstall.

---

## 4. Resizing the Chat Window

Drag the **resize handle** in the bottom-right corner of the chat panel. Your preferred size is automatically saved and restored between sessions.

To reset to the default size:

```bash
gsettings reset org.gnome.shell.extensions.gnome-agent window-width
gsettings reset org.gnome.shell.extensions.gnome-agent window-height
```

---

## 5. Browsing Chat History

1. Click the **🕐 clock icon** in the top-right of the chat header
2. The history overlay slides in, listing all past conversation sessions by date
3. Click any session to **resume it** — the full message history is restored and the agent has context of all prior messages in that session
4. Click **Close** (or the ✕ button) to return to the current chat

---

## 6. Switching LLM Provider

### Via the Preferences UI (recommended)

1. Open the extension preferences → **LLM Config** tab
2. Select a provider from the dropdown
3. Enter the model name
4. Enter your API key (leave blank for Ollama)
5. Optionally adjust the system prompt
6. Click **Save Configuration**

Changes take effect immediately on the next chat message.

### Via the API

```bash
curl -X PUT http://localhost:8000/config/llm \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openai",
    "model": "gpt-4o-mini",
    "api_key": "sk-...",
    "system_prompt": "You are a helpful GNOME desktop assistant.",
    "temperature": 0.7,
    "max_iterations": 6
  }'
```

---

## 7. Using MCP Tools

When built-in MCP servers are enabled (`GNOME_AGENT_ENABLE_BUILTIN_SERVERS=true`), the AI can use desktop tools automatically. Just ask naturally:

> *"What processes are using the most CPU right now?"*
> *"Search my home directory for Python files modified this week"*
> *"What are the latest system errors in the journal?"*
> *"Open Firefox"*

The tool call and result are shown inline in the chat bubble.

### Check Available Tools

```bash
curl http://localhost:8000/tools | jq '.[] | .name'
```

---

## 8. Adding a Custom MCP Server

You can register any [MCP-compatible](https://modelcontextprotocol.io) server.

### Via the Preferences UI

1. Open Preferences → **MCP Servers** tab
2. Click **+ Add Server**
3. Fill in: Name, Transport (`stdio` or `http`), Command / Endpoint
4. Click **Save** — the server is registered and tools are loaded automatically

### Via the API

#### stdio (subprocess) server

```bash
curl -X POST http://localhost:8000/mcp/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-cli-tool",
    "transport": "stdio",
    "endpoint": "my-mcp-server",
    "command": "/path/to/my-mcp-server",
    "args": ["--flag"]
  }'
```

#### HTTP server

```bash
curl -X POST http://localhost:8000/mcp/servers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "remote-tools",
    "transport": "http",
    "endpoint": "http://192.168.1.100:8080/mcp"
  }'
```

---

## 9. Desktop Context Injection

The extension can automatically inject information about your current desktop state into every message. Configure this in Preferences → **Connection**:

| Toggle | What it injects |
|---|---|
| Active App | Name of the currently focused application |
| Window Title | Title of the focused window |
| Clipboard | Content of the clipboard (first 500 chars) |

This allows the AI to give context-aware answers like:
> *"I see you're using VS Code. Do you need help with your current file?"*

---

## 10. Using the REST API Directly

All functionality is available via the REST API for scripting or integration.

### Stream a Chat Message

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "List top 5 CPU processes",
    "session_id": null
  }'
```

**SSE Events:**

| Event | Payload |
|---|---|
| `session` | `{"session_id": "..."}` |
| `tool_call` | `{"tool_name": "...", "arguments": {...}}` |
| `tool_result` | `{"tool_name": "...", "result": "..."}` |
| `message` | `{"text": "..."}` (streaming token) |
| `final_answer` | `{"text": "...", "session_id": "..."}` |
| `error` | `{"detail": "..."}` |

### Resume a Session

Pass the `session_id` from a previous response:

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What did I just ask you?",
    "session_id": "your-session-uuid"
  }'
```

### List All Sessions

```bash
curl http://localhost:8000/sessions | jq
```

### Get Messages in a Session

```bash
curl http://localhost:8000/sessions/{session_id}/messages | jq
```

---

## 11. Checking Provider Capabilities

Not all LLM models support tool calling or structured output. Check the current configuration:

```bash
curl http://localhost:8000/config/llm | jq '{provider, model, supports_tools, supports_structured_output}'
```

**Example response:**
```json
{
  "provider": "ollama",
  "model": "llama3",
  "supports_tools": true,
  "supports_structured_output": true
}
```

> ⚠️ **Important:** MCP tools **require** `supports_tools: true`. If your model doesn't support tool calling, the agent won't be able to use any desktop tools. Use a model with tool support (e.g., `llama3`, `mistral`, `gpt-4o-mini`, `claude-3-5-haiku`).

### List All Supported Providers

```bash
curl http://localhost:8000/config/providers | jq
```
