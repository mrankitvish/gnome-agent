# ⚙️ Setup Guide

> Complete installation and configuration guide for **Gnome Agent**.

---

## Prerequisites

| Requirement | Minimum Version | Notes |
|---|---|---|
| Linux + GNOME Shell | 45+ | Wayland and X11 supported |
| Python | 3.11+ | Virtual environments recommended |
| pip | 23+ | Comes with Python |
| LLM Backend | — | Ollama (local), or cloud API key |

---

## 1 — Clone the Repository

```bash
git clone https://github.com/youruser/gnome-agent.git
cd gnome-agent
```

---

## 2 — Python Backend Setup

### 2.1 Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate
```

### 2.2 Install Dependencies

```bash
pip install -e .
```

This installs:
- `fastapi`, `uvicorn` — API server
- `langchain`, `langgraph` — AI orchestration
- `langchain-ollama`, `langchain-openai`, `langchain-anthropic`, `langchain-google-genai`, `langchain-mistralai` — LLM providers
- `aiosqlite` — Async SQLite
- `sse-starlette` — Server-Sent Events
- `fastmcp` — MCP tool server framework

---

## 3 — Configure the Backend

### 3.1 Copy the example environment file

```bash
cp .env.example .env
```

### 3.2 Edit `.env`

Open `.env` in your editor and set the defaults. The most important settings are:

```bash
# Default provider and model (used on first startup to seed the database)
GNOME_AGENT_DEFAULT_LLM_PROVIDER=ollama
GNOME_AGENT_DEFAULT_LLM_MODEL=llama3

# For Ollama (running locally)
GNOME_AGENT_OLLAMA_BASE_URL=http://localhost:11434

# Database location
GNOME_AGENT_DATABASE_PATH=gnome_agent.db
```

> **Note:** After the first startup, LLM settings are stored in the `app_config` database table and managed through the extension's preferences UI. The `.env` values are only used to seed the initial defaults.

### 3.3 Provider-Specific Setup

#### Ollama (Recommended for local use)

1. Install Ollama: https://ollama.com
2. Pull a model:
   ```bash
   ollama pull llama3
   # or for tool calling support:
   ollama pull mistral
   ```
3. Set in `.env`:
   ```bash
   GNOME_AGENT_DEFAULT_LLM_PROVIDER=ollama
   GNOME_AGENT_DEFAULT_LLM_MODEL=llama3
   ```

#### OpenAI

```bash
GNOME_AGENT_DEFAULT_LLM_PROVIDER=openai
GNOME_AGENT_DEFAULT_LLM_MODEL=gpt-4o-mini
# Set your API key in the extension preferences UI after setup
```

#### Anthropic

```bash
GNOME_AGENT_DEFAULT_LLM_PROVIDER=anthropic
GNOME_AGENT_DEFAULT_LLM_MODEL=claude-3-5-haiku-20241022
```

#### Google Gemini

```bash
GNOME_AGENT_DEFAULT_LLM_PROVIDER=google_genai
GNOME_AGENT_DEFAULT_LLM_MODEL=gemini-2.0-flash
```

#### OpenAI-Compatible (LM Studio, vLLM, Jan, etc.)

```bash
GNOME_AGENT_DEFAULT_LLM_PROVIDER=openai_compatible
GNOME_AGENT_DEFAULT_LLM_MODEL=mistral
GNOME_AGENT_OPENAI_COMPATIBLE_BASE_URL=http://localhost:1234/v1
GNOME_AGENT_OPENAI_COMPATIBLE_API_KEY=not-needed
```

---

## 4 — Start the Backend Server

### Manual (development)

```bash
source venv/bin/activate
uvicorn app.main:app --reload
```

Server starts at `http://127.0.0.1:8000`.

Verify it's running:
```bash
curl http://localhost:8000/health
```

### Systemd Service (recommended for production)

Install as a user-level service so it starts automatically at login:

```bash
# Copy the service file
cp gnome-agent.service ~/.config/systemd/user/

# Edit the path in the file to match your installation
nano ~/.config/systemd/user/gnome-agent.service

# Enable and start
systemctl --user daemon-reload
systemctl --user enable gnome-agent.service
systemctl --user start gnome-agent.service

# Check status
systemctl --user status gnome-agent.service
```

View live logs:
```bash
journalctl --user -u gnome-agent.service -f
```

---

## 5 — Install the GNOME Extension

```bash
bash extension/install.sh
```

This script:
1. Compiles the GSettings schema
2. Copies files to `~/.local/share/gnome-shell/extensions/gnome-agent@localhost`
3. Enables the extension

### Restart GNOME Shell

- **X11**: Press `Alt+F2`, type `r`, press `Enter`
- **Wayland**: Log out and log back in

---

## 6 — Configure the Extension

Open GNOME Extensions app and click the settings (⚙️) icon next to **Gnome Agent**, or run:

```bash
gnome-extensions prefs gnome-agent@localhost
```

### Tabs Overview

| Tab | Description |
|---|---|
| **Status** | Runtime health, connection test |
| **LLM Config** | Provider, model, API key, system prompt |
| **MCP Servers** | Add/remove external MCP tool servers |
| **Tools** | View available tools from all MCP servers |
| **Connection** | Server URL, API key, context injection toggles |
| **Appearance** | Font size, opacity, margin |

### Recommended: Set your LLM in the UI

1. Open Preferences → **LLM Config**
2. Select your provider from the dropdown
3. Enter your model name (e.g., `llama3`, `gpt-4o`, `claude-3-5-haiku-20241022`)
4. Paste your API key (if required)
5. Click **Save Configuration**

---

## 7 — Optional: Enable Built-in MCP Servers

Built-in MCP servers give the AI access to system tools. Enable them in `.env`:

```bash
GNOME_AGENT_ENABLE_BUILTIN_SERVERS=true
```

Then restart the server. The following tools become available:

| Server | Tools |
|---|---|
| **System** | `list_processes`, `disk_usage`, `journal_logs` |
| **Filesystem** | `read_file`, `search_files` |
| **Desktop** | `open_application`, `take_screenshot` |

---

## 8 — Security Notes

- The backend listens on `127.0.0.1` only by default — not exposed to the network
- Set `GNOME_AGENT_API_KEY` to enable Bearer token auth if needed
- API keys entered through the preferences UI are stored in the SQLite database — the DB file should have appropriate permissions (`chmod 600 gnome_agent.db`)

---

## Troubleshooting

### Extension shows "Offline"
- Check that the backend server is running: `curl http://localhost:8000/health`
- Check the server URL in preferences (default: `http://127.0.0.1:8000`)

### Extension won't open on click
- Check GNOME Shell logs: `journalctl /usr/bin/gnome-shell -n 50 --no-pager`
- Try restarting the shell after reinstalling the extension

### LLM returns no response
- Ensure the model supports tool calling if MCP servers are enabled
- Check GET `/config/llm` response for `supports_tools: true`

### Chat doesn't remember previous messages
- Ensure the backend was restarted after the latest update
- Check that the session ID is being passed correctly in chat requests
