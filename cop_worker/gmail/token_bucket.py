"""Token bucket for rate limiting."""

import json
import threading
import time
from pathlib import Path

# Historical code defaults for Gatekeeper pacing. config/rate_limits.json, when
# present, overrides them; a missing or malformed file changes nothing.
DEFAULT_CAPACITY = 10.0
DEFAULT_REFILL_PER_S = 0.1

_RATE_LIMITS_PATH = Path(__file__).resolve().parents[2] / "config" / "rate_limits.json"


def load_gmail_rate(path: str | Path | None = None) -> tuple[float, float]:
    """Read Gmail pacing from ``config/rate_limits.json`` (externalized, versioned).

    Returns ``(capacity, refill_per_s)``. Falls back to the code defaults when
    the file is absent or malformed — configuration is the override mechanism,
    never a behavioral dependency.
    """
    candidate = Path(path) if path else _RATE_LIMITS_PATH
    try:
        doc = json.loads(candidate.read_text(encoding="utf-8"))
        spec = doc["kinds"]["gmail"]
        return float(spec["capacity"]), float(spec["refill_per_s"])
    except (OSError, KeyError, TypeError, ValueError):
        return (DEFAULT_CAPACITY, DEFAULT_REFILL_PER_S)


class TokenBucket:
    """Thread-safe continuous token bucket with monotonic refill."""

    def __init__(self, capacity: float, refill_rate: float):
        self._capacity = capacity  # max tokens
        self._rate = refill_rate  # tokens per second
        self._tokens = capacity  # start full
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + self._rate * elapsed)
        self._last_refill = now

    def consume(self, cost: float = 1.0) -> bool:
        """Returns True if allowed, False if insufficient tokens."""
        with self._lock:
            self._refill()
            if self._tokens >= cost:
                self._tokens -= cost
                return True
            return False

    def tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens
