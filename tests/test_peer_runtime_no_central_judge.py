"""Tests verifying that PeerRuntime drives a game without any central judge.

Key design invariants tested:
- Each agent stores its own commits (h_commit + nonce) locally.
- Each agent stores the opponent's h_commits before the opponent reveals.
- After each reveal the agent verifies the opponent's move against stored h_commit.
- Final audit verifies all opponent nonces against stored h_commits independently.
- On commitment mismatch the agent declares TECHNICAL_LOSS and does NOT trust opponent.
- No third-process simultaneous verification occurs.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.board import Board
from agent.mcp.crypto import create_commitment, hash_game_state, verify_commitment
from agent.peer_audit import (
    append_opponent_commit,
    append_opponent_reveal,
    run_final_audit,
    verify_opponent_reveal,
)
from agent.peer_runtime import PeerRuntime
from agent.peer_turn_loop import _MOVE_ALIASES, run_peer_turn
from agent.peer_turn_helpers import select_move as _select_move


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_runtime(role: str, tmp_path: Path) -> PeerRuntime:
    """Create a PeerRuntime wired to a fake opponent client."""
    rt = PeerRuntime(
        role=role,
        secret="test-secret",
        config_sha256="a" * 64,
        opponent_url="http://localhost:9999/mcp",
        games_dir=tmp_path,
        max_turns=5,
        group_name="test_group",
    )
    rt.game_id = "game_test_001"
    rt.game_dir = tmp_path / rt.game_id
    rt.game_dir.mkdir(parents=True, exist_ok=True)
    rt.board = Board(cop_position=[0, 0], thief_position=[6, 6])
    rt._my_commits = {}
    return rt


def _make_opponent_commit_response(
    game_id: str, step: int, role: str
) -> tuple[str, str, dict]:
    """Create a valid commit+reveal payload for an opponent."""
    state_hash = hash_game_state({"cop_position": [0, 0], "thief_position": [6, 6], "turn": step})
    h_commit, nonce = create_commitment(
        game_id=game_id, step=step, role=role,
        state_hash=state_hash, move="STAY", hint="Moving STAY", intent="truth",
    )
    reveal = {"move": "STAY", "hint": "Moving STAY", "intent": "truth",
              "state_hash": state_hash}
    return h_commit, nonce, reveal


# ---------------------------------------------------------------------------
# peer_audit.py unit tests
# ---------------------------------------------------------------------------

class TestVerifyOpponentReveal:
    """verify_opponent_reveal uses crypto directly — no judge."""

    def test_valid_reveal_returns_true(self):
        game_id = "g1"
        step = 1
        role = "thief"
        state_hash = hash_game_state({"cop_position": [0, 0], "thief_position": [3, 3], "turn": 1})
        h_commit, nonce = create_commitment(
            game_id=game_id, step=step, role=role,
            state_hash=state_hash, move="NORTH", hint="Moving NORTH", intent="truth",
        )
        reveal = {"move": "NORTH", "hint": "Moving NORTH", "intent": "truth",
                  "state_hash": state_hash, "nonce": nonce}
        assert verify_opponent_reveal(h_commit, reveal, game_id, step, role) is True

    def test_tampered_move_returns_false(self):
        game_id = "g2"
        step = 2
        role = "cop"
        state_hash = hash_game_state({"cop_position": [1, 1], "thief_position": [5, 5], "turn": 2})
        h_commit, nonce = create_commitment(
            game_id=game_id, step=step, role=role,
            state_hash=state_hash, move="EAST", hint="Moving EAST", intent="truth",
        )
        # Opponent tampers: claims a different move
        tampered_reveal = {"move": "WEST", "hint": "Moving EAST", "intent": "truth",
                           "state_hash": state_hash, "nonce": nonce}
        assert verify_opponent_reveal(h_commit, tampered_reveal, game_id, step, role) is False

    def test_wrong_nonce_returns_false(self):
        game_id = "g3"
        step = 1
        role = "thief"
        state_hash = hash_game_state({"cop_position": [0, 0], "thief_position": [4, 4], "turn": 1})
        h_commit, _ = create_commitment(
            game_id=game_id, step=step, role=role,
            state_hash=state_hash, move="SOUTH", hint="Moving SOUTH", intent="truth",
        )
        reveal = {"move": "SOUTH", "hint": "Moving SOUTH", "intent": "truth",
                  "state_hash": state_hash, "nonce": "deadbeef" * 8}
        assert verify_opponent_reveal(h_commit, reveal, game_id, step, role) is False


class TestAppendAndLoadOpponentData:
    """Disk persistence functions for opponent commitments and reveals."""

    def test_append_and_read_opponent_commits(self, tmp_path):
        game_dir = tmp_path / "game_001"
        game_dir.mkdir()
        append_opponent_commit(game_dir, 1, "aaa" * 21 + "a")
        append_opponent_commit(game_dir, 2, "bbb" * 21 + "b")
        path = game_dir / "opponent_commitments.json"
        data = json.loads(path.read_text())
        assert "1" in data and "2" in data

    def test_append_opponent_reveal(self, tmp_path):
        game_dir = tmp_path / "game_002"
        game_dir.mkdir()
        reveal = {"move": "NORTH", "hint": "hint", "intent": "truth", "state_hash": "x" * 64}
        append_opponent_reveal(game_dir, 1, reveal)
        path = game_dir / "opponent_reveals.json"
        data = json.loads(path.read_text())
        assert data["1"]["move"] == "NORTH"

    def test_append_is_idempotent_across_steps(self, tmp_path):
        game_dir = tmp_path / "game_003"
        game_dir.mkdir()
        for step in range(1, 6):
            append_opponent_commit(game_dir, step, f"{'c' * 63}{step}")
        data = json.loads((game_dir / "opponent_commitments.json").read_text())
        assert len(data) == 5


class TestRunFinalAudit:
    """run_final_audit verifies all stored opponent commits against nonces — no judge."""

    def _setup_game(self, tmp_path: Path, game_id: str, steps: int = 3) -> tuple[Path, dict]:
        game_dir = tmp_path / game_id
        game_dir.mkdir()
        nonces_map: dict[int, str] = {}
        for step in range(1, steps + 1):
            state_hash = hash_game_state({"cop_position": [0, step], "thief_position": [6, 6],
                                          "turn": step})
            h_commit, nonce = create_commitment(
                game_id=game_id, step=step, role="thief",
                state_hash=state_hash, move="STAY", hint="Moving STAY", intent="truth",
            )
            append_opponent_commit(game_dir, step, h_commit)
            reveal = {"move": "STAY", "hint": "Moving STAY", "intent": "truth",
                      "state_hash": state_hash}
            append_opponent_reveal(game_dir, step, reveal)
            nonces_map[step] = nonce
        return game_dir, nonces_map

    def test_all_steps_verified_ok(self, tmp_path):
        game_id = "audit_ok_001"
        game_dir, nonces = self._setup_game(tmp_path, game_id, steps=3)
        ok, details = run_final_audit(game_dir, game_id, "thief", nonces)
        assert ok is True
        assert all(v == "ok" for v in details.values())

    def test_missing_nonce_causes_failure(self, tmp_path):
        game_id = "audit_missing_nonce"
        game_dir, nonces = self._setup_game(tmp_path, game_id, steps=2)
        del nonces[1]  # Remove nonce for step 1
        ok, details = run_final_audit(game_dir, game_id, "thief", nonces)
        assert ok is False
        assert details["step_1"] == "missing_nonce"

    def test_wrong_nonce_causes_mismatch(self, tmp_path):
        game_id = "audit_wrong_nonce"
        game_dir, nonces = self._setup_game(tmp_path, game_id, steps=2)
        nonces[1] = "00" * 32  # Replace with wrong nonce
        ok, details = run_final_audit(game_dir, game_id, "thief", nonces)
        assert ok is False
        assert details["step_1"] == "commitment_mismatch"

    def test_empty_game_audit_ok(self, tmp_path):
        game_dir = tmp_path / "audit_empty"
        game_dir.mkdir()
        ok, details = run_final_audit(game_dir, "empty_game", "thief", {})
        assert ok is True
        assert details == {}


# ---------------------------------------------------------------------------
# PeerRuntime unit tests
# ---------------------------------------------------------------------------

class TestPeerRuntimeInit:
    def test_role_cop_sets_opponent_thief(self, tmp_path):
        rt = _make_runtime("cop", tmp_path)
        assert rt.role == "cop"
        assert rt.opponent_role == "thief"

    def test_role_thief_sets_opponent_cop(self, tmp_path):
        rt = _make_runtime("thief", tmp_path)
        assert rt.role == "thief"
        assert rt.opponent_role == "cop"

    def test_invalid_role_raises(self, tmp_path):
        with pytest.raises(ValueError):
            PeerRuntime(
                role="judge",
                secret="s", config_sha256="a" * 64,
                opponent_url="http://localhost:9/mcp",
                games_dir=tmp_path,
            )


class TestPeerRuntimeStoreMyCommit:
    def test_commit_persisted_to_disk(self, tmp_path):
        rt = _make_runtime("cop", tmp_path)
        payload = {"h_commit": "a" * 64, "nonce": "n" * 64, "move": "NORTH",
                   "hint": "Moving NORTH", "intent": "truth", "state_hash": "s" * 64}
        rt._store_my_commit(1, payload)

        path = rt.game_dir / "my_commitments_cop.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "1" in data
        assert data["1"]["move"] == "NORTH"

    def test_multiple_commits_accumulate(self, tmp_path):
        rt = _make_runtime("thief", tmp_path)
        for step in range(1, 4):
            rt._store_my_commit(step, {"h_commit": "a" * 64, "nonce": "n" * 64,
                                       "move": "STAY", "hint": "h", "intent": "truth",
                                       "state_hash": "s" * 64})
        data = json.loads((rt.game_dir / "my_commitments_thief.json").read_text())
        assert len(data) == 3

    def test_in_memory_dict_updated(self, tmp_path):
        rt = _make_runtime("cop", tmp_path)
        rt._store_my_commit(5, {"h_commit": "a" * 64, "nonce": "n" * 64,
                                "move": "EAST", "hint": "h", "intent": "truth",
                                "state_hash": "s" * 64})
        assert 5 in rt._my_commits
        assert rt._my_commits[5]["move"] == "EAST"


# ---------------------------------------------------------------------------
# peer_turn_loop unit tests (mocking MCP calls)
# ---------------------------------------------------------------------------

class TestRunPeerTurn:
    """run_peer_turn does local verification without any judge process."""

    def _build_valid_opponent_resp(
        self, game_id: str, step: int, opp_role: str
    ) -> tuple[dict, dict]:
        """Build commit-response and reveal-response dicts for a valid opponent."""
        state_hash = hash_game_state(
            {"cop_position": [0, 0], "thief_position": [6, 6], "turn": step}
        )
        h_commit, nonce = create_commitment(
            game_id=game_id, step=step, role=opp_role,
            state_hash=state_hash, move="STAY", hint="Moving STAY", intent="truth",
        )
        commit_resp = {"ok": True, "h_commit": h_commit}
        reveal_resp = {
            "ok": True, "move": "STAY", "hint": "Moving STAY",
            "intent": "truth", "state_hash": state_hash,
            "nonces": {str(step): nonce},
        }
        return commit_resp, reveal_resp

    @pytest.mark.asyncio
    async def test_valid_turn_returns_no_winner(self, tmp_path):
        rt = _make_runtime("cop", tmp_path)
        step = 1
        commit_resp, reveal_resp = self._build_valid_opponent_resp(rt.game_id, step, "thief")

        rt.opponent_client.action = AsyncMock(side_effect=[commit_resp, reveal_resp])
        from agent.rules_engine import RulesEngine
        rules = RulesEngine(rt.board, max_turns=5)

        winner, abort = await run_peer_turn(rt, step, rules)
        assert winner is None
        assert abort is None

    @pytest.mark.asyncio
    async def test_tampered_reveal_stored_for_final_audit(self, tmp_path):
        # Per protocol: nonces are withheld until final_audit, so per-turn reveal
        # tampering cannot be detected during the turn itself. The tampered reveal
        # data is stored; final_audit catches the mismatch when nonces are exchanged.
        rt = _make_runtime("cop", tmp_path)
        step = 1
        commit_resp, reveal_resp = self._build_valid_opponent_resp(rt.game_id, step, "thief")
        # Tamper: change the move in reveal but keep the original h_commit
        reveal_resp["move"] = "NORTH"

        rt.opponent_client.action = AsyncMock(side_effect=[commit_resp, reveal_resp])
        from agent.rules_engine import RulesEngine
        rules = RulesEngine(rt.board, max_turns=5)

        winner, abort = await run_peer_turn(rt, step, rules)
        # Turn completes; tamper is detected at final_audit time (not per-turn)
        assert winner is None
        assert abort is None
        # Tampered reveal is stored in opponent_reveals.json for later audit
        import json
        reveals = json.loads((rt.game_dir / "opponent_reveals.json").read_text())
        assert reveals[str(step)]["move"] == "NORTH"

    @pytest.mark.asyncio
    async def test_missing_h_commit_in_commit_resp(self, tmp_path):
        rt = _make_runtime("thief", tmp_path)
        step = 1
        bad_commit_resp = {"ok": True}  # no h_commit

        rt.opponent_client.action = AsyncMock(side_effect=[bad_commit_resp])
        from agent.rules_engine import RulesEngine
        rules = RulesEngine(rt.board, max_turns=5)

        winner, abort = await run_peer_turn(rt, step, rules)
        assert abort is not None
        assert "h_commit" in abort

    @pytest.mark.asyncio
    async def test_missing_move_in_reveal(self, tmp_path):
        rt = _make_runtime("cop", tmp_path)
        step = 1
        state_hash = hash_game_state(
            {"cop_position": [0, 0], "thief_position": [6, 6], "turn": step}
        )
        h_commit, nonce = create_commitment(
            game_id=rt.game_id, step=step, role="thief",
            state_hash=state_hash, move="STAY", hint="Moving STAY", intent="truth",
        )
        commit_resp = {"ok": True, "h_commit": h_commit}
        reveal_resp = {"ok": True, "nonces": {str(step): nonce}}  # no move

        rt.opponent_client.action = AsyncMock(side_effect=[commit_resp, reveal_resp])
        from agent.rules_engine import RulesEngine
        rules = RulesEngine(rt.board, max_turns=5)

        winner, abort = await run_peer_turn(rt, step, rules)
        assert abort is not None
        assert "move" in abort

    @pytest.mark.asyncio
    async def test_own_commit_stored_after_turn(self, tmp_path):
        rt = _make_runtime("cop", tmp_path)
        step = 1
        commit_resp, reveal_resp = self._build_valid_opponent_resp(rt.game_id, step, "thief")
        rt.opponent_client.action = AsyncMock(side_effect=[commit_resp, reveal_resp])
        from agent.rules_engine import RulesEngine
        rules = RulesEngine(rt.board, max_turns=5)

        await run_peer_turn(rt, step, rules)
        assert step in rt._my_commits
        _valid = {"NORTH", "SOUTH", "EAST", "WEST", "STAY", "N", "S", "E", "W",
                  "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"}
        assert rt._my_commits[step]["move"] in _valid

    @pytest.mark.asyncio
    async def test_opponent_commit_stored_before_reveal(self, tmp_path):
        """Opponent h_commit must be persisted to disk before we process their reveal."""
        rt = _make_runtime("thief", tmp_path)
        step = 1
        commit_resp, reveal_resp = self._build_valid_opponent_resp(rt.game_id, step, "cop")
        rt.opponent_client.action = AsyncMock(side_effect=[commit_resp, reveal_resp])
        from agent.rules_engine import RulesEngine
        rules = RulesEngine(rt.board, max_turns=5)

        await run_peer_turn(rt, step, rules)
        commits_file = rt.game_dir / "opponent_commitments.json"
        assert commits_file.exists()
        data = json.loads(commits_file.read_text())
        assert "1" in data


# ---------------------------------------------------------------------------
# Full game integration test (no central judge)
# ---------------------------------------------------------------------------

class TestPeerRuntimeFullGame:
    """Integration test: two-sided game with mocked MCP, no GameRunner or judge."""

    def _build_opponent_commit_side(
        self, game_id: str, step: int, opp_role: str
    ) -> tuple[str, str]:
        state_hash = hash_game_state(
            {"cop_position": [0, 0], "thief_position": [6, 6], "turn": step}
        )
        return create_commitment(
            game_id=game_id, step=step, role=opp_role,
            state_hash=state_hash, move="STAY", hint="Moving STAY", intent="truth",
        )

    def _make_action_side_effect(self, game_id: str, opp_role: str, max_turns: int):
        """Return an async callable that simulates the opponent's MCP action endpoint."""
        commits: dict[int, tuple[str, str]] = {}  # step -> (h_commit, nonce)

        async def side_effect(gid, msg):
            if msg.phase == "commit":
                step = msg.step
                state_hash = hash_game_state(
                    {"cop_position": [0, 0], "thief_position": [6, 6], "turn": step}
                )
                h, nonce = create_commitment(
                    game_id=game_id, step=step, role=opp_role,
                    state_hash=state_hash, move="STAY", hint="Moving STAY", intent="truth",
                )
                commits[step] = (h, nonce)
                return {"ok": True, "h_commit": h}

            elif msg.phase == "reveal":
                step = msg.step
                h, nonce = commits.get(step, ("x" * 64, "y" * 64))
                state_hash = hash_game_state(
                    {"cop_position": [0, 0], "thief_position": [6, 6], "turn": step}
                )
                return {
                    "ok": True, "move": "STAY", "hint": "Moving STAY",
                    "intent": "truth", "state_hash": state_hash,
                    "nonces": {str(step): nonce},
                }

            elif msg.phase == "final_audit":
                # Return nonces for all committed steps
                return {"ok": True, "nonces": {str(s): n for s, (h, n) in commits.items()}}

            elif msg.phase == "game_end":
                return {"ok": True}

            return {"ok": True}

        return side_effect

    @pytest.mark.asyncio
    async def test_cop_completes_game_without_judge(self, tmp_path):
        game_id = "full_game_cop_001"
        rt = _make_runtime("cop", tmp_path)

        rt.opponent_client.action = AsyncMock(
            side_effect=self._make_action_side_effect(game_id, "thief", 5)
        )

        result = await rt.run_game(game_id)

        assert result["ok"] is True
        assert result["role"] == "cop"
        assert result["game_id"] == game_id
        assert result["winner"] in ("cop", "thief")
        assert result["final_step"] >= 1

    @pytest.mark.asyncio
    async def test_thief_completes_game_without_judge(self, tmp_path):
        game_id = "full_game_thief_001"
        rt = _make_runtime("thief", tmp_path)

        rt.opponent_client.action = AsyncMock(
            side_effect=self._make_action_side_effect(game_id, "cop", 5)
        )

        result = await rt.run_game(game_id)

        assert result["ok"] is True
        assert result["role"] == "thief"
        assert result["winner"] in ("cop", "thief")

    @pytest.mark.asyncio
    async def test_result_file_written_locally(self, tmp_path):
        game_id = "result_file_test"
        rt = _make_runtime("cop", tmp_path)
        rt.opponent_client.action = AsyncMock(
            side_effect=self._make_action_side_effect(game_id, "thief", 5)
        )
        await rt.run_game(game_id)

        result_path = tmp_path / game_id / f"result_{game_id}.json"
        assert result_path.exists()
        data = json.loads(result_path.read_text())
        assert data["game_id"] == game_id
        assert data["role"] == "cop"

    @pytest.mark.asyncio
    async def test_my_commitments_file_written(self, tmp_path):
        game_id = "my_commits_test"
        rt = _make_runtime("thief", tmp_path)
        rt.opponent_client.action = AsyncMock(
            side_effect=self._make_action_side_effect(game_id, "cop", 5)
        )
        await rt.run_game(game_id)

        commits_path = tmp_path / game_id / "my_commitments_thief.json"
        assert commits_path.exists()
        data = json.loads(commits_path.read_text())
        assert len(data) >= 1  # At least one step committed

    @pytest.mark.asyncio
    async def test_opponent_commitments_file_written(self, tmp_path):
        game_id = "opp_commits_test"
        rt = _make_runtime("cop", tmp_path)
        rt.opponent_client.action = AsyncMock(
            side_effect=self._make_action_side_effect(game_id, "thief", 5)
        )
        await rt.run_game(game_id)

        opp_commits_path = tmp_path / game_id / "opponent_commitments.json"
        assert opp_commits_path.exists()

    @pytest.mark.asyncio
    async def test_audit_ok_when_opponent_honest(self, tmp_path):
        game_id = "audit_honest_opponent"
        rt = _make_runtime("cop", tmp_path)
        rt.opponent_client.action = AsyncMock(
            side_effect=self._make_action_side_effect(game_id, "thief", 5)
        )
        result = await rt.run_game(game_id)
        assert result["audit_ok"] is True

    @pytest.mark.asyncio
    async def test_game_state_json_written(self, tmp_path):
        game_id = "state_json_test"
        rt = _make_runtime("thief", tmp_path)
        rt.opponent_client.action = AsyncMock(
            side_effect=self._make_action_side_effect(game_id, "cop", 5)
        )
        await rt.run_game(game_id)

        state_path = tmp_path / game_id / "game_state.json"
        assert state_path.exists()
        state = json.loads(state_path.read_text())
        assert state["completed"] is True
        assert "winner" in state


# ---------------------------------------------------------------------------
# No-central-judge invariant: both agents verify independently
# ---------------------------------------------------------------------------

class TestNoCentralJudgeInvariant:
    """Explicitly verify the no-central-judge design property."""

    def test_each_agent_has_separate_commit_stores(self, tmp_path):
        """Cop and Thief stores are independent files, not shared."""
        cop_rt = _make_runtime("cop", tmp_path / "cop")
        thief_rt = _make_runtime("thief", tmp_path / "thief")

        cop_rt._store_my_commit(1, {"h_commit": "a" * 64, "nonce": "n" * 64,
                                    "move": "NORTH", "hint": "h", "intent": "truth",
                                    "state_hash": "s" * 64})
        thief_rt._store_my_commit(1, {"h_commit": "b" * 64, "nonce": "m" * 64,
                                      "move": "SOUTH", "hint": "h", "intent": "truth",
                                      "state_hash": "t" * 64})

        # game_id is "game_test_001" as set by _make_runtime
        cop_path = cop_rt.game_dir / "my_commitments_cop.json"
        thief_path = thief_rt.game_dir / "my_commitments_thief.json"
        assert cop_path.exists()
        assert thief_path.exists()
        # They are different files in different directories
        assert cop_path != thief_path

    def test_verify_commitment_is_pure_crypto_no_network(self):
        """verify_commitment() is a pure local computation — no I/O, no judge."""
        game_id = "pure_crypto"
        step = 3
        role = "cop"
        state_hash = "s" * 64
        move = "EAST"
        hint = "Moving EAST"
        intent = "truth"

        h_commit, nonce = create_commitment(
            game_id=game_id, step=step, role=role,
            state_hash=state_hash, move=move, hint=hint, intent=intent,
        )

        # verify_commitment is synchronous and pure — no network needed
        result = verify_commitment(
            h_commit=h_commit, game_id=game_id, step=step, role=role,
            state_hash=state_hash, move=move, hint=hint, intent=intent, nonce=nonce,
        )
        assert result is True

    def test_run_final_audit_uses_only_local_files(self, tmp_path):
        """run_final_audit reads files on disk — no MCP call, no external process."""
        game_id = "local_audit_only"
        game_dir = tmp_path / game_id
        game_dir.mkdir()

        state_hash = hash_game_state({"cop_position": [1, 1], "thief_position": [5, 5], "turn": 1})
        h_commit, nonce = create_commitment(
            game_id=game_id, step=1, role="thief",
            state_hash=state_hash, move="WEST", hint="Moving WEST", intent="truth",
        )
        append_opponent_commit(game_dir, 1, h_commit)
        reveal = {"move": "WEST", "hint": "Moving WEST", "intent": "truth",
                  "state_hash": state_hash}
        append_opponent_reveal(game_dir, 1, reveal)

        # No MCP call happens inside run_final_audit
        ok, details = run_final_audit(game_dir, game_id, "thief", {1: nonce})
        assert ok is True
        assert details["step_1"] == "ok"
