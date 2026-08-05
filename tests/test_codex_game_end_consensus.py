"""Counted game-end evidence must be independent and use the locked adapter."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent.audit.audit_summary import AuditSummary, create_signed_audit_summary
from agent.board import Board
from agent.peer_agent_passive import handle_passive_game_end
from agent.peer_runtime_audit import notify_game_end
from agent.rules_engine import RulesEngine
from agent.step0.signing import generate_key_pair


def test_passive_records_only_locally_derived_terminal_outcome(tmp_path):
    private, public = generate_key_pair()
    game_id = "series_fixture_g01"
    audit = create_signed_audit_summary(
        AuditSummary(
            game_uid=game_id,
            gamelet=1,
            config_hash="c" * 64,
            audit_status="PASSED",
            public_key_hex=public.hex(),
        ),
        private,
    )
    board = Board(cop_position=[2, 2], thief_position=[2, 2])
    board.turn = 4
    runtime = SimpleNamespace(
        game_id=game_id,
        board=board,
        _local_audit_summaries={game_id: audit},
        _observed_gamelet_outcomes={},
        _gamelet_number=lambda _: 1,
    )

    response = handle_passive_game_end(
        runtime,
        game_id,
        SimpleNamespace(reason="cop"),
        [RulesEngine(board)],
    )

    assert response["ok"] is True
    assert runtime._observed_gamelet_outcomes[game_id] == {
        "gamelet": 1,
        "winner": "cop",
        "cop_score": 20,
        "thief_score": 5,
        "turns_played": 4,
    }


def test_passive_rejects_claimed_winner_that_disagrees_with_board():
    private, public = generate_key_pair()
    game_id = "series_fixture_g01"
    audit = create_signed_audit_summary(
        AuditSummary(
            game_uid=game_id,
            gamelet=1,
            config_hash="c" * 64,
            audit_status="PASSED",
            public_key_hex=public.hex(),
        ),
        private,
    )
    board = Board(cop_position=[2, 2], thief_position=[2, 2])
    runtime = SimpleNamespace(
        game_id=game_id,
        board=board,
        _local_audit_summaries={game_id: audit},
        _observed_gamelet_outcomes={},
    )

    response = handle_passive_game_end(
        runtime,
        game_id,
        SimpleNamespace(reason="thief"),
        [RulesEngine(board)],
    )

    assert response["ok"] is False
    assert "winner mismatch" in response["error"]


def test_counted_game_end_uses_locked_adapter_and_fails_closed():
    client = SimpleNamespace(action=AsyncMock())
    runtime = SimpleNamespace(
        protocol_adapter=object(),
        counted_mode=True,
        game_id="series_fixture_g01",
    )

    with patch(
        "agent.peer_turn_helpers._call_adapted_phase",
        new=AsyncMock(return_value={"ok": True}),
    ) as adapted:
        response = asyncio.run(
            notify_game_end(
                client,
                runtime.game_id,
                "cop",
                "c" * 64,
                4,
                "cop",
                lambda: "2026-08-05T00:00:00Z",
                runtime=runtime,
            )
        )
    assert response["ok"] is True
    adapted.assert_awaited_once()
    client.action.assert_not_awaited()

    with (
        patch(
            "agent.peer_turn_helpers._call_adapted_phase",
            new=AsyncMock(return_value={"ok": False, "error": "rejected"}),
        ),
        pytest.raises(RuntimeError, match="COUNTED game_end notification failed"),
    ):
        asyncio.run(
            notify_game_end(
                client,
                runtime.game_id,
                "cop",
                "c" * 64,
                4,
                "cop",
                lambda: "2026-08-05T00:00:00Z",
                runtime=runtime,
            )
        )
