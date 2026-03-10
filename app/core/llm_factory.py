"""LLM factory — provider-agnostic model instantiation via LangChain.

Supported providers:
  - ollama             Local Ollama server (http://localhost:11434)
  - openai             OpenAI API (api.openai.com)
  - openai_compatible  Any OpenAI-API-compatible server (LM Studio, vLLM, Jan, etc.)
"""

import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mistralai import ChatMistralAI
from langchain_ollama import ChatOllama

from app.config import settings

logger = logging.getLogger(__name__)


def get_llm(
    provider: str,
    model: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
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
    # ── OpenAI-compatible (LM Studio, vLLM, default provider for generic APIs) ───────────
    if provider == "openai_compatible":
        if not base_url:
            raise ValueError(
                "openai_compatible provider requires a base URL"
            )
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            base_url=base_url,
            api_key=api_key or "not-needed",
            **kwargs,
        )

    # ── Native Ollama ─────────────────────────────────────────────────────────
    if provider == "ollama":
        return ChatOllama(
            model=model,
            temperature=temperature,
            base_url=base_url,
            **kwargs,
        )

    # ── OpenAI ────────────────────────────────────────────────────────────────
    if provider == "openai":
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            api_key=api_key,
            **kwargs,
        )

    # ── Anthropic ─────────────────────────────────────────────────────────────
    if provider == "anthropic":
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            streaming=streaming,
            api_key=api_key,
            **kwargs,
        )

    # ── Google GenAI (Gemini) ─────────────────────────────────────────────────
    if provider == "google_genai":
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            api_key=api_key,
            **kwargs,
        )

    # ── MistralAI ─────────────────────────────────────────────────────────────
    if provider == "mistralai":
        return ChatMistralAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            api_key=api_key,
            **kwargs,
        )

    # ── Fallback ────────────
    raise ValueError(f"Unknown LLM provider: {provider}")

