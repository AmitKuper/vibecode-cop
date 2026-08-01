"""Provider-specific LLM builder functions — returns crewai.LLM for all backends."""

import logging
import os
from typing import Any

from agent.llm.config import LLMConfig

logger = logging.getLogger(__name__)


def create_ollama(config: LLMConfig) -> Any:
    """Create crewai.LLM backed by a local Ollama server."""
    from crewai import LLM  # crewai>=1.0 uses LiteLLM under the hood

    base_url = (config.base_url or "http://localhost:11434").rstrip("/")
    model = f"ollama/{config.model}"
    logger.info(f"Initialising Ollama LLM: {model} at {base_url}")
    max_tokens = getattr(config, "max_tokens", None)
    kwargs = {"model": model, "base_url": base_url, "temperature": config.temperature}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    return LLM(**kwargs)


def create_anthropic(config: LLMConfig) -> Any:
    """Create crewai.LLM backed by Anthropic API."""
    from crewai import LLM

    api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "Anthropic API key required — set ANTHROPIC_API_KEY or [llm] api_key in config"
        )
    model = config.model if "/" in config.model else f"anthropic/{config.model}"
    logger.info(f"Initialising Anthropic LLM: {model}")
    return LLM(model=model, api_key=api_key, temperature=config.temperature)


def create_openai(config: LLMConfig) -> Any:
    """Create crewai.LLM backed by OpenAI API."""
    from crewai import LLM

    api_key = config.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenAI API key required — set OPENAI_API_KEY or [llm] api_key in config"
        )
    logger.info(f"Initialising OpenAI LLM: {config.model}")
    return LLM(model=config.model, api_key=api_key, temperature=config.temperature)


def create_azure(config: LLMConfig) -> Any:
    """Create crewai.LLM backed by Azure OpenAI."""
    from crewai import LLM

    api_key = config.api_key or os.getenv("AZURE_OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "Azure API key required — set AZURE_OPENAI_API_KEY or [llm] api_key in config"
        )
    if not config.base_url:
        raise ValueError("Azure endpoint URL required — set [llm] base_url in config")

    logger.info(f"Initialising Azure OpenAI LLM: {config.deployment_id or config.model}")
    return LLM(
        model=f"azure/{config.deployment_id or config.model}",
        api_key=api_key,
        base_url=config.base_url,
        api_version=config.api_version or "2024-02-15-preview",
        temperature=config.temperature,
    )
