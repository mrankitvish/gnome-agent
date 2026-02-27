"""Health check endpoint — rich system status."""

import logging

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    """Return server health and runtime statistics."""
    try:
        tool_registry = request.app.state.tool_registry
        mcp_router = request.app.state.mcp_router
        db_get = request.app.state.db_get

        # Count agents in DB
        agent_count = 0
        session_count = 0
        async with db_get() as db:
            async with db.execute("SELECT COUNT(*) FROM agents") as cur:
                agent_count = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM sessions") as cur:
                session_count = (await cur.fetchone())[0]

        return {
            "status": "ok",
            "version": "0.3.0",
            "mcp_servers": mcp_router.server_names,
            "tools_loaded": tool_registry.count,
            "agents": agent_count,
            "sessions": session_count,
        }
    except Exception as e:
        logger.warning("Health check error: %s", e)
        return {"status": "ok", "version": "0.3.0"}
