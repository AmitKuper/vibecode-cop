"""Circuit breaker for Gmail API calls."""

import threading
import time


class CircuitState:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout_s: float = 30.0):
        self._threshold = failure_threshold
        self._recovery_timeout = recovery_timeout_s
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        return self._state

    def allow_request(self) -> bool:
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._opened_at >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    return True
                return False
            return True  # HALF_OPEN: allow one probe

    def on_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = CircuitState.CLOSED

    def on_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
