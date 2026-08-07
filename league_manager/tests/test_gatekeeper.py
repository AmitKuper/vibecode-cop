"""Tests for Gmail Gatekeeper — fail-closed behaviour."""

from __future__ import annotations

from league_manager.gmail.gatekeeper import Gatekeeper
from league_manager.tests.mock_gmail import MockGmailSender


def make_gate(counted: bool = True, cli: bool = True) -> Gatekeeper:
    """Build a Gatekeeper with both flags set by default.

    Args:
        counted: Config-level counted flag.
        cli: CLI --counted flag.

    Returns:
        Configured Gatekeeper with a MockGmailSender.
    """
    return Gatekeeper(counted=counted, cli_counted_flag=cli, sender=MockGmailSender())


def test_friendly_run_never_sends() -> None:
    """Neither counted flag set — no email sent."""
    gate = Gatekeeper(counted=False, cli_counted_flag=False, sender=MockGmailSender())
    result = gate.request_send("game_001", {})
    assert result["sent"] is False
    gate.sender.assert_not_sent()


def test_counted_config_only_does_not_send() -> None:
    """Config counted=True alone is insufficient — no email sent."""
    gate = Gatekeeper(counted=True, cli_counted_flag=False, sender=MockGmailSender())
    result = gate.request_send("game_002", {})
    assert result["sent"] is False
    gate.sender.assert_not_sent()


def test_counted_flag_only_does_not_send() -> None:
    """CLI flag alone is insufficient — no email sent."""
    gate = Gatekeeper(counted=False, cli_counted_flag=True, sender=MockGmailSender())
    result = gate.request_send("game_003", {})
    assert result["sent"] is False
    gate.sender.assert_not_sent()


def test_circuit_breaker_fail_closed() -> None:
    """Tripped circuit breaker blocks sends even when both flags set."""
    gate = make_gate()
    gate.circuit_breaker.trip()
    result = gate.request_send("game_004", {})
    assert result["sent"] is False
    assert result["reason"] == "circuit_breaker"
    gate.sender.assert_not_sent()


def test_counted_both_flags_sends() -> None:
    """Both flags set with open circuit breaker — email is sent."""
    gate = make_gate()
    result = gate.request_send("game_005", {"cop_total": 3})
    assert result["sent"] is True
    gate.sender.assert_sent(count=1)


def test_circuit_breaker_reset_allows_send() -> None:
    """After reset, circuit breaker allows sends again."""
    gate = make_gate()
    gate.circuit_breaker.trip()
    gate.circuit_breaker.reset()
    result = gate.request_send("game_006", {})
    assert result["sent"] is True


def test_friendly_run_reason_reported() -> None:
    """Friendly run returns 'friendly_run' reason."""
    gate = make_gate(counted=False, cli=False)
    result = gate.request_send("game_007", {})
    assert result["reason"] == "friendly_run"


def test_circuit_breaker_trips_on_send_error() -> None:
    """Failed send trips the circuit breaker automatically."""

    class FailingSender:
        """Sender that always raises on send()."""

        def send(self, **kwargs) -> dict:
            """Always raise to simulate Gmail API failure."""
            raise OSError("connection refused")

    gate = Gatekeeper(counted=True, cli_counted_flag=True, sender=FailingSender())
    result = gate.request_send("game_008", {})
    assert result["sent"] is False
    assert result["reason"] == "send_error"
    assert gate.circuit_breaker.is_open is True


def test_quota_exhaustion_blocks_send() -> None:
    """Daily quota=1 allows first send; second send is blocked."""
    gate = make_gate()
    gate._quota.daily_limit = 1
    r1 = gate.request_send("game_009a", {})
    assert r1["sent"] is True
    r2 = gate.request_send("game_009b", {})
    assert r2["sent"] is False
    assert r2["reason"] == "quota_exceeded"
