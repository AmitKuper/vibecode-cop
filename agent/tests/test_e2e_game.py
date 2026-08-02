"""End-to-end local game test (R10).

Runs a complete game using GameRunner with patched MCP clients so no real agents
or network connections are needed. Verifies the full flow: handshake → commit →
reveal → move application → final audit → output file generation.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import pytest

from agent.game_runner import GameRunner
from agent.mcp.crypto import create_commitment, hash_game_state

_SECRET = "e2e-test-secret"
_CFG_SHA = "c" * 64
_MAX_TURNS = 5  # short game for tests


def _make_agent_stub(role: str):
    """Return a stateful mock that simulates one agent's MCP responses."""
    my_commitments: dict[int, dict] = {}

    async def mock_action(game_id: str, msg) -> dict:
        phase = msg.phase

        if phase == "commit":
            step = msg.step
            board = msg.board_state or {}
            state_hash = hash_game_state(
                {
                    "cop_position": board.get("cop_position", [0, 0]),
                    "thief_position": board.get("thief_position", [6, 6]),
                    "turn": board.get("turn", step - 1),
                }
            )
            move = "STAY"  # deterministic for testing
            hint = "testing"
            intent = "truth"
            h_commit, nonce = create_commitment(
                game_id=game_id,
                step=step,
                role=role,
                state_hash=state_hash,
                move=move,
                hint=hint,
                intent=intent,
            )
            my_commitments[step] = {
                "h_commit": h_commit,
                "nonce": nonce,
                "move": move,
                "hint": hint,
                "intent": intent,
                "state_hash": state_hash,
            }
            return {
                "ok": True,
                "game_id": game_id,
                "phase": "commit",
                "step": step,
                "h_commit": h_commit,
            }

        elif phase == "reveal":
            step = msg.step
            payload = my_commitments.get(step)
            if not payload:
                return {"ok": False, "error": "no stored commitment"}
            return {
                "ok": True,
                "game_id": game_id,
                "phase": "reveal",
                "step": step,
                "move": payload["move"],
                "hint": payload["hint"],
                "intent": payload["intent"],
                "state_hash": payload["state_hash"],
                "h_commit": payload["h_commit"],
            }

        elif phase == "final_audit":
            nonces = {str(s): p["nonce"] for s, p in my_commitments.items()}
            return {
                "ok": True,
                "game_id": game_id,
                "phase": "final_audit",
                "nonces": nonces,
                "verified": True,
            }

        elif phase == "game_end":
            return {"ok": True, "game_id": game_id, "phase": "game_end", "winner": msg.reason}

        elif phase == "ack":
            return {"ok": True, "game_id": game_id, "phase": "ack"}

        return {"ok": False, "error": f"Unknown phase: {phase}"}

    return mock_action


@pytest.mark.asyncio
async def test_e2e_game_completes_with_output_files():
    """Full game: GameRunner runs 5 turns, final audit passes, output files exist."""
    with TemporaryDirectory() as tmpdir:
        games_dir = Path(tmpdir)

        runner = GameRunner(
            cop_url="http://localhost:5000",
            thief_url="http://localhost:5001",
            secret=_SECRET,
            config_sha256=_CFG_SHA,
            games_dir=games_dir,
            max_turns=_MAX_TURNS,
        )

        cop_stub = _make_agent_stub("cop")
        thief_stub = _make_agent_stub("thief")

        # Patch out the MCP clients: action() and the initiator's start_game
        runner.cop_client.action = cop_stub
        runner.thief_client.action = thief_stub

        # Patch GameInitiator so handshake succeeds without real agents
        with patch("agent.game_runner.GameInitiator") as MockInitiator:  # noqa: N806
            mock_init_inst = AsyncMock()
            mock_init_inst.start_game.return_value = {"ok": True, "game_id": "test"}
            MockInitiator.return_value = mock_init_inst

            result = await runner.run_game(game_id="e2e_test_game_001")

        assert result["ok"] is True, f"Game failed: {result}"
        assert result["game_id"] == "e2e_test_game_001"
        assert result["winner"] in ("cop", "thief")
        # STAY moves → cop never catches thief → thief survives 5 turns
        assert result["winner"] == "thief"
        assert result["final_step"] == _MAX_TURNS
        assert result["audit_ok"] is True, "Final audit should pass with correct nonces"

        # Check required output files
        game_dir = games_dir / "e2e_test_game_001"
        assert (game_dir / "game_state.json").exists()
        assert (game_dir / "events.jsonl").exists()
        assert (game_dir / "declaration_e2e_test_game_001.json").exists()
        assert (game_dir / "config_e2e_test_game_001_g01.json").exists()
        assert (game_dir / "log_e2e_test_game_001_g01.json").exists()
        assert (game_dir / "result_e2e_test_game_001.json").exists()

        # Verify game_state.json content
        with open(game_dir / "game_state.json") as f:
            state = json.load(f)
        assert state["completed"] is True
        assert state["winner"] == "thief"

        # Verify result file
        with open(game_dir / "result_e2e_test_game_001.json") as f:
            result_file = json.load(f)
        assert result_file["winner"] == "thief"
        assert result_file["audit_ok"] is True
        assert "log_sha256" in result_file

        # Verify events.jsonl has entries
        events = []
        with open(game_dir / "events.jsonl") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        assert len(events) > 0
        event_types = {e["event_type"] for e in events}
        assert "game_start" in event_types
        assert "commit_received" in event_types
        assert "reveal_received" in event_types
        assert "final_audit" in event_types


@pytest.mark.asyncio
async def test_e2e_game_without_reports_still_completes():
    """Game completes even if report plugins are not configured."""
    with TemporaryDirectory() as tmpdir:
        games_dir = Path(tmpdir)
        runner = GameRunner(
            cop_url="http://localhost:5000",
            thief_url="http://localhost:5001",
            secret=_SECRET,
            config_sha256=_CFG_SHA,
            games_dir=games_dir,
            max_turns=3,
        )
        runner.cop_client.action = _make_agent_stub("cop")
        runner.thief_client.action = _make_agent_stub("thief")

        with patch("agent.game_runner.GameInitiator") as MockInitiator:  # noqa: N806
            mock_inst = AsyncMock()
            mock_inst.start_game.return_value = {"ok": True, "game_id": "test"}
            MockInitiator.return_value = mock_inst

            result = await runner.run_game(game_id="e2e_no_report_001")

        assert result["ok"] is True
        game_dir = games_dir / "e2e_no_report_001"
        assert (game_dir / "result_e2e_no_report_001.json").exists()


@pytest.mark.asyncio
async def test_e2e_handshake_failure_aborts_game():
    """If handshake fails, game aborts immediately."""
    with TemporaryDirectory() as tmpdir:
        games_dir = Path(tmpdir)
        runner = GameRunner(
            cop_url="http://localhost:5000",
            thief_url="http://localhost:5001",
            secret=_SECRET,
            config_sha256=_CFG_SHA,
            games_dir=games_dir,
            max_turns=5,
        )

        with patch("agent.game_runner.GameInitiator") as MockInitiator:  # noqa: N806
            mock_inst = AsyncMock()
            mock_inst.start_game.return_value = {"ok": False, "error": "refused"}
            MockInitiator.return_value = mock_inst

            result = await runner.run_game(game_id="e2e_fail_001")

        assert result["ok"] is False
        assert "Handshake failed" in result.get("error", "")
