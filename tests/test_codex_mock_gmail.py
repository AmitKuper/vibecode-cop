"""Tests for MockGmailSender — verifies the test double behavior."""

import pytest

from league_manager.tests.mock_gmail import MockGmailSender


def test_send_records_message():
    """send() must record a message entry."""
    sender = MockGmailSender()
    sender.send(to="a@b.com", subject="Test", body="hello")
    sender.assert_sent(count=1)


def test_send_returns_message_id():
    """send() must return a dict with 'message_id'."""
    sender = MockGmailSender()
    result = sender.send(to="a@b.com", subject="Test", body="body")
    assert "message_id" in result


def test_assert_not_sent_passes_when_empty():
    """assert_not_sent must pass when no sends have occurred."""
    sender = MockGmailSender()
    sender.assert_not_sent()


def test_assert_not_sent_fails_after_send():
    """assert_not_sent must fail after a send."""
    sender = MockGmailSender()
    sender.send(to="a@b.com", subject="s", body="b")
    with pytest.raises(AssertionError):
        sender.assert_not_sent()


def test_assert_sent_count_mismatch_raises():
    """assert_sent(count=2) must fail when only 1 was sent."""
    sender = MockGmailSender()
    sender.send(to="a@b.com", subject="s", body="b")
    with pytest.raises(AssertionError):
        sender.assert_sent(count=2)


def test_assert_to_address_matches():
    """assert_to_address must pass when last send was to expected address."""
    sender = MockGmailSender()
    sender.send(to="target@example.com", subject="s", body="b")
    sender.assert_to_address("target@example.com")


def test_reset_clears_sent_log():
    """reset() must clear all recorded sends."""
    sender = MockGmailSender()
    sender.send(to="a@b.com", subject="s", body="b")
    sender.reset()
    sender.assert_not_sent()
