"""Token usage counter — aggregates LLM prompt/completion tokens across calls."""

import logging
import threading

logger = logging.getLogger(__name__)


class TokenCounter:
    """Thread-safe accumulator for LLM token usage.

    Usage:
        counter = TokenCounter()
        counter.record(prompt_tokens=120, completion_tokens=30)
        counter.record_from_crew_output(crew_result)
        summary = counter.summary()
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._prompt = 0
        self._completion = 0
        self._calls = 0

    def record(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        with self._lock:
            self._prompt += prompt_tokens
            self._completion += completion_tokens
            self._calls += 1

    def record_from_crew_output(self, result: object) -> None:
        """Extract and record token usage from a crewAI CrewOutput object."""
        try:
            usage = getattr(result, "token_usage", None)
            if usage is None:
                return
            if hasattr(usage, "total_tokens"):
                # CrewAI UsageMetrics object
                self.record(
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                )
            elif isinstance(usage, dict):
                self.record(
                    prompt_tokens=usage.get("prompt_tokens", 0) or 0,
                    completion_tokens=usage.get("completion_tokens", 0) or 0,
                )
        except Exception as exc:
            logger.debug(f"[TokenCounter] Could not extract token usage: {exc}")

    @property
    def total(self) -> int:
        with self._lock:
            return self._prompt + self._completion

    def summary(self) -> dict:
        with self._lock:
            return {
                "prompt_tokens": self._prompt,
                "completion_tokens": self._completion,
                "total_tokens": self._prompt + self._completion,
                "llm_calls": self._calls,
            }

    def reset(self) -> None:
        with self._lock:
            self._prompt = self._completion = self._calls = 0
