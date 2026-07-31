"""LLM configuration and factory for multiple backends."""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
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
    base_url: str | None = None
    api_version: str | None = None
    deployment_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "provider": self.provider.value, "model": self.model,
            "temperature": self.temperature, "max_tokens": self.max_tokens,
            "base_url": self.base_url,
        }


class LLMConfigBuilder:
    """Build LLM configuration from various sources."""

    @staticmethod
    def from_dict(config_dict: dict) -> LLMConfig:
        """Build LLM config from a dict with keys: provider, model, temperature, etc."""
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
        """Create Ollama LLM config."""
        return LLMConfig(
            provider=LLMProvider.OLLAMA, model=model, base_url=base_url,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
        )

    @staticmethod
    def openai(model: str = "gpt-4", api_key: str = "", **kwargs) -> LLMConfig:
        """Create OpenAI LLM config."""
        return LLMConfig(
            provider=LLMProvider.OPENAI, model=model, api_key=api_key,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
        )

    @staticmethod
    def anthropic(model: str = "claude-3-sonnet", api_key: str = "", **kwargs) -> LLMConfig:
        """Create Anthropic LLM config."""
        return LLMConfig(
            provider=LLMProvider.ANTHROPIC, model=model, api_key=api_key,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
        )

    @staticmethod
    def azure(
        model: str, api_key: str, base_url: str,
        api_version: str = "2024-02-15-preview", deployment_id: str = "", **kwargs,
    ) -> LLMConfig:
        """Create Azure OpenAI LLM config."""
        return LLMConfig(
            provider=LLMProvider.AZURE, model=model, api_key=api_key,
            base_url=base_url, api_version=api_version, deployment_id=deployment_id,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
        )
