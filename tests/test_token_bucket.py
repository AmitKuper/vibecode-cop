"""Unit tests for TokenBucket."""

import time

import pytest

from agent.gmail.token_bucket import TokenBucket


def test_initial_tokens_full():
    bucket = TokenBucket(capacity=5.0, refill_rate=1.0)
    assert bucket.tokens() == pytest.approx(5.0, abs=0.01)


def test_consume_success():
    bucket = TokenBucket(capacity=5.0, refill_rate=1.0)
    assert bucket.consume(1.0) is True
    assert bucket.tokens() == pytest.approx(4.0, abs=0.05)


def test_consume_insufficient():
    bucket = TokenBucket(capacity=2.0, refill_rate=0.0)
    bucket.consume(2.0)
    assert bucket.consume(1.0) is False


def test_consume_exact():
    bucket = TokenBucket(capacity=3.0, refill_rate=0.0)
    assert bucket.consume(3.0) is True
    assert bucket.consume(0.1) is False


def test_refill_over_time():
    bucket = TokenBucket(capacity=10.0, refill_rate=10.0)
    # drain it
    bucket.consume(10.0)
    assert bucket.tokens() == pytest.approx(0.0, abs=0.1)
    # wait for refill
    time.sleep(0.2)
    assert bucket.tokens() >= 1.5  # 10 t/s * 0.2s = 2.0 tokens


def test_tokens_capped_at_capacity():
    bucket = TokenBucket(capacity=5.0, refill_rate=100.0)
    time.sleep(0.1)
    assert bucket.tokens() <= 5.0


def test_consume_fractional():
    bucket = TokenBucket(capacity=10.0, refill_rate=0.0)
    assert bucket.consume(0.5) is True
    assert bucket.tokens() == pytest.approx(9.5, abs=0.01)
