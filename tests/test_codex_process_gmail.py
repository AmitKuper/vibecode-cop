"""Process-level Gmail dependency construction and acceptance fake tests."""

import json

import pytest

from cop_worker.gmail.sender import AcceptanceFileGmailSender, GmailApiSender


def test_acceptance_file_sender_is_explicit_and_auditable(tmp_path):
    outbox = tmp_path / "fake-gmail.jsonl"
    sender = AcceptanceFileGmailSender(outbox)
    sender.validate()

    message_id = sender("recipient@example.test", "subject", '{"result":true}', [])

    record = json.loads(outbox.read_text(encoding="utf-8"))
    assert message_id.startswith("FAKE_ACCEPTANCE_GMAIL_")
    assert record["delivery_kind"] == "FAKE_ACCEPTANCE_ONLY"
    assert record["message_id"] == message_id


def test_real_gmail_sender_fails_preflight_without_oauth_token(tmp_path):
    with pytest.raises(RuntimeError, match="OAuth token missing"):
        GmailApiSender(tmp_path / "missing-token.json").validate()
