"""LLM hint backends: Ollama HTTP and crewai LLM objects."""

from __future__ import annotations

import logging

from cop_worker.language.llm_hint import _record_tokens
from cop_worker.language.llm_prompts import _SYSTEM_PROMPT, _build_user_prompt

logger = logging.getLogger(__name__)


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
