"""FastAPI application entry point — lifespan, routers, and app-wide state."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import init_db, get_db
from app.mcp.client import MCPRouter
from app.mcp.registry import ToolRegistry
from app.core.session_manager import SessionManager
from app.core.agent_builder import AgentBuilder
from app.core.permissions import PermissionManager
from app.core.checkpointer import SQLiteCheckpointer
from app.core.middleware import AuthMiddleware, RateLimitMiddleware
from app.api import health, config, mcp, chat, sessions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _load_persisted_mcp_servers(mcp_router: MCPRouter, db_get) -> None:
    """Re-register external MCP servers stored in the DB from previous sessions."""
    async with db_get() as db:
        async with db.execute(
            "SELECT name, transport, endpoint, command, args FROM mcp_servers "
            "WHERE enabled = 1 AND builtin = 0"
        ) as cur:
            rows = await cur.fetchall()

    import json as _json
    for row in rows:
        try:
            args = _json.loads(row["args"]) if row["args"] else []
            mcp_router.register_server(
                row["name"],
                transport=row["transport"],
                endpoint=row["endpoint"],
                command=row["command"],
                args=args,
            )
            logger.info("Restored persisted MCP server: %s", row["name"])
        except Exception as e:
            logger.warning("Failed to restore MCP server '%s': %s", row["name"], e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of long-lived resources."""
    logger.info("Starting Gnome Agent Runtime v0.3.0")

    # ── Database ──────────────────────────────────────────────────────────────
    await init_db()

    # ── SQLite checkpointer ───────────────────────────────────────────────────
    checkpointer = SQLiteCheckpointer()
    await checkpointer.setup()

    # ── MCP client + tool registry ────────────────────────────────────────────
    mcp_router = MCPRouter()
    if settings.enable_builtin_servers:
        mcp_router.register_builtin_servers()

    # Restore externally-registered MCP servers from DB
    await _load_persisted_mcp_servers(mcp_router, get_db)

    await mcp_router.start()

    tool_registry = ToolRegistry()
    try:
        tools = await mcp_router.get_tools()
        tool_registry.register_tools(tools)
        logger.info("Loaded %d tools from MCP servers", tool_registry.count)
    except Exception as e:
        logger.warning("Failed to load MCP tools on startup: %s", e)

    # ── Core services ─────────────────────────────────────────────────────────
    session_manager = SessionManager(get_db)
    permission_manager = PermissionManager(get_db)
    agent_builder = AgentBuilder(tool_registry, checkpointer)

    # ── Attach to app state ───────────────────────────────────────────────────
    app.state.db_get = get_db
    app.state.mcp_router = mcp_router
    app.state.tool_registry = tool_registry
    app.state.session_manager = session_manager
    app.state.permission_manager = permission_manager
    app.state.agent_builder = agent_builder
    app.state.checkpointer = checkpointer

    logger.info(
        "Runtime ready — %d tool(s) across %d MCP server(s)",
        tool_registry.count,
        len(mcp_router.server_names),
    )
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down Gnome Agent Runtime")
    await mcp_router.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Gnome Agent Runtime",
        description=(
            "Local-first AI agent runtime with MCP support, LangGraph execution engine, "
            "and SSE streaming. GNOME extension is the primary client."
        ),
        version="0.3.0",
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost runs first) ─────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware, rpm=settings.rate_limit_rpm)
    app.add_middleware(AuthMiddleware)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(config.router)
    app.include_router(mcp.router)
    app.include_router(chat.router)
    app.include_router(sessions.router)

    return app


app = create_app()
