"""Fast unit tests for league_manager gmail sender, example report plugin,
and transport-probe URL normalisation. No real Gmail/OAuth, no network.
"""

from __future__ import annotations

import json

import pytest

from league_manager.gmail.sender import AcceptanceFileGmailSender, GmailApiSender
from league_manager.protocol.transport_probe import (
    ProbeResult,
    TransportType,
    normalize_mcp_base_url,
)
from league_manager.reports.example_plugin import ExampleCustomPlugin

# --- gmail sender -----------------------------------------------------------


def test_acceptance_file_sender_writes_fake_record(tmp_path):
    outbox = tmp_path / "outbox.jsonl"
    sender = AcceptanceFileGmailSender(outbox)
    sender.validate()  # creates parent, probes writability
    mid = sender("to@x.com", "Result", "body text", [])
    assert mid.startswith("FAKE_ACCEPTANCE_GMAIL_")
    record = json.loads(outbox.read_text().strip())
    assert record["to"] == "to@x.com" and record["delivery_kind"] == "FAKE_ACCEPTANCE_ONLY"


def test_gmail_api_sender_validate_missing_token(tmp_path):
    with pytest.raises(RuntimeError, match="token missing"):
        GmailApiSender(tmp_path / "nope.json").validate()


def test_gmail_api_sender_validate_empty_token(tmp_path):
    tok = tmp_path / "token.json"
    tok.write_text(json.dumps({"scopes": []}))
    with pytest.raises(RuntimeError, match="neither token nor refresh_token"):
        GmailApiSender(tok).validate()


def test_gmail_api_sender_validate_ok(tmp_path):
    tok = tmp_path / "token.json"
    tok.write_text(json.dumps({"refresh_token": "r"}))
    GmailApiSender(tok).validate()  # must not raise


# --- example report plugin (async) ------------------------------------------


async def test_example_plugin_generates_stats(tmp_path):
    plugin = ExampleCustomPlugin()
    (tmp_path / "G1").mkdir()
    state = {
        "winner": "cop",
        "cop_position": [1, 1],
        "thief_position": [4, 5],
        "move_history": [{"cop": "N", "thief": "S"}, {"cop": "N", "thief": "E"}],
    }
    result = await plugin.generate("G1", state, str(tmp_path))
    assert result["ok"] is True
    stats = json.loads((tmp_path / "G1" / "stats.json").read_text())
    assert stats["winner"] == "cop" and stats["total_turns"] == 2
    assert stats["final_distance"] == abs(1 - 4) + abs(1 - 5)
    assert stats["cop_move_frequency"]["N"] == 2


async def test_example_plugin_error_path_returns_not_ok(tmp_path):
    plugin = ExampleCustomPlugin()
    # game_dir/game_id does not exist → open() fails → ok False, no raise
    result = await plugin.generate("MISSING", {"move_history": []}, str(tmp_path / "absent"))
    assert result["ok"] is False and result["destination"] is None


# --- transport-probe URL normalisation --------------------------------------


def test_normalize_strips_exact_mcp_and_sse_suffix():
    assert normalize_mcp_base_url("https://team.com/mcp") == "https://team.com"
    assert normalize_mcp_base_url("https://team.com/sse") == "https://team.com"


def test_normalize_preserves_custom_path_and_host():
    # the classic rstrip('/mcp') bug would corrupt this host; it must not
    assert normalize_mcp_base_url("https://team.com/custom") == "https://team.com/custom"
    assert normalize_mcp_base_url("https://teammcp.com/") == "https://teammcp.com"


def test_normalize_passes_stdio_through():
    assert normalize_mcp_base_url("stdio://run-server") == "stdio://run-server"


def test_probe_result_dataclass_defaults():
    pr = ProbeResult(TransportType.SSE, "https://x", "https://x/sse", 1.5)
    assert pr.transport == TransportType.SSE and pr.stdio_command == ()
