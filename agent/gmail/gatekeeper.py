"""Production Gmail Gatekeeper — full pipeline."""

import threading
import time
from collections.abc import Callable

from agent.gmail.circuit_breaker import CircuitBreaker
from agent.gmail.dos_detector import DosDetector
from agent.gmail.token_bucket import TokenBucket

RECIPIENT = "agentsorch@gmail.com"
DAILY_QUOTA = 20
MAX_CONCURRENT = 2
MIN_INTERVAL_S = 5.0
MAX_RETRIES = 3
MIN_RETRY_DELAY_S = 2.0


class GatekeeperError(ValueError):
    pass


class Gatekeeper:
    """Full pipeline: validate -> idempotency -> quota -> token bucket ->
    concurrency -> DOS -> circuit breaker -> retry -> send."""

    def __init__(
        self,
        gmail_sender: Callable,
        capacity: float = 10.0,
        refill_rate: float = 0.1,
    ):
        # gmail_sender: Callable(to, subject, body, attachments) -> message_id
        self._sender = gmail_sender
        self._bucket = TokenBucket(capacity, refill_rate)
        self._dos = DosDetector()
        self._cb = CircuitBreaker()
        self._semaphore = threading.Semaphore(MAX_CONCURRENT)
        self._idempotency: dict = {}  # idempotency_key -> message_id
        self._daily_count = 0
        self._last_send_time = 0.0
        self._lock = threading.Lock()

    def send(
        self,
        idempotency_key: str,
        game_id: str,
        subject: str,
        body: str,
        attachments: list | None = None,
    ) -> str:
        """Send email through full pipeline. Returns message_id."""
        attachments = attachments or []

        # 1. Schema validation: body must be JSON result, not plain text
        if not body.strip().startswith("{"):
            raise GatekeeperError("Report body must be JSON (signed result), not plain text")

        # 2. Idempotency
        with self._lock:
            if idempotency_key in self._idempotency:
                return self._idempotency[idempotency_key]

            # 3. Daily quota
            if self._daily_count >= DAILY_QUOTA:
                raise GatekeeperError(f"Daily quota {DAILY_QUOTA} exhausted")

            # 4. Minimum interval
            elapsed = time.monotonic() - self._last_send_time
            if self._last_send_time > 0 and elapsed < MIN_INTERVAL_S:
                raise GatekeeperError(
                    f"Too soon: {elapsed:.1f}s < {MIN_INTERVAL_S}s minimum interval"
                )

        # 5. Token bucket
        if not self._bucket.consume():
            raise GatekeeperError("Token bucket empty — rate limit")

        # 6. DOS detector
        ok, reason = self._dos.check(game_id)
        if not ok:
            raise GatekeeperError(f"DOS check failed: {reason}")

        # 7. Circuit breaker
        if not self._cb.allow_request():
            raise GatekeeperError("Circuit breaker OPEN")

        # 8. Concurrency semaphore + retry
        with self._semaphore:
            last_err = None
            for attempt in range(MAX_RETRIES):
                try:
                    message_id = self._sender(RECIPIENT, subject, body, attachments)
                    self._cb.on_success()
                    with self._lock:
                        self._idempotency[idempotency_key] = message_id
                        self._daily_count += 1
                        self._last_send_time = time.monotonic()
                    return message_id
                except Exception as e:
                    last_err = e
                    self._cb.on_failure()
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(MIN_RETRY_DELAY_S * (attempt + 1))
            raise GatekeeperError(f"All {MAX_RETRIES} attempts failed: {last_err}")
