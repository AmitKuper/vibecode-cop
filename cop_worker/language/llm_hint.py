"""LLM-backed hint text generation with template fallback.

Calls Ollama directly via httpx for speed (no crewai/LiteLLM overhead on the
hot path).  Any other configured provider falls back to the crewai LLM object.
Templates are always the fallback when the LLM is unavailable or times out.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

from cop_worker.language.llm_prompts import (  # noqa: E402,F401  (re-exports)
    _DIRECTION_NAMES,
    _OPPOSITES,
    _SYSTEM_PROMPT,
    _build_user_prompt,
)

#: Cumulative real token usage of every successful local-LLM hint call in this
#: process. Surfaced in result artifacts via :func:`token_totals`.
_TOKEN_METER = {"prompt": 0, "completion": 0, "total": 0}


def token_totals() -> dict:
    """Real cumulative LLM token usage for this process (prompt/completion/total)."""
    return dict(_TOKEN_METER)


def reset_token_totals() -> None:
    for key in _TOKEN_METER:
        _TOKEN_METER[key] = 0


def _record_tokens(prompt: int, completion: int) -> None:
    _TOKEN_METER["prompt"] += int(prompt)
    _TOKEN_METER["completion"] += int(completion)
    _TOKEN_METER["total"] += int(prompt) + int(completion)


class LLMHintGenerator:
    """Wraps LLM config and generates hint text; falls back silently to None."""

    def __init__(
        self,
        provider: str = "ollama",
        model: str = "llama3.1:8b",
        base_url: str = "http://localhost:11434",
        timeout: float = 3.0,
        keep_alive: str = "30m",
        llm=None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.keep_alive = keep_alive
        self._llm = llm  # crewai LLM object for non-Ollama providers

    def generate(self, move: str, intent: str) -> str | None:
        """Return LLM-generated hint text, or None if unavailable/too slow."""
        if self.provider == "ollama":
            return _call_ollama(
                self.base_url,
                self.model,
                move,
                intent,
                self.timeout,
                keep_alive=self.keep_alive,
            )
        if self._llm is not None:
            return _call_crewai_llm(self._llm, move, intent, self.timeout)
        return None

    def warmup(self, timeout: float = 90.0) -> bool:
        """Load the model into VRAM before play so hint calls hit a warm model.

        Uses a generous timeout because the first (cold) load can take tens of
        seconds. Returns True if the model responded, False otherwise.
        """
        if self.provider != "ollama":
            return self._llm is not None
        text = _call_ollama(
            self.base_url,
            self.model,
            "N",
            "truth",
            timeout,
            keep_alive=self.keep_alive,
        )
        ok = text is not None
        logger.info(
            "LLM warmup %s: model=%s keep_alive=%s",
            "OK" if ok else "FAILED",
            self.model,
            self.keep_alive,
        )
        return ok

    @classmethod
    def from_llm_config(cls, llm_config: dict, llm=None) -> LLMHintGenerator:
        """Build from the [llm] config section dict."""
        return cls(
            provider=llm_config.get("provider", "ollama"),
            model=llm_config.get("model", "llama3.1:8b"),
            base_url=llm_config.get("base_url", "http://localhost:11434"),
            timeout=float(llm_config.get("hint_timeout", 3.0)),
            keep_alive=str(llm_config.get("keep_alive", "30m")),
            llm=llm,
        )


from cop_worker.language.llm_hint_backends import (  # noqa: E402,F401  (re-exports)
    _call_crewai_llm,
    _call_ollama,
)
