"""Shared fake-sender helpers for the ported Gmail Gatekeeper test suites."""

VALID_BODY = '{"game_id": "g1", "winner": "cop", "signature": "abc123"}'


def make_fake_sender(message_id: str = "fake-msg-id-001"):
    """Return a fake sender callable that records calls and returns message_id."""
    calls = []

    def sender(to, subject, body, attachments):
        calls.append({"to": to, "subject": subject, "body": body})
        return message_id

    sender.calls = calls
    return sender
