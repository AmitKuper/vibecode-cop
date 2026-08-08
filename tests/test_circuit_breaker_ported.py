"""Unit tests for CircuitBreaker."""

import time

from cop_worker.gmail.circuit_breaker import CircuitBreaker, CircuitState


def test_initial_state_closed():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout_s=30.0)
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_opens_after_threshold_failures():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout_s=30.0)
    cb.on_failure()
    cb.on_failure()
    assert cb.state == CircuitState.CLOSED
    cb.on_failure()
    assert cb.state == CircuitState.OPEN


def test_open_blocks_requests():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout_s=30.0)
    cb.on_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_half_open_after_recovery_timeout():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout_s=0.05)
    cb.on_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.1)
    assert cb.allow_request() is True
    assert cb.state == CircuitState.HALF_OPEN


def test_success_closes_from_half_open():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout_s=0.05)
    cb.on_failure()
    time.sleep(0.1)
    cb.allow_request()  # transitions to HALF_OPEN
    cb.on_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_success_resets_failure_count():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout_s=30.0)
    cb.on_failure()
    cb.on_failure()
    cb.on_success()
    cb.on_failure()
    cb.on_failure()
    # only 2 failures after reset — still closed
    assert cb.state == CircuitState.CLOSED
