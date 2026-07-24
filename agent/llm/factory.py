"""LLM factory for creating LLM instances from various backends."""

import logging
import os
from typing import Any

from agent.llm.config import LLMConfig, LLMConfigBuilder, LLMProvider
from agent.llm.providers import (
    create_anthropic,
    create_azure,
    create_ollama,
    create_openai,
)

logger = logging.getLogger(__name__)


class LLMFactory:
    """Factory for creating LLM instances for crewAI."""

    @staticmethod
    def create_llm(config: LLMConfig) -> Any:
        """Create LLM instance from config.

        Args:
            config: LLMConfig instance

        Returns:
            LLM instance compatible with crewAI

        Raises:
            ImportError: If required package not installed
            ValueError: If configuration invalid
        """
        logger.info(f"Creating LLM: {config.provider.value}/{config.model}")

        if config.provider == LLMProvider.OLLAMA:
            return create_ollama(config)
        elif config.provider == LLMProvider.OPENAI:
            return create_openai(config)
        elif config.provider == LLMProvider.ANTHROPIC:
            return create_anthropic(config)
        elif config.provider == LLMProvider.AZURE:
            return create_azure(config)
        else:
            raise ValueError(f"Unknown LLM provider: {config.provider}")

    @staticmethod
    def create_from_env() -> Any:
        """Create LLM from environment variables.

        Looks for:
          LLM_PROVIDER: ollama, openai, anthropic, azure
          LLM_MODEL: model name
          LLM_BASE_URL: for ollama/azure
          OPENAI_API_KEY: for openai
          ANTHROPIC_API_KEY: for anthropic
          AZURE_OPENAI_API_KEY: for azure

        Returns:
            LLM instance
        """
        provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        model = os.getenv("LLM_MODEL", "llama2")

        logger.info(f"Creating LLM from environment: {provider}/{model}")

        if provider == "ollama":
            base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
            config = LLMConfigBuilder.ollama(model=model, base_url=base_url)
        elif provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "")
            config = LLMConfigBuilder.openai(model=model, api_key=api_key)
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            config = LLMConfigBuilder.anthropic(model=model, api_key=api_key)
        elif provider == "azure":
            api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
            base_url = os.getenv("LLM_BASE_URL", "")
            config = LLMConfigBuilder.azure(
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
        else:
            logger.warning(f"Unknown provider {provider}, using ollama")
            config = LLMConfigBuilder.ollama(model=model)

        return LLMFactory.create_llm(config)

    @staticmethod
    def create_from_dict(config_dict: dict) -> Any:
        """Create LLM from dict (e.g., from TOML config).

        Args:
            config_dict: Config dict with llm settings

        Returns:
            LLM instance
        """
        config = LLMConfigBuilder.from_dict(config_dict)
        return LLMFactory.create_llm(config)
