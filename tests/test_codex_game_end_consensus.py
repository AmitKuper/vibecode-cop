"""Counted game-end evidence must be independent and use the locked adapter."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.audit.audit_summary import AuditSummary, create_signed_audit_summary
from agent.board import Board
from agent.peer_agent_passive import handle_passive_game_end
from agent.peer_runtime_audit import do_final_audit, notify_game_end
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


def test_final_audit_runtime_identity_and_missing_summary_branches(tmp_path):
    local_private, local_public = generate_key_pair()
    remote_private, remote_public = generate_key_pair()
    game_id = "series_fixture_g01"
    remote_signed = create_signed_audit_summary(
        AuditSummary(
            game_uid=game_id,
            gamelet=1,
            config_hash="c" * 64,
            audit_status="PASSED",
            public_key_hex=remote_public.hex(),
        ),
        remote_private,
    )

    def runtime(*, remote_identity=True):
        return SimpleNamespace(
            protocol_adapter=object(),
            counted_mode=True,
            _signing_private_key=local_private,
            _signing_public_key=local_public,
            _signing_key_id="local",
            _local_step0={
                game_id: SimpleNamespace(
                    declaration=SimpleNamespace(declaration_hash=lambda: "declaration")
                )
            },
            _remote_step0=(
                {
                    game_id: SimpleNamespace(
                        declaration=SimpleNamespace(public_key_hex=remote_public.hex())
                    )
                }
                if remote_identity
                else {}
            ),
            _local_audit_summaries={},
            _remote_audit_summaries={},
            orchestrator=SimpleNamespace(
                get_journal=lambda _gamelet: SimpleNamespace(transcript_root=lambda: "root")
            ),
            board=SimpleNamespace(to_dict=lambda: {"turn": 1}),
        )

    coordinator = MagicMock()
    response = {
        "nonces": {},
        "signed_audit_summary": json.dumps(remote_signed.to_dict()),
    }
    with (
        patch("agent.mcp.coordinator.get_coordinator", return_value=coordinator),
        patch(
            "agent.peer_runtime_audit.run_final_audit",
            return_value=(True, {"audit_status": "PASSED"}),
        ),
        patch("agent.peer_runtime_audit.load_opponent_commits", return_value={}),
        patch("agent.peer_turn_helpers._call_adapted_phase", new=AsyncMock(return_value=response)),
    ):
        current = runtime()
        ok, details = asyncio.run(
            do_final_audit(
                SimpleNamespace(),
                game_id,
                "cop",
                "c" * 64,
                {},
                tmp_path,
                "thief",
                1,
                lambda: "2026-08-05T00:00:00Z",
                gamelet=1,
                runtime=current,
            )
        )
    assert ok and details["opponent_audit_verified"] is True
    assert game_id in current._remote_audit_summaries
    coordinator.on_final_audit_complete.assert_called_once()

    with (
        patch("agent.mcp.coordinator.get_coordinator", return_value=coordinator),
        patch(
            "agent.peer_runtime_audit.run_final_audit",
            return_value=(True, {"audit_status": "PASSED"}),
        ),
        patch("agent.peer_runtime_audit.load_opponent_commits", return_value={}),
        patch("agent.peer_turn_helpers._call_adapted_phase", new=AsyncMock(return_value=response)),
    ):
        ok, details = asyncio.run(
            do_final_audit(
                SimpleNamespace(),
                game_id,
                "cop",
                "c" * 64,
                {},
                tmp_path,
                "thief",
                1,
                lambda: "2026-08-05T00:00:00Z",
                gamelet=1,
                runtime=runtime(remote_identity=False),
            )
        )
    assert ok is False and "missing remote Step-0" in details["opponent_audit_parse_error"]

    with (
        patch("agent.mcp.coordinator.get_coordinator", return_value=coordinator),
        patch(
            "agent.peer_runtime_audit.run_final_audit",
            return_value=(True, {"audit_status": "PASSED"}),
        ),
        patch("agent.peer_runtime_audit.load_opponent_commits", return_value={}),
        patch(
            "agent.peer_turn_helpers._call_adapted_phase",
            new=AsyncMock(return_value={"nonces": {}}),
        ),
    ):
        ok, details = asyncio.run(
            do_final_audit(
                SimpleNamespace(),
                game_id,
                "cop",
                "c" * 64,
                {},
                tmp_path,
                "thief",
                1,
                lambda: "2026-08-05T00:00:00Z",
                gamelet=1,
                runtime=runtime(),
            )
        )
    assert ok is False and details["opponent_audit_parse_error"] == "missing signed audit summary"
