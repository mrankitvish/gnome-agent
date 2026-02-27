"""MCP client — wraps MultiServerMCPClient for server management."""

import logging
import sys
from pathlib import Path
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

# Paths to built-in MCP server scripts
_BUILTINS_DIR = Path(__file__).parent / "builtins"
_BUILTIN_SYSTEM_PATH = str(_BUILTINS_DIR / "system.py")
_BUILTIN_FILESYSTEM_PATH = str(_BUILTINS_DIR / "filesystem.py")
_BUILTIN_DESKTOP_PATH = str(_BUILTINS_DIR / "desktop.py")


class MCPRouter:
    """Routes tool calls to registered MCP servers.

    Wraps LangChain's MultiServerMCPClient to manage both built-in
    and external MCP server connections.
    """

    def __init__(self) -> None:
        self._server_configs: dict[str, dict[str, Any]] = {}
        self._client: MultiServerMCPClient | None = None

    def register_builtin_servers(self) -> None:
        """Register all built-in MCP servers."""
        builtin_scripts = {
            "system": _BUILTIN_SYSTEM_PATH,
            "filesystem": _BUILTIN_FILESYSTEM_PATH,
            "desktop": _BUILTIN_DESKTOP_PATH,
        }
        for name, script_path in builtin_scripts.items():
            self._server_configs[name] = {
                "transport": "stdio",
                "command": sys.executable,
                "args": [script_path],
            }
            logger.info("Registered built-in MCP server: %s", name)

    def register_server(
        self,
        name: str,
        *,
        transport: str,
        endpoint: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
    ) -> None:
        """Register an external MCP server.

        Args:
            name: Unique server name (used as tool namespace).
            transport: 'stdio' or 'http'.
            endpoint: URL for http transport.
            command: Executable for stdio transport.
            args: Arguments for stdio transport.
        """
        if transport == "http":
            if not endpoint:
                raise ValueError("HTTP transport requires 'endpoint' URL")
            self._server_configs[name] = {
                "transport": "http",
                "url": endpoint,
            }
        elif transport == "stdio":
            if not command:
                raise ValueError("stdio transport requires 'command'")
            config: dict[str, Any] = {
                "transport": "stdio",
                "command": command,
            }
            if args:
                config["args"] = args
            self._server_configs[name] = config
        else:
            raise ValueError(f"Unsupported transport: {transport}")

        logger.info("Registered external MCP server: %s (%s)", name, transport)

    async def start(self) -> None:
        """Initialize the MultiServerMCPClient with all registered servers."""
        if not self._server_configs:
            logger.warning("No MCP servers registered, starting with empty config")
            self._server_configs = {}

        self._client = MultiServerMCPClient(self._server_configs)
        logger.info(
            "MCP client started with %d server(s): %s",
            len(self._server_configs),
            list(self._server_configs.keys()),
        )

    async def get_tools(self) -> list:
        """Get all tools from all connected MCP servers as LangChain Tool objects."""
        if self._client is None:
            raise RuntimeError("MCP client not started — call start() first")
        tools = await self._client.get_tools()
        logger.info("Loaded %d tools from MCP servers", len(tools))
        return tools

    async def stop(self) -> None:
        """Clean up MCP client connections."""
        self._client = None
        logger.info("MCP client stopped")

    @property
    def server_names(self) -> list[str]:
        """List registered server names."""
        return list(self._server_configs.keys())

    def get_server_config(self, name: str) -> dict[str, Any] | None:
        """Get config for a specific server."""
        return self._server_configs.get(name)
