"""Token bucket for rate limiting."""

import threading
import time


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
