"""SQLite schema definitions and table creation."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS app_config (
    id INTEGER PRIMARY KEY CHECK (id = 1), -- Single row table
    provider TEXT NOT NULL DEFAULT 'ollama',
    model TEXT NOT NULL DEFAULT 'llama3:latest',
    base_url TEXT DEFAULT 'http://localhost:11434',
    api_key TEXT,
    system_prompt TEXT NOT NULL DEFAULT 'You are a helpful AI assistant with access to desktop tools.',
    temperature REAL NOT NULL DEFAULT 0.7,
    max_iterations INTEGER NOT NULL DEFAULT 6,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mcp_servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    transport TEXT NOT NULL CHECK(transport IN ('stdio', 'http')),
    endpoint TEXT NOT NULL,
    command TEXT,
    args TEXT,
    enabled BOOLEAN NOT NULL DEFAULT 1,
    builtin BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS permissions (
    tool_name TEXT PRIMARY KEY,
    policy TEXT NOT NULL CHECK(policy IN ('always_allow', 'ask_every_time', 'deny'))
        DEFAULT 'ask_every_time'
);

CREATE TABLE IF NOT EXISTS tool_logs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT,
    result TEXT,
    approved BOOLEAN,
    latency_ms INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Index for fast message lookups by session
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

-- Index for tool log lookups
CREATE INDEX IF NOT EXISTS idx_tool_logs_session ON tool_logs(session_id, created_at);
"""

# Default config — seeded on first startup if row doesn't exist
DEFAULT_CONFIG_SQL = """
INSERT OR IGNORE INTO app_config (id, provider, model, base_url, api_key, system_prompt, temperature, max_iterations)
VALUES (
    1,
    '{provider}',
    '{model}',
    '{base_url}',
    '{api_key}',
    'You are a helpful AI assistant with access to desktop and system tools. Use the available tools to help the user with tasks on their GNOME desktop. Always explain what you are doing before executing tools.',
    0.7,
    6
);
"""
