"""Coverage contracts for the Gmail report module in the 3-process design."""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Gmail report module
# ---------------------------------------------------------------------------


def test_gmail_sender_validate_missing_file(tmp_path):
    from cop_worker.gmail.sender import GmailApiSender

    sender = GmailApiSender(tmp_path / "missing.json")
    with pytest.raises(RuntimeError, match="missing"):
        sender.validate()


def test_gmail_sender_validate_empty_token(tmp_path):
    import json

    token_path = tmp_path / "empty.json"
    token_path.write_text(json.dumps({}), encoding="utf-8")
    from cop_worker.gmail.sender import GmailApiSender

    sender = GmailApiSender(token_path)
    with pytest.raises(RuntimeError):
        sender.validate()


def test_acceptance_file_sender_writes_record(tmp_path):
    from cop_worker.gmail.sender import AcceptanceFileGmailSender

    outbox = tmp_path / "outbox.jsonl"
    sender = AcceptanceFileGmailSender(outbox)
    sender.validate()
    msg_id = sender("to@example.com", "subject", "body", [])
    assert msg_id.startswith("FAKE_ACCEPTANCE_GMAIL_")
    import json

    lines = outbox.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["delivery_kind"] == "FAKE_ACCEPTANCE_ONLY"
