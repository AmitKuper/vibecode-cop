"""Failure and success branches for Gmail senders (league_manager variant)."""

from __future__ import annotations

import json

import pytest

from cop_worker.gmail.sender import AcceptanceFileGmailSender, GmailApiSender


def test_gmail_sender_validation_and_attachment_rejection(tmp_path) -> None:
    missing = GmailApiSender(tmp_path / "missing.json")
    with pytest.raises(RuntimeError, match="token missing"):
        missing.validate()

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{}", encoding="utf-8")
    invalid = GmailApiSender(invalid_path)
    with pytest.raises(RuntimeError, match="neither token nor refresh_token"):
        invalid.validate()

    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps({"refresh_token": "refresh"}), encoding="utf-8")
    sender = GmailApiSender(token_path)
    sender.validate()
    with pytest.raises(RuntimeError, match="untyped attachments"):
        sender("to@example.com", "subject", "body", [tmp_path / "file"])


def test_gmail_sender_calls_real_api_boundary(monkeypatch, tmp_path) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps({"token": "access"}), encoding="utf-8")
    sender = GmailApiSender(token_path)
    monkeypatch.setattr(
        "league_manager.reports.gmail_send.load_oauth_credentials",
        lambda path: ("credentials", path),
    )

    def fake_send(message, credentials):
        assert message["To"] == "to@example.com"
        assert message["Subject"] == "subject"
        assert credentials[0] == "credentials"
        return "gmail-message-id"

    monkeypatch.setattr("league_manager.reports.gmail_send.gmail_api_send", fake_send)
    assert sender("to@example.com", "subject", "body", []) == "gmail-message-id"


def test_acceptance_fake_gmail_is_explicit_deterministic_outbox(tmp_path) -> None:
    outbox = tmp_path / "nested" / "outbox.jsonl"
    sender = AcceptanceFileGmailSender(outbox)
    sender.validate()
    first = sender("to@example.com", "subject", "body", ["artifact.json"])
    second = sender("to@example.com", "subject", "body", ["artifact.json"])
    records = [json.loads(line) for line in outbox.read_text(encoding="utf-8").splitlines()]
    assert first == second
    assert len(records) == 2
    assert records[0]["delivery_kind"] == "FAKE_ACCEPTANCE_ONLY"
    assert records[0]["attachments"] == ["artifact.json"]
