"""Tests for Gmail Gatekeeper rate limiting (quota, bucket, interval, DOS) via fake sender."""

import time

import pytest

from cop_worker.gmail.gatekeeper import (
    DAILY_QUOTA,
    Gatekeeper,
    GatekeeperError,
)
from tests.helpers_gmail_gatekeeper import VALID_BODY, make_fake_sender


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
