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
from app.api import health, agents, mcp, chat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of long-lived resources."""
    logger.info("Starting Gnome Agent Runtime v0.1.0")

    # ── Database ──────────────────────────────────────────────────────────────
    await init_db()

    # ── MCP client and tool registry ─────────────────────────────────────────
    mcp_router = MCPRouter()
    mcp_router.register_builtin_servers()
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
    agent_builder = AgentBuilder(tool_registry)

    # ── Attach to app state (available in request.app.state) ─────────────────
    app.state.db_get = get_db
    app.state.mcp_router = mcp_router
    app.state.tool_registry = tool_registry
    app.state.session_manager = session_manager
    app.state.permission_manager = permission_manager
    app.state.agent_builder = agent_builder

    logger.info(
        "Runtime ready — %d tool(s) across %d MCP server(s)",
        tool_registry.count,
        len(mcp_router.server_names),
    )
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down Gnome Agent Runtime")
    await mcp_router.stop()


# ── Application factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Gnome Agent Runtime",
        description=(
            "Local-first AI agent runtime with MCP support, LangGraph execution engine, "
            "and SSE streaming. GNOME extension is the primary client."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — allow GNOME extension (and local dev tools) to connect
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(agents.router)
    app.include_router(mcp.router)
    app.include_router(chat.router)

    return app


app = create_app()
