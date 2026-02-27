"""Agent graph builder — creates LangChain/LangGraph agents with guardrails."""

import logging
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langgraph.checkpoint.memory import InMemorySaver

from app.config import settings
from app.core.llm_factory import get_llm

logger = logging.getLogger(__name__)

# Shared in-memory checkpointer for session continuity within a process lifetime.
# Phase 2 will swap this for a SQLite-backed checkpointer for true persistence.
_checkpointer = InMemorySaver()


def build_agent(
    *,
    llm,
    tools: list,
    system_prompt: str,
    max_iterations: int = 6,
    max_tool_calls: int = 10,
) -> Any:
    """Build a LangGraph-powered agent with middleware guardrails.

    Args:
        llm: LangChain chat model instance.
        tools: List of LangChain Tool objects.
        system_prompt: System prompt for the agent.
        max_iterations: Max LLM calls per run (ModelCallLimitMiddleware).
        max_tool_calls: Max tool calls per run (ToolCallLimitMiddleware).

    Returns:
        A compiled LangGraph agent (CompiledStateGraph).
    """
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=[
            ModelCallLimitMiddleware(run_limit=max_iterations, exit_behavior="end"),
            ToolCallLimitMiddleware(run_limit=max_tool_calls, exit_behavior="end"),
        ],
        checkpointer=_checkpointer,
    )
    logger.info(
        "Built agent with %d tools, max_iterations=%d, max_tool_calls=%d",
        len(tools),
        max_iterations,
        max_tool_calls,
    )
    return agent


class AgentBuilder:
    """Factory that creates and caches agent instances from DB profiles.

    One agent instance per agent_id is cached since LangGraph agents are
    stateless between invocations (state lives in the checkpointer/thread).
    """

    def __init__(self, tool_registry) -> None:
        self._registry = tool_registry
        self._cache: dict[str, Any] = {}

    def build(
        self,
        agent_id: str,
        *,
        provider: str,
        model: str,
        system_prompt: str,
        temperature: float = 0.7,
        max_iterations: int | None = None,
    ) -> Any:
        """Create or retrieve a cached agent instance.

        Args:
            agent_id: Unique agent identifier (used as cache key).
            provider: LLM provider name.
            model: Model name.
            system_prompt: Agent system prompt.
            temperature: Sampling temperature.
            max_iterations: Max LLM loop iterations (defaults to settings).

        Returns:
            A compiled LangGraph agent.
        """
        if agent_id in self._cache:
            logger.debug("Returning cached agent: %s", agent_id)
            return self._cache[agent_id]

        llm = get_llm(provider, model, temperature=temperature)
        tools = self._registry.get_all()
        iterations = max_iterations or settings.max_iterations

        agent = build_agent(
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            max_iterations=iterations,
            max_tool_calls=settings.max_tool_calls,
        )
        self._cache[agent_id] = agent
        logger.info("Cached new agent instance: %s (%s:%s)", agent_id, provider, model)
        return agent

    def invalidate(self, agent_id: str) -> None:
        """Remove a cached agent (e.g. after config update)."""
        self._cache.pop(agent_id, None)
