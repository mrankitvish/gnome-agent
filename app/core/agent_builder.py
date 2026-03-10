"""Agent graph builder — creates LangChain/LangGraph agents with guardrails."""

import logging
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

from app.config import settings
from app.core.llm_factory import get_llm

logger = logging.getLogger(__name__)


def build_agent(
    *,
    llm,
    tools: list,
    system_prompt: str,
    checkpointer: Any,
    max_iterations: int = 6,
    max_tool_calls: int = 10,
) -> Any:
    """Build a LangGraph-powered agent with middleware guardrails.

    Args:
        llm: LangChain chat model instance.
        tools: List of LangChain Tool objects.
        system_prompt: System prompt for the agent.
        checkpointer: LangGraph checkpointer (SQLite or InMemory).
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
        checkpointer=checkpointer,
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

    def __init__(self, tool_registry, checkpointer: Any) -> None:
        self._registry = tool_registry
        self._checkpointer = checkpointer
        self._cache: dict[str, Any] = {}

    def build(
        self,
        *,
        provider: str,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        system_prompt: str,
        temperature: float = 0.7,
        max_iterations: int | None = None,
    ) -> Any:
        """Create or retrieve a cached agent instance based on current global config.

        Args:
            provider: LLM provider name.
            model: Model name.
            base_url: Optional API base url.
            api_key: Optional API key.
            system_prompt: Agent system prompt.
            temperature: Sampling temperature.
            max_iterations: Max LLM loop iterations (defaults to settings).

        Returns:
            A compiled LangGraph agent.
        """
        # Cache key based on all parameters so if config updates, a new graph is built.
        cache_key = f"{provider}:{model}:{base_url}:{api_key}:{system_prompt}:{temperature}:{max_iterations}"
        
        if cache_key in self._cache:
            logger.debug("Returning cached agent for current config")
            return self._cache[cache_key]

        llm = get_llm(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature
        )
        tools = self._registry.get_all()
        iterations = max_iterations or settings.max_iterations

        agent = build_agent(
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            checkpointer=self._checkpointer,
            max_iterations=iterations,
            max_tool_calls=settings.max_tool_calls,
        )
        self._cache[cache_key] = agent
        logger.info("Compiled new agent graph for provider=%s model=%s", provider, model)
        return agent

    def invalidate_all(self) -> None:
        """Clear the cache."""
        self._cache.clear()
