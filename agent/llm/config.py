"""LLM configuration and factory for multiple backends."""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers."""

    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"


@dataclass
class LLMConfig:
    """Configuration for LLM backend."""

    provider: LLMProvider
    model: str
    temperature: float = 0.7
    max_tokens: int = 2048
    api_key: str | None = None
    base_url: str | None = None  # For Ollama: http://localhost:11434
    api_version: str | None = None  # For Azure
    deployment_id: str | None = None  # For Azure

    def to_dict(self) -> dict:
        """Convert to dict for logging."""
        return {
            "provider": self.provider.value,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "base_url": self.base_url,
        }


class LLMConfigBuilder:
    """Build LLM configuration from various sources."""

    @staticmethod
    def from_dict(config_dict: dict) -> LLMConfig:
        """Build LLM config from dict.

        Args:
            config_dict: Dict with keys: provider, model, temperature, etc.

        Returns:
            LLMConfig instance
        """
        provider_str = config_dict.get("provider", "ollama").lower()
        try:
            provider = LLMProvider(provider_str)
        except ValueError:
            logger.warning(f"Unknown provider {provider_str}, using ollama")
            provider = LLMProvider.OLLAMA

        return LLMConfig(
            provider=provider,
            model=config_dict.get("model", "gemma3:4b"),
            temperature=float(config_dict.get("temperature", 0.7)),
            max_tokens=int(config_dict.get("max_tokens", 2048)),
            api_key=config_dict.get("api_key"),
            base_url=config_dict.get("base_url"),
            api_version=config_dict.get("api_version"),
            deployment_id=config_dict.get("deployment_id"),
        )

    @staticmethod
    def ollama(
        model: str = "gemma3:4b", base_url: str = "http://localhost:11434", **kwargs
    ) -> LLMConfig:
        """Create Ollama LLM config.

        Args:
            model: Ollama model name (llama2, mistral, neural-chat, etc.)
            base_url: Ollama server URL
            **kwargs: Additional config (temperature, max_tokens)

        Returns:
            LLMConfig for Ollama
        """
        return LLMConfig(
            provider=LLMProvider.OLLAMA,
            model=model,
            base_url=base_url,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
        )

    @staticmethod
    def openai(model: str = "gpt-4", api_key: str = "", **kwargs) -> LLMConfig:
        """Create OpenAI LLM config.

        Args:
            model: OpenAI model (gpt-4, gpt-3.5-turbo, etc.)
            api_key: OpenAI API key
            **kwargs: Additional config

        Returns:
            LLMConfig for OpenAI
        """
        return LLMConfig(
            provider=LLMProvider.OPENAI,
            model=model,
            api_key=api_key,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
        )

    @staticmethod
    def anthropic(model: str = "claude-3-sonnet", api_key: str = "", **kwargs) -> LLMConfig:
        """Create Anthropic LLM config.

        Args:
            model: Claude model (claude-3-sonnet, claude-opus, etc.)
            api_key: Anthropic API key
            **kwargs: Additional config

        Returns:
            LLMConfig for Anthropic
        """
        return LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model=model,
            api_key=api_key,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
        )

    @staticmethod
    def azure(
        model: str,
        api_key: str,
        base_url: str,
        api_version: str = "2024-02-15-preview",
        deployment_id: str = "",
        **kwargs,
    ) -> LLMConfig:
        """Create Azure OpenAI LLM config.

        Args:
            model: Model name
            api_key: Azure API key
            base_url: Azure endpoint URL
            api_version: Azure API version
            deployment_id: Azure deployment ID
            **kwargs: Additional config

        Returns:
            LLMConfig for Azure
        """
        return LLMConfig(
            provider=LLMProvider.AZURE,
            model=model,
            api_key=api_key,
            base_url=base_url,
            api_version=api_version,
            deployment_id=deployment_id,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
        )
