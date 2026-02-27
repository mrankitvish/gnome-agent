"""MCP servers and tools API."""

import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(tags=["mcp"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class MCPServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    transport: str = Field(..., pattern="^(stdio|http)$")
    endpoint: str | None = Field(default=None, description="URL for HTTP transport")
    command: str | None = Field(default=None, description="Executable for stdio transport")
    args: list[str] = Field(default_factory=list)


class MCPServerResponse(BaseModel):
    name: str
    transport: str
    endpoint: str | None
    enabled: bool


class ToolResponse(BaseModel):
    name: str
    description: str


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/mcp/servers", response_model=list[MCPServerResponse])
async def list_mcp_servers(request: Request) -> list[dict]:
    """List all registered MCP servers."""
    mcp_router = request.app.state.mcp_router
    servers = []
    for name in mcp_router.server_names:
        cfg = mcp_router.get_server_config(name)
        servers.append(
            {
                "name": name,
                "transport": cfg.get("transport", "unknown"),
                "endpoint": cfg.get("url") or cfg.get("command"),
                "enabled": True,
            }
        )
    return servers


@router.post("/mcp/servers", status_code=201)
async def register_mcp_server(body: MCPServerCreate, request: Request) -> dict:
    """Register a new external MCP server and refresh tools."""
    mcp_router = request.app.state.mcp_router
    tool_registry = request.app.state.tool_registry

    try:
        mcp_router.register_server(
            body.name,
            transport=body.transport,
            endpoint=body.endpoint,
            command=body.command,
            args=body.args or [],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Restart the MCP client to pick up new server
    await mcp_router.stop()
    await mcp_router.start()
    tools = await mcp_router.get_tools()
    tool_registry.clear()
    tool_registry.register_tools(tools)

    # Invalidate all cached agents so they pick up the new tools
    request.app.state.agent_builder._cache.clear()

    logger.info("Registered and connected to MCP server: %s", body.name)
    return {"status": "registered", "name": body.name, "tools_count": tool_registry.count}


@router.get("/tools", response_model=list[ToolResponse])
async def list_tools(request: Request) -> list[dict]:
    """List all tools across all connected MCP servers."""
    tool_registry = request.app.state.tool_registry
    return tool_registry.list_tools()
