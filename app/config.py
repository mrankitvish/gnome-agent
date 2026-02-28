"""Central configuration for Gnome Agent Runtime."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings, loaded from environment variables."""

    # ── Database ──────────────────────────────────────────────────────
    database_path: str = "gnome_agent.db"

    # ── LLM Defaults ─────────────────────────────────────────────────
    default_llm_provider: str = "ollama"
    default_llm_model: str = "llama3.2"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # OpenAI
    openai_api_key: str = ""

    # OpenAI-compatible (LM Studio, vLLM, Jan, Ollama /v1, etc.)
    openai_compatible_base_url: str = ""   # e.g. http://localhost:1234/v1
    openai_compatible_api_key: str = ""    # optional; many local servers accept anything

    # ── Agent Guardrails ─────────────────────────────────────────────
    max_iterations: int = 6
    max_tool_calls: int = 10
    tool_timeout_seconds: int = 30

    # ── Server ───────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["*"]
    enable_builtin_servers: bool = False

    # ── Auth & Rate Limiting ──────────────────────────────────────────
    api_key: str = ""             # Bearer token; empty = auth disabled
    rate_limit_rpm: int = 0       # Requests/minute per IP; 0 = disabled

    model_config = {"env_prefix": "GNOME_AGENT_", "env_file": ".env"}


settings = Settings()
