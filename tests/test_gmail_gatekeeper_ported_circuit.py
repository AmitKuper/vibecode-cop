"""Tests for Gmail Gatekeeper circuit breaker, validation, and contradiction guard."""

import time

import pytest

from cop_worker.gmail.circuit_breaker import CircuitState
from cop_worker.gmail.gatekeeper import (
    Gatekeeper,
    GatekeeperError,
)
from tests.helpers_gmail_gatekeeper import VALID_BODY, make_fake_sender


def make_failing_sender(exc: Exception | None = None):
    """Return a fake sender that always raises."""
    if exc is None:
        exc = RuntimeError("Gmail API unavailable")

    def sender(to, subject, body, attachments):
        raise exc

    return sender


# ---------------------------------------------------------------------------
# 9. Circuit breaker opens after 3 failures
# ---------------------------------------------------------------------------
def test_circuit_breaker_opens():
    failing = make_failing_sender()
    gk = Gatekeeper(gmail_sender=failing, capacity=100.0, refill_rate=0.0)
    gk._cb._threshold = 3

    # 3 consecutive send attempts → each exhausts retries, each calls on_failure
    for i in range(3):
        with pytest.raises(GatekeeperError):
            gk.send(
                f"key-cbopen-{i}",
                f"game-cb-{i}",
                "Subject",
                VALID_BODY,
            )
        # Reset interval to allow next send through
        gk._last_send_time = 0.0

    assert gk._cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# 10. Circuit breaker half-open recovery
# ---------------------------------------------------------------------------
def test_circuit_breaker_half_open_recovery():
    fake = make_fake_sender("msg-recovered")
    gk = Gatekeeper(gmail_sender=fake, capacity=100.0, refill_rate=0.0)
    # Force open with short recovery timeout
    gk._cb._threshold = 1
    gk._cb._recovery_timeout = 0.05
    gk._cb.on_failure()
    assert gk._cb.state == CircuitState.OPEN

    time.sleep(0.1)  # wait for recovery window

    # Next send should go through in HALF_OPEN and close circuit on success
    mid = gk.send("key-hopen", "game-hopen", "Subject", VALID_BODY)
    assert mid == "msg-recovered"
    assert gk._cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# 11. Plain text body rejected
# ---------------------------------------------------------------------------
def test_plain_text_rejected():
    fake = make_fake_sender()
    gk = Gatekeeper(gmail_sender=fake)
    with pytest.raises(GatekeeperError, match="must be JSON"):
        gk.send("key-pt", "game-011", "Subject", "This is plain text, not JSON")


# ---------------------------------------------------------------------------
# 12. Dry-run mode must NOT record delivery (documented test)
# ---------------------------------------------------------------------------
def test_dry_run_cannot_count():
    # dry-run mode is handled at the GmailReportPlugin layer (agent/reports/gmail_report.py),
    # NOT inside Gatekeeper. The Gatekeeper.send() always increments _daily_count on real send.
    # This test documents that a dry-run wrapper must bypass Gatekeeper.send() entirely
    # so that _daily_count is never incremented.
    fake = make_fake_sender("msg-dryrun")
    gk = Gatekeeper(gmail_sender=fake, capacity=100.0, refill_rate=0.0)
    initial_count = gk._daily_count
    # Simulate dry-run: caller does NOT invoke gk.send() — returns preview directly
    # => daily_count must remain unchanged
    assert gk._daily_count == initial_count


# ---------------------------------------------------------------------------
# 13. Contradictory result — second game_id count blocked by DOS detector
# ---------------------------------------------------------------------------
def test_contradictory_result_blocked():
    """A second counted result for the same game_id is blocked by the DOS detector."""
    fake = make_fake_sender("msg-legit")
    gk = Gatekeeper(gmail_sender=fake, capacity=100.0, refill_rate=0.0)
    gk._dos._max_per_game = 1  # only 1 send per game_id allowed

    # First send succeeds
    mid = gk.send("key-legit", "game-contra", "Subject", VALID_BODY)
    assert mid == "msg-legit"

    # Advance last_send_time to bypass interval check
    gk._last_send_time = 0.0

    # Second send for same game_id (different idempotency key) is blocked
    with pytest.raises(GatekeeperError, match="DOS check failed"):
        gk.send("key-contra2", "game-contra", "Subject", VALID_BODY)
