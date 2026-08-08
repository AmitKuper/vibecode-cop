"""RuntimeMode, mcp_server, and __main__ dispatch contracts."""

from __future__ import annotations

import pytest

from cop_worker.runtime_mode import RuntimeMode


def test_runtime_mode_values():
    assert RuntimeMode.COUNTED.value == "counted"
    assert RuntimeMode.WARMUP.value == "warmup"
    assert RuntimeMode.DEVELOPMENT.value == "development"


def test_runtime_mode_from_string():
    assert RuntimeMode("counted") is RuntimeMode.COUNTED
    assert RuntimeMode("development") is RuntimeMode.DEVELOPMENT


def test_mcp_server_start_gamelet_returns_ok():
    import cop_worker.mcp_server as ms

    _VALID_TERMS = {
        "board_size": 7,
        "smell_grid_size": 5,
        "max_steps": 35,
        "survival_threshold": 35,
        "cop_barrier_quota": 2,
        "capture_radius": 0,
        "decay_per_step": 0.1,
        "emit_intensity": 0.9,
        "barriers_max": 14,
        "num_games": 6,
    }
    ms._GAMELETS.clear()
    result = ms.start_gamelet(
        game_uid="cli_test_series",
        sub_game_number=1,
        terms=_VALID_TERMS,
        opponent_group="OPP_GROUP",
        role="thief",
    )
    assert result.get("ok") is True
    assert ("cli_test_series", 1) in ms._GAMELETS
    ms._GAMELETS.clear()


def test_mcp_server_duplicate_start_gamelet_raises():
    import cop_worker.mcp_server as ms
    from cop_worker.gamelet import GameletError

    _VALID_TERMS = {
        "board_size": 7,
        "smell_grid_size": 5,
        "max_steps": 35,
        "survival_threshold": 35,
        "cop_barrier_quota": 2,
        "capture_radius": 0,
        "decay_per_step": 0.1,
        "emit_intensity": 0.9,
        "barriers_max": 14,
        "num_games": 6,
    }
    ms._GAMELETS.clear()
    ms.start_gamelet("dup_cli", 1, _VALID_TERMS, "OPP", "thief")
    with pytest.raises(GameletError, match="already exists"):
        ms.start_gamelet("dup_cli", 1, _VALID_TERMS, "OPP", "thief")
    ms._GAMELETS.clear()


def test_mcp_server_get_gamelets_empty_initially():
    import cop_worker.mcp_server as ms

    ms._GAMELETS.clear()
    assert len(ms._GAMELETS) == 0


def test_acceptance_file_gmail_sender_used_when_no_token(tmp_path):
    from cop_worker.gmail.sender import AcceptanceFileGmailSender

    outbox = tmp_path / "outbox.jsonl"
    sender = AcceptanceFileGmailSender(outbox)
    sender.validate()
    msg_id = sender("to@example.com", "subject", "body", [])
    assert msg_id.startswith("FAKE_ACCEPTANCE_GMAIL_")


def test_gmail_api_sender_rejects_missing_token(tmp_path):
    from cop_worker.gmail.sender import GmailApiSender

    sender = GmailApiSender(tmp_path / "missing.json")
    with pytest.raises(RuntimeError):
        sender.validate()
