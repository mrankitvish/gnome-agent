"""Tool registry — aggregates and manages tools from MCP servers."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for all available tools from MCP servers.

    Provides lookup, filtering, and listing capabilities.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}  # tool.name -> tool object

    def register_tools(self, tools: list) -> None:
        """Register a list of LangChain Tool objects.

        Args:
            tools: List of LangChain Tool objects from MCP servers.
        """
        for tool in tools:
            self._tools[tool.name] = tool
        logger.info("Registered %d tools in registry", len(tools))

    def get_tool(self, name: str) -> Any | None:
        """Look up a tool by its fully-qualified name."""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, str]]:
        """List all registered tools with name and description."""
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
            }
            for tool in self._tools.values()
        ]

    def get_all(self) -> list:
        """Get all registered tool objects."""
        return list(self._tools.values())

    @property
    def count(self) -> int:
        return len(self._tools)

    def clear(self) -> None:
        """Remove all registered tools."""
        self._tools.clear()
