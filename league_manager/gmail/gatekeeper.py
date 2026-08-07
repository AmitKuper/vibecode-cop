"""Gmail Gatekeeper — fail-closed rate limiting and anomaly detection stack."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class GatekeeperLockedError(Exception):
    """Raised when the circuit breaker is tripped and blocks a send."""


@dataclass
class DailyQuotaManager:
    """Tracks Gmail API sends per day to avoid exceeding quota."""

    daily_limit: int = 100
    _sends_today: int = field(default=0, init=False)
    _day_start: float = field(default_factory=time.time, init=False)

    def check_and_consume(self) -> bool:
        """Return True and consume one quota unit if within limit, else False.

        Resets the daily counter automatically after 24 hours.

        Returns:
            True if quota was available and consumed; False if quota exhausted.
        """
        now = time.time()
        if now - self._day_start > 86400:
            self._sends_today = 0
            self._day_start = now
        if self._sends_today >= self.daily_limit:
            return False
        self._sends_today += 1
        return True


@dataclass
class CircuitBreaker:
    """Fail-closed circuit breaker. Manual reset required after trip."""

    _tripped: bool = field(default=False, init=False)

    def trip(self) -> None:
        """Trip the circuit breaker — blocks all subsequent sends."""
        self._tripped = True
        logger.warning("Gmail circuit breaker TRIPPED")

    def reset(self) -> None:
        """Reset the circuit breaker (manual operator action required)."""
        self._tripped = False
        logger.info("Gmail circuit breaker RESET")

    @property
    def is_open(self) -> bool:
        """Return True if breaker is tripped (blocking sends)."""
        return self._tripped


class Gatekeeper:
    """Fail-closed send gatekeeper for Gmail.

    Stack: DailyQuotaManager → CircuitBreaker → Gmail API.
    On any anomaly, lock out and block. Never fail open.
    Both counted=True AND cli_counted_flag=True required to send.
    """

    def __init__(self, counted: bool, cli_counted_flag: bool, sender: object) -> None:
        """Initialise gatekeeper.

        Args:
            counted: Whether config has match.counted = True.
            cli_counted_flag: Whether --counted CLI flag was passed.
            sender: Gmail sender object with a send() method.
        """
        self.counted = counted
        self.cli_counted_flag = cli_counted_flag
        self.sender = sender
        self._quota = DailyQuotaManager()
        self.circuit_breaker = CircuitBreaker()

    def request_send(self, game_id: str, result_data: dict) -> dict:
        """Attempt to send a Gmail result report.

        Args:
            game_id: Game identifier for the email subject.
            result_data: Result data dict to include in the email.

        Returns:
            Dict with 'sent': True/False and optional 'reason'.
        """
        if not (self.counted and self.cli_counted_flag):
            logger.info("Friendly run — Gmail send suppressed")
            return {"sent": False, "reason": "friendly_run"}
        if self.circuit_breaker.is_open:
            logger.warning("Circuit breaker open — Gmail send blocked")
            return {"sent": False, "reason": "circuit_breaker"}
        if not self._quota.check_and_consume():
            logger.warning("Daily quota exceeded — Gmail send blocked")
            return {"sent": False, "reason": "quota_exceeded"}
        try:
            target = "rmisegal+uoh26finalgame@gmail.com"
            result = self.sender.send(
                to=target,
                subject=f"Game Result — {game_id}",
                body=str(result_data),
            )
            return {"sent": True, "message_id": result.get("message_id")}
        except Exception as exc:
            self.circuit_breaker.trip()
            logger.error("Gmail send failed, circuit breaker tripped: %s", exc)
            return {"sent": False, "reason": "send_error"}
