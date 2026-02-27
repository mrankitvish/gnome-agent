# Gnome Agent Runtime

Local-first AI agent runtime using FastAPI, LangGraph, LangChain MCP, and SQLite.

## Quick Start

```bash
# Install dependencies (Python 3.11+)
pip install -e .

# Copy and configure settings
cp .env.example .env

# Start the runtime (Ollama must be running with a model loaded)
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Server health check |
| GET | `/agents` | List agent profiles |
| POST | `/agents` | Create agent profile |
| GET | `/agents/{id}` | Get agent profile |
| DELETE | `/agents/{id}` | Delete agent profile |
| POST | `/chat` | Stream chat response (SSE) |
| GET | `/mcp/servers` | List MCP servers |
| POST | `/mcp/servers` | Register external MCP server |
| GET | `/tools` | List all available tools |

## Chat SSE Events

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What processes are using the most CPU?"}'
```

Event types: `session`, `message`, `tool_call`, `tool_result`, `final_answer`, `error`

## Configuration

All settings use the `GNOME_AGENT_` prefix (see `.env.example`).

## Project Structure

```
app/
├── main.py              # FastAPI app + lifespan
├── config.py            # Settings (pydantic-settings)
├── api/                 # HTTP endpoints
│   ├── chat.py          # POST /chat (SSE streaming)
│   ├── agents.py        # Agent CRUD
│   ├── mcp.py           # MCP server management
│   └── health.py        # Health check
├── core/                # Agent engine
│   ├── agent_builder.py # LangGraph agent factory
│   ├── llm_factory.py   # LLM provider abstraction
│   ├── session_manager.py
│   └── permissions.py
├── mcp/                 # MCP integration
│   ├── client.py        # MCPRouter (MultiServerMCPClient)
│   ├── registry.py      # Tool registry
│   └── builtins/
│       └── system.py    # Built-in system MCP server
└── db/
    ├── database.py      # Async SQLite connection
    └── models.py        # Schema SQL
```
