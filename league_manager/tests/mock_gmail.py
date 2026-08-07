"""Fake Gmail sender for LeagueManager tests.

Records all send calls. Never actually sends email.
"""

from __future__ import annotations


class MockGmailSender:
    """Records send() calls without sending to Gmail API."""

    def __init__(self) -> None:
        """Initialise with empty sent log."""
        self.sent: list[dict] = []

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        attachment_path: str | None = None,
    ) -> dict:
        """Record the send call and return a fake message ID.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Email body text.
            attachment_path: Optional path to attachment file.

        Returns:
            Dict with 'message_id' key.
        """
        record = {
            "to": to,
            "subject": subject,
            "body": body,
            "attachment_path": attachment_path,
        }
        self.sent.append(record)
        return {"message_id": f"mock-msg-{len(self.sent)}"}

    def assert_sent(self, count: int = 1) -> None:
        """Assert that exactly count send calls occurred."""
        assert len(self.sent) == count, f"Expected {count} sends, got {len(self.sent)}"

    def assert_not_sent(self) -> None:
        """Assert that no send calls occurred."""
        assert len(self.sent) == 0, f"Expected no sends, got {len(self.sent)}: {self.sent}"

    def assert_to_address(self, expected: str) -> None:
        """Assert all sends went to the expected address."""
        mismatches = [r["to"] for r in self.sent if r["to"] != expected]
        assert not mismatches, f"Expected all sends to {expected!r}, got mismatches: {mismatches}"

    def reset(self) -> None:
        """Clear the sent log."""
        self.sent.clear()
