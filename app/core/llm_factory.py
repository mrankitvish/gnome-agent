"""LLM factory — provider-agnostic model instantiation via LangChain.

Supported providers:
  - ollama             Local Ollama server (http://localhost:11434)
  - openai             OpenAI API (api.openai.com)
  - openai_compatible  Any OpenAI-API-compatible server (LM Studio, vLLM, Jan, etc.)
"""

import logging
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    *,
    temperature: float = 0.7,
    streaming: bool = True,
    **kwargs: Any,
):
    """Create a LangChain chat model instance.

    Args:
        provider: One of 'ollama', 'openai', 'openai_compatible'.
                  Defaults to settings.default_llm_provider.
        model:    Model name (e.g. 'llama3.2', 'gpt-4o-mini', 'mistral').
                  Defaults to settings.default_llm_model.
        temperature: Sampling temperature.
        streaming:   Whether to enable streaming responses.
        **kwargs:    Extra kwargs forwarded to the model constructor.

    Returns:
        A LangChain BaseChatModel instance.
    """
    provider = provider or settings.default_llm_provider
    model = model or settings.default_llm_model

    logger.info(
        "Creating LLM: provider=%s model=%s temperature=%.2f streaming=%s",
        provider,
        model,
        temperature,
        streaming,
    )

    # ── OpenAI-compatible (LM Studio, vLLM, Ollama /v1, Jan, etc.) ───────────
    if provider == "openai_compatible":
        if not settings.openai_compatible_base_url:
            raise ValueError(
                "openai_compatible provider requires GNOME_AGENT_OPENAI_COMPATIBLE_BASE_URL to be set"
            )
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            base_url=settings.openai_compatible_base_url,
            api_key=settings.openai_compatible_api_key or "not-needed",
            **kwargs,
        )

    # ── Native Ollama ─────────────────────────────────────────────────────────
    if provider == "ollama":
        return init_chat_model(
            f"ollama:{model}",
            temperature=temperature,
            streaming=streaming,
            base_url=settings.ollama_base_url,
            **kwargs,
        )

    # ── OpenAI ────────────────────────────────────────────────────────────────
    if provider == "openai":
        extra: dict[str, Any] = {}
        if settings.openai_api_key:
            extra["api_key"] = settings.openai_api_key
        return init_chat_model(
            f"openai:{model}",
            temperature=temperature,
            streaming=streaming,
            **extra,
            **kwargs,
        )

    # ── Fallback: pass provider:model directly to init_chat_model ────────────
    logger.warning("Unknown provider '%s', passing to init_chat_model directly", provider)
    return init_chat_model(
        f"{provider}:{model}",
        temperature=temperature,
        streaming=streaming,
        **kwargs,
    )

