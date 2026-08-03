"""Phase 2 tests: complete state commitment and six-gamelet enforcement."""

from __future__ import annotations

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

# ---------------------------------------------------------------------------
# 1. build_board_state() completeness
# ---------------------------------------------------------------------------


class TestBuildBoardState:
    def _make_runtime(
        self,
        *,
        cop_position=None,
        thief_position=None,
        turn=5,
        barriers=None,
        cop_barriers_remaining=10,
        game_id="series_20260101_000000_aabbccdd_g03",
        config_sha256="a" * 64,
    ):
        from agent.board import Board

        runtime = MagicMock()
        runtime.board = Board(
            cop_position=cop_position or [0, 0],
            thief_position=thief_position or [3, 3],
            turn=turn,
            barriers=barriers or [],
        )
        runtime._cop_barriers_remaining = cop_barriers_remaining
        runtime.game_id = game_id
        runtime.config_sha256 = config_sha256
        return runtime

    def test_includes_cop_position(self):
        from agent.peer_turn_helpers import build_board_state

        rt = self._make_runtime(cop_position=[1, 2])
        state = build_board_state(rt)
        assert state["cop_position"] == [1, 2]

    def test_includes_thief_position(self):
        from agent.peer_turn_helpers import build_board_state

        rt = self._make_runtime(thief_position=[4, 5])
        state = build_board_state(rt)
        assert state["thief_position"] == [4, 5]

    def test_includes_turn(self):
        from agent.peer_turn_helpers import build_board_state

        rt = self._make_runtime(turn=12)
        state = build_board_state(rt)
        assert state["turn"] == 12

    def test_includes_barriers(self):
        from agent.peer_turn_helpers import build_board_state

        barriers = [[2, 2], [1, 3]]
        rt = self._make_runtime(barriers=barriers)
        state = build_board_state(rt)
        assert "barriers" in state
        # must be sorted for determinism
        assert state["barriers"] == sorted(barriers)

    def test_barriers_are_sorted(self):
        from agent.peer_turn_helpers import build_board_state

        barriers = [[5, 5], [1, 1], [3, 3]]
        rt = self._make_runtime(barriers=barriers)
        state = build_board_state(rt)
        assert state["barriers"] == sorted(barriers)

    def test_includes_cop_barriers_remaining(self):
        from agent.peer_turn_helpers import build_board_state

        rt = self._make_runtime(cop_barriers_remaining=7)
        state = build_board_state(rt)
        assert state["cop_barriers_remaining"] == 7

    def test_includes_gamelet(self):
        from agent.peer_turn_helpers import build_board_state

        rt = self._make_runtime(game_id="series_abc_g04")
        state = build_board_state(rt)
        assert state["gamelet"] == 4

    def test_includes_config_sha256(self):
        from agent.peer_turn_helpers import build_board_state

        sha = "b" * 64
        rt = self._make_runtime(config_sha256=sha)
        state = build_board_state(rt)
        assert state["config_sha256"] == sha

    def test_different_barriers_produce_different_hash(self):
        from agent.mcp.crypto import hash_game_state
        from agent.peer_turn_helpers import build_board_state

        rt1 = self._make_runtime(barriers=[])
        rt2 = self._make_runtime(barriers=[[2, 2]])
        h1 = hash_game_state(build_board_state(rt1))
        h2 = hash_game_state(build_board_state(rt2))
        assert h1 != h2

    def test_different_config_sha256_produces_different_hash(self):
        from agent.mcp.crypto import hash_game_state
        from agent.peer_turn_helpers import build_board_state

        rt1 = self._make_runtime(config_sha256="a" * 64)
        rt2 = self._make_runtime(config_sha256="b" * 64)
        h1 = hash_game_state(build_board_state(rt1))
        h2 = hash_game_state(build_board_state(rt2))
        assert h1 != h2


# ---------------------------------------------------------------------------
# 2. public_transition_hash()
# ---------------------------------------------------------------------------


class TestPublicTransitionHash:
    def test_returns_64_hex_chars(self):
        from agent.mcp.crypto import public_transition_hash

        h = public_transition_hash(
            game_id="g001",
            gamelet=1,
            step=5,
            config_sha256="a" * 64,
            barriers=[],
            cop_barriers_remaining=14,
            previous_transcript_root="",
        )
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic_for_same_inputs(self):
        from agent.mcp.crypto import public_transition_hash

        kwargs = {
            "game_id": "g001",
            "gamelet": 1,
            "step": 5,
            "config_sha256": "a" * 64,
            "barriers": [[1, 2], [3, 4]],
            "cop_barriers_remaining": 10,
            "previous_transcript_root": "prev_root",
        }
        assert public_transition_hash(**kwargs) == public_transition_hash(**kwargs)

    def test_barriers_sorted_for_determinism(self):
        from agent.mcp.crypto import public_transition_hash

        base = {
            "game_id": "g001",
            "gamelet": 1,
            "step": 5,
            "config_sha256": "a" * 64,
            "cop_barriers_remaining": 10,
            "previous_transcript_root": "",
        }
        h1 = public_transition_hash(**base, barriers=[[3, 4], [1, 2]])
        h2 = public_transition_hash(**base, barriers=[[1, 2], [3, 4]])
        assert h1 == h2

    def test_different_steps_produce_different_hash(self):
        from agent.mcp.crypto import public_transition_hash

        base = {
            "game_id": "g001",
            "gamelet": 1,
            "config_sha256": "a" * 64,
            "barriers": [],
            "cop_barriers_remaining": 14,
            "previous_transcript_root": "",
        }
        h1 = public_transition_hash(**base, step=1)
        h2 = public_transition_hash(**base, step=2)
        assert h1 != h2

    def test_different_config_sha256_produces_different_hash(self):
        from agent.mcp.crypto import public_transition_hash

        base = {
            "game_id": "g001",
            "gamelet": 1,
            "step": 1,
            "barriers": [],
            "cop_barriers_remaining": 14,
            "previous_transcript_root": "",
        }
        h1 = public_transition_hash(**base, config_sha256="a" * 64)
        h2 = public_transition_hash(**base, config_sha256="b" * 64)
        assert h1 != h2

    def test_excludes_private_positions(self):
        """The function signature has no cop/thief position args — verify by import inspection."""
        import inspect

        from agent.mcp.crypto import public_transition_hash

        params = inspect.signature(public_transition_hash).parameters
        assert "cop_position" not in params
        assert "thief_position" not in params


# ---------------------------------------------------------------------------
# 3. run_series() counted_mode enforcement
# ---------------------------------------------------------------------------


class TestRunSeriesCountedMode:
    """run_series with counted_mode=True must require exactly 6 gamelets."""

    @pytest.mark.asyncio
    async def test_counted_mode_with_6_gamelets_does_not_raise(self):
        """counted_mode=True with n_gamelets=6 is the only valid counted config."""
        from pathlib import Path

        from scripts.run_series import run_series

        _shared_cfg = {
            "scoring": {
                "capture_cop": 20,
                "capture_thief": 5,
                "survival_cop": 5,
                "survival_thief": 10,
                "tie_score": 2,
            }
        }

        async def _run_game(**kwargs):
            return {"winner": "cop", "audit_ok": True, "final_step": 10}

        mock_runtime = MagicMock()
        mock_runtime.run_game = _run_game

        with (
            patch("agent.config.shared_config.load_shared_config", return_value=_shared_cfg),
            patch("agent.peer_runtime.PeerRuntime", return_value=mock_runtime),
        ):
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                # Should NOT raise
                result = await run_series(
                    thief_url="http://localhost:5001/mcp",
                    secret="s",
                    config_sha256="a" * 64,
                    games_dir=Path(tmpdir),
                    n_gamelets=6,
                    group_name="test",
                    counted_mode=True,
                )
            assert result["n_gamelets"] == 6

    @pytest.mark.asyncio
    async def test_counted_mode_n_gamelets_5_raises(self):
        from pathlib import Path

        from scripts.run_series import run_series

        with pytest.raises(ValueError, match="Counted mode requires exactly 6 gamelets"):
            await run_series(
                thief_url="http://localhost:5001/mcp",
                secret="s",
                config_sha256="a" * 64,
                games_dir=Path("."),
                n_gamelets=5,
                group_name="test",
                counted_mode=True,
            )

    @pytest.mark.asyncio
    async def test_counted_mode_n_gamelets_7_raises(self):
        from pathlib import Path

        from scripts.run_series import run_series

        with pytest.raises(ValueError, match="Counted mode requires exactly 6 gamelets"):
            await run_series(
                thief_url="http://localhost:5001/mcp",
                secret="s",
                config_sha256="a" * 64,
                games_dir=Path("."),
                n_gamelets=7,
                group_name="test",
                counted_mode=True,
            )

    @pytest.mark.asyncio
    async def test_uncounted_mode_any_gamelets_allowed(self):
        """Without counted_mode, any n_gamelets is accepted (no ValueError raised at entry)."""
        from pathlib import Path

        from scripts.run_series import run_series

        _shared_cfg = {
            "scoring": {
                "capture_cop": 20,
                "capture_thief": 5,
                "survival_cop": 5,
                "survival_thief": 10,
                "tie_score": 2,
            }
        }

        async def _run_game(**kwargs):
            return {"winner": "cop", "audit_ok": True, "final_step": 5}

        mock_runtime = MagicMock()
        mock_runtime.run_game = _run_game

        with (
            patch("agent.config.shared_config.load_shared_config", return_value=_shared_cfg),
            patch("agent.peer_runtime.PeerRuntime", return_value=mock_runtime),
        ):
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                result = await run_series(
                    thief_url="http://localhost:5001/mcp",
                    secret="s",
                    config_sha256="a" * 64,
                    games_dir=Path(tmpdir),
                    n_gamelets=3,
                    group_name="test",
                    counted_mode=False,
                )
            assert result["n_gamelets"] == 3
