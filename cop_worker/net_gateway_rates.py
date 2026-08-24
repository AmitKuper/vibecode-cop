"""Gateway pacing configuration (split from net_gateway, 150-line rule).

Rates are externalized in ``config/rate_limits.json`` (versioned); the defaults
here are identical to the shipped file, so configuration is the override
mechanism, never a behavioral dependency.
"""

from __future__ import annotations

#: Default pacing per call kind; override via ``configure()`` from runtime config.
DEFAULT_RATES: dict[str, tuple[int, float]] = {
    # kind: (bucket capacity, refill per second). 0.5/s = the signed
    # rate_limiter_gatekeeper 30/min SUSTAINED cap; capacity 30 is burst headroom.
    "mcp": (30, 0.5),
    "llm": (10, 0.5),
    "http": (30, 0.5),
    "gmail": (30, 0.5),
}

#: Signed gatekeeper minimum: bound on outbound calls waiting for a bucket token.
DEFAULT_QUEUE_DEPTH = 100


def load_rates(path: str | None = None) -> dict[str, tuple[int, float]]:
    """Read pacing from ``config/rate_limits.json`` (externalized, versioned).

    Falls back to :data:`DEFAULT_RATES` when the file is absent or malformed — the
    file ships with values identical to the defaults, so configuration is the
    override mechanism, never a behavioral dependency.
    """
    import json
    from pathlib import Path

    default = Path(__file__).resolve().parents[1] / "config" / "rate_limits.json"
    candidate = Path(path) if path else default
    try:
        doc = json.loads(candidate.read_text(encoding="utf-8"))
        return {
            kind: (int(spec["capacity"]), float(spec["refill_per_s"]))
            for kind, spec in doc["kinds"].items()
        }
    except (OSError, KeyError, TypeError, ValueError):
        return dict(DEFAULT_RATES)


def load_queue_depth(path: str | None = None) -> int:
    """Read the signed pending-call bound from ``config/rate_limits.json``."""
    import json
    from pathlib import Path

    default = Path(__file__).resolve().parents[1] / "config" / "rate_limits.json"
    candidate = Path(path) if path else default
    try:
        doc = json.loads(candidate.read_text(encoding="utf-8"))
        return int(doc.get("queue_depth", DEFAULT_QUEUE_DEPTH))
    except (OSError, TypeError, ValueError):
        return DEFAULT_QUEUE_DEPTH
