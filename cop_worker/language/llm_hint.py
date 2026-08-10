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

_SYSTEM_PROMPT = (
    "You are a player in a grid-based cop-and-thief game. "
    "Reply with ONE short sentence (max 10 words) hinting at your movement direction. "
    "No coordinates, no numbers, no punctuation beyond one period."
)

_INTENT_INSTRUCTION = {
    "truth": "Tell the truth about your direction.",
    "lie": "Lie — describe the opposite direction.",
    "ambiguous": "Be vague — do not reveal your direction.",
    "bluff": "Sound confident but be misleading.",
}

_DIRECTION_NAMES = {
    "N": "north",
    "S": "south",
    "E": "east",
    "W": "west",
    "STAY": "staying put",
}
_OPPOSITES = {
    "N": "south",
    "S": "north",
    "E": "west",
    "W": "east",
    "STAY": "away from here",
}


def _build_user_prompt(move: str, intent: str) -> str:
    direction = _DIRECTION_NAMES.get(move.upper(), move.lower())
    opposite = _OPPOSITES.get(move.upper(), direction)
    instruction = _INTENT_INSTRUCTION.get(intent, _INTENT_INSTRUCTION["truth"])
    return (
        f"You are moving {direction} (opposite would be {opposite}). "
        f"{instruction} One sentence only."
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


def _call_ollama(
    base_url: str,
    model: str,
    move: str,
    intent: str,
    timeout: float,
    keep_alive: str = "30m",
) -> str | None:
    """Blocking Ollama /api/chat call. Returns text or None on any error.

    ``keep_alive`` tells Ollama how long to keep the model resident in VRAM after
    the request. Without it the model may unload between hint calls, so the next
    call cold-loads (tens of seconds), blows past ``timeout``, and silently falls
    back to a template — while the GPU cycles the model in and out.
    """
    try:
        import httpx

        url = base_url.rstrip("/") + "/api/chat"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(move, intent)},
            ],
            "stream": False,
            "keep_alive": keep_alive,
            "options": {"num_predict": 30, "temperature": 0.7},
        }
        resp = httpx.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("message", {}).get("content", "").strip()
        if text:
            _record_tokens(data.get("prompt_eval_count", 0), data.get("eval_count", 0))
            # Enforce word cap — model may ignore instructions
            words = text.split()
            if len(words) > 15:
                text = " ".join(words[:15])
            return text
    except Exception as exc:
        logger.debug("Ollama hint call failed (%s): %s", type(exc).__name__, exc)
    return None


def _call_crewai_llm(llm, move: str, intent: str, timeout: float) -> str | None:
    """Call a crewai LLM object. Returns text or None on any error."""
    try:
        prompt = _SYSTEM_PROMPT + "\n\n" + _build_user_prompt(move, intent)
        result = llm.call([{"role": "user", "content": prompt}])
        if isinstance(result, str):
            text = result.strip()
            words = text.split()
            if len(words) > 15:
                text = " ".join(words[:15])
            return text or None
    except Exception as exc:
        logger.debug("crewai LLM hint call failed (%s): %s", type(exc).__name__, exc)
    return None


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
