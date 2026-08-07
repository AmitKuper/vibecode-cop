"""Tests for Gmail Gatekeeper fail-closed behavior."""

from league_manager.gmail.gatekeeper import Gatekeeper
from league_manager.tests.mock_gmail import MockGmailSender


def make_gate(counted=True, cli=True):
    """Create a Gatekeeper with both flags and a MockGmailSender."""
    return Gatekeeper(counted=counted, cli_counted_flag=cli, sender=MockGmailSender())


def test_both_flags_false_suppresses_send():
    """No flags set — email must not be sent."""
    gate = make_gate(counted=False, cli=False)
    result = gate.request_send("g001", {})
    assert result["sent"] is False
    gate.sender.assert_not_sent()


def test_only_config_counted_suppresses_send():
    """Config counted only — email must not be sent."""
    gate = make_gate(counted=True, cli=False)
    result = gate.request_send("g002", {})
    assert result["sent"] is False


def test_only_cli_flag_suppresses_send():
    """CLI flag only — email must not be sent."""
    gate = make_gate(counted=False, cli=True)
    result = gate.request_send("g003", {})
    assert result["sent"] is False


def test_both_flags_set_sends_email():
    """Both flags set — email must be sent."""
    gate = make_gate(counted=True, cli=True)
    result = gate.request_send("g004", {"cop_total": 3})
    assert result["sent"] is True
    gate.sender.assert_sent(count=1)


def test_tripped_circuit_breaker_blocks_send():
    """Tripped circuit breaker must block send even with both flags."""
    gate = make_gate()
    gate.circuit_breaker.trip()
    result = gate.request_send("g005", {})
    assert result["sent"] is False
    assert result["reason"] == "circuit_breaker"


def test_reset_circuit_breaker_allows_send():
    """Resetting circuit breaker must allow send again."""
    gate = make_gate()
    gate.circuit_breaker.trip()
    gate.circuit_breaker.reset()
    result = gate.request_send("g006", {})
    assert result["sent"] is True


def test_send_failure_trips_circuit_breaker():
    """A send failure must automatically trip the circuit breaker."""

    class FailSender:
        """Always raises on send."""

        def send(self, **kwargs):
            """Simulate network failure."""
            raise OSError("network failure")

    gate = Gatekeeper(counted=True, cli_counted_flag=True, sender=FailSender())
    gate.request_send("g007", {})
    assert gate.circuit_breaker.is_open is True
