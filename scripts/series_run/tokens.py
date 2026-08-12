"""LLM token accounting shared by the series runner."""

_TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


def _validated_token_totals(value: dict | None = None) -> dict[str, int]:
    """Return explicit non-negative LLM token accounting for final JSON."""
    source = value or {}
    totals: dict[str, int] = {}
    for key in _TOKEN_KEYS:
        raw = source.get(key, 0)
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise ValueError(f"invalid {key} token total: {raw!r}")
        totals[key] = raw
    if totals["total_tokens"] != totals["prompt_tokens"] + totals["completion_tokens"]:
        raise ValueError("total_tokens must equal prompt_tokens + completion_tokens")
    return totals
