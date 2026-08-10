"""Outbound-call gateway: one seam for every network call the agent makes.

The course architecture requires all external calls to route through a central
gatekeeper with rate limiting and retries. The Gmail pipeline has had one from the
start (``cop_worker.gmail.gatekeeper``); this module gives the remaining outbound
surfaces — MCP wire calls and local-LLM hint calls — the same discipline:

* a per-kind token bucket (config-driven rates, never hard-coded),
* bounded at-least-once retries with exponential backoff (dedup-safe on the wire:
  turns dedupe on commit, greetings are drained, audits re-carry identical records),
* uniform logging of attempts and failures.

The match runner's per-call timeout policy (strictly below the signed
``response_timeout_sec``) stays with the caller — the gateway enforces *pacing and
persistence*, the caller enforces *deadline semantics*.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: Default pacing per call kind; override via ``configure()`` from runtime config.
DEFAULT_RATES: dict[str, tuple[int, float]] = {
    # kind: (bucket capacity, refill per second)
    "mcp": (30, 2.0),  # matches the signed rate_limiter_gatekeeper 30/min with burst
    "llm": (10, 0.5),
    "http": (30, 2.0),
}


@dataclass
class _Bucket:
    capacity: int
    refill_per_s: float
    tokens: float = field(default=0.0)
    stamp: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        self.tokens = float(self.capacity)

    async def take(self) -> None:
        while True:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.stamp) * self.refill_per_s)
            self.stamp = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            await asyncio.sleep(max(0.01, (1.0 - self.tokens) / self.refill_per_s))


class NetGateway:
    """Rate-limited, retrying executor for outbound async calls."""

    def __init__(self, rates: dict[str, tuple[int, float]] | None = None) -> None:
        self._buckets = {
            kind: _Bucket(cap, refill) for kind, (cap, refill) in (rates or DEFAULT_RATES).items()
        }

    def configure(self, kind: str, capacity: int, refill_per_s: float) -> None:
        self._buckets[kind] = _Bucket(capacity, refill_per_s)

    async def call(
        self,
        kind: str,
        fn: Callable[[], Awaitable],
        *,
        retries: int = 1,
        backoff_s: float = 0.5,
        max_backoff_s: float = 5.0,
        label: str = "",
    ):
        """Execute ``fn`` under the ``kind`` bucket with bounded retries.

        ``retries`` counts ATTEMPTS (>=1). The last failure re-raises — callers own
        the decision of what a hard failure means for the game.
        """
        bucket = self._buckets.get(kind)
        if bucket is None:
            raise KeyError(f"unknown gateway kind {kind!r}; configure() it first")
        delay = backoff_s
        for attempt in range(1, max(1, retries) + 1):
            await bucket.take()
            try:
                return await fn()
            except Exception as exc:
                if attempt == max(1, retries):
                    raise
                logger.warning(
                    "gateway %s%s attempt %d/%d failed (%s); retrying in %.1fs",
                    kind,
                    f":{label}" if label else "",
                    attempt,
                    retries,
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_backoff_s)


#: Process-wide instance; the match runner and hint generator share pacing state.
GATEWAY = NetGateway()
