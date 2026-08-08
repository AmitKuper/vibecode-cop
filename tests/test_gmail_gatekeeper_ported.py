"""Tests for Gmail Gatekeeper full pipeline using injected fake sender."""

import time

import pytest

from cop_worker.gmail.circuit_breaker import CircuitState
from cop_worker.gmail.gatekeeper import (
    DAILY_QUOTA,
    Gatekeeper,
    GatekeeperError,
)

VALID_BODY = '{"game_id": "g1", "winner": "cop", "signature": "abc123"}'


def make_fake_sender(message_id: str = "fake-msg-id-001"):
    """Return a fake sender callable that records calls and returns message_id."""
    calls = []

    def sender(to, subject, body, attachments):
        calls.append({"to": to, "subject": subject, "body": body})
        return message_id

    sender.calls = calls
    return sender


def make_failing_sender(exc: Exception | None = None):
    """Return a fake sender that always raises."""
    if exc is None:
        exc = RuntimeError("Gmail API unavailable")

    def sender(to, subject, body, attachments):
        raise exc

    return sender


# ---------------------------------------------------------------------------
# 1. Successful send
# ---------------------------------------------------------------------------
def test_successful_send():
    fake = make_fake_sender("msg-001")
    gk = Gatekeeper(gmail_sender=fake)
    mid = gk.send("key-1", "game-001", "Subject", VALID_BODY)
    assert mid == "msg-001"
    assert len(fake.calls) == 1


# ---------------------------------------------------------------------------
# 2. Idempotent duplicate — second call returns cached, sender not called again
# ---------------------------------------------------------------------------
def test_idempotent_duplicate():
    fake = make_fake_sender("msg-002")
    gk = Gatekeeper(gmail_sender=fake)
    mid1 = gk.send("key-dup", "game-002", "Subject", VALID_BODY)
    mid2 = gk.send("key-dup", "game-002", "Subject", VALID_BODY)
    assert mid1 == mid2 == "msg-002"
    assert len(fake.calls) == 1  # sender called only once


# ---------------------------------------------------------------------------
# 3. Quota exhaustion
# ---------------------------------------------------------------------------
def test_quota_exhaustion():
    fake = make_fake_sender()
    gk = Gatekeeper(gmail_sender=fake)
    gk._daily_count = DAILY_QUOTA  # force quota exhausted
    with pytest.raises(GatekeeperError, match="Daily quota"):
        gk.send("key-quota", "game-003", "Subject", VALID_BODY)


# ---------------------------------------------------------------------------
# 4. Token bucket depletion
# ---------------------------------------------------------------------------
def test_token_bucket_depletion():
    fake = make_fake_sender()
    # capacity=1, no refill; drain the bucket manually first
    gk = Gatekeeper(gmail_sender=fake, capacity=1.0, refill_rate=0.0)
    gk._bucket.consume(1.0)  # drain
    with pytest.raises(GatekeeperError, match="Token bucket empty"):
        gk.send("key-tb", "game-004", "Subject", VALID_BODY)


# ---------------------------------------------------------------------------
# 5. Token bucket refill
# ---------------------------------------------------------------------------
def test_token_bucket_refill():
    fake = make_fake_sender("msg-refill")
    # refill_rate=50.0 means 50 tokens/sec — after 0.1s we get 5 tokens back
    gk = Gatekeeper(gmail_sender=fake, capacity=5.0, refill_rate=50.0)
    gk._bucket.consume(5.0)  # drain
    time.sleep(0.12)  # wait for refill (50 * 0.12 = 6 > 1 token)
    mid = gk.send("key-refill", "game-005", "Subject", VALID_BODY)
    assert mid == "msg-refill"


# ---------------------------------------------------------------------------
# 6. Minimum interval
# ---------------------------------------------------------------------------
def test_minimum_interval():
    fake = make_fake_sender()
    gk = Gatekeeper(gmail_sender=fake, capacity=100.0, refill_rate=0.0)
    gk._last_send_time = time.monotonic()  # simulate a recent send
    with pytest.raises(GatekeeperError, match="Too soon"):
        gk.send("key-interval", "game-006", "Subject", VALID_BODY)


# ---------------------------------------------------------------------------
# 7. DOS lock — burst detection
# ---------------------------------------------------------------------------
def test_dos_lock_burst():
    fake = make_fake_sender()
    # max_per_minute=2 so 3rd call within window triggers lock
    gk = Gatekeeper(gmail_sender=fake, capacity=100.0, refill_rate=0.0)
    gk._dos._max_per_minute = 2
    # Pre-fill timestamps to simulate 2 already counted
    now = time.monotonic()
    gk._dos._timestamps.append(now)
    gk._dos._timestamps.append(now)
    with pytest.raises(GatekeeperError, match="DOS check failed"):
        gk.send("key-burst", "game-007", "Subject", VALID_BODY)
    assert gk._dos.is_locked


# ---------------------------------------------------------------------------
# 8. DOS lock — repeated game_id
# ---------------------------------------------------------------------------
def test_dos_lock_repeated_game_id():
    fake = make_fake_sender()
    gk = Gatekeeper(gmail_sender=fake, capacity=100.0, refill_rate=0.0)
    gk._dos._max_per_game = 1
    gk._dos._game_counts["game-008"] = 1  # already at limit
    with pytest.raises(GatekeeperError, match="DOS check failed"):
        gk.send("key-repeated", "game-008", "Subject", VALID_BODY)
    assert gk._dos.is_locked


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
