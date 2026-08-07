import pytest

pytest.skip("module removed in restructure", allow_module_level=True)

"""Tests that the thief RL observation never uses the true live cop position."""

import pytest

from cop_worker.board import Board
from cop_worker.rl.observation import thief_observation
from cop_worker.rules_engine import RulesEngine


def _one_hot_pos(obs_channel, n=7) -> tuple[int, int]:
    for y in range(n):
        for x in range(n):
            if obs_channel[y][x] == 1.0:
                return x, y
    return -1, -1


class TestThiefObservationHiddenInfo:
    def _make_board(self, cop_pos=(0, 0), thief_pos=(3, 3)) -> Board:
        return Board(cop_position=list(cop_pos), thief_position=list(thief_pos))

    def test_without_scent_channel1_is_zeros(self):
        """Without cop scent, channel 1 must be all zeros (not the live cop 1-hot)."""
        board = self._make_board(cop_pos=(2, 2), thief_pos=(4, 4))
        obs = thief_observation(board, max_steps=35)
        # Channel 1 is scent field — all zeros when no scent provided
        ch1_flat = [v for row in obs[1] for v in row]
        assert all(v == 0.0 for v in ch1_flat), "Channel 1 must be zeros when no scent supplied"

    def test_with_scent_channel1_reflects_scent(self):
        """When cop scent is provided, channel 1 must equal the scent field."""
        board = self._make_board(cop_pos=(2, 2), thief_pos=(4, 4))
        n = board.grid_size
        scent = [[0.0] * n for _ in range(n)]
        scent[0][0] = 0.5  # cop was around (0,0) recently
        obs = thief_observation(board, max_steps=35, cop_scent_field=scent)
        assert obs[1] == scent, "Channel 1 must equal the provided cop scent field"

    def test_channel1_is_not_live_cop_one_hot(self):
        """Channel 1 must never equal the live cop one-hot (hidden info fix)."""
        board = self._make_board(cop_pos=(2, 2), thief_pos=(4, 4))
        n = board.grid_size
        obs = thief_observation(board, max_steps=35)
        cop_one_hot = [[0.0] * n for _ in range(n)]
        cop_one_hot[2][2] = 1.0  # live cop at (2,2)
        assert obs[1] != cop_one_hot, "Channel 1 must not be the live cop position one-hot"

    def test_thief_position_channel_is_always_live(self):
        board = self._make_board(cop_pos=(0, 0), thief_pos=(4, 2))
        obs = thief_observation(board, max_steps=35, cop_scent_field=None)
        tx, ty = _one_hot_pos(obs[0])
        assert (tx, ty) == (4, 2), "Thief's own position (channel 0) is always live"


class TestRLPolicyHiddenInfo:
    def test_select_move_from_dict_accepts_last_revealed_cop_pos(self):
        """RLPolicy.select_move_from_dict must accept last_revealed_cop_pos without error."""
        import inspect

        from cop_worker.rl.policy import RLPolicy

        sig = inspect.signature(RLPolicy.select_move_from_dict)
        assert "last_revealed_cop_pos" in sig.parameters

    def test_build_obs_uses_cop_scent_for_thief(self):
        """_build_obs must route cop_scent_field to thief_observation."""
        from unittest.mock import MagicMock, patch

        import torch

        from cop_worker.rl.policy import RLPolicy

        policy = RLPolicy.__new__(RLPolicy)
        policy.net = MagicMock()
        policy.role = "thief"
        policy.algo = "dqn"
        policy.max_steps = 35
        policy.barrier_quota = 0
        policy.barriers_remaining = 0
        policy.device = torch.device("cpu")

        board = Board(cop_position=[5, 5], thief_position=[1, 1])
        rules = RulesEngine(board)

        scent = [[0.0] * 7 for _ in range(7)]
        with patch("agent.rl.policy.thief_observation") as mock_obs:
            grid = [[0.0] * 7 for _ in range(7)]
            mock_obs.return_value = [[grid for _ in range(7)] for _ in range(4)]
            policy._build_obs(board, rules, cop_scent_field=scent)
            mock_obs.assert_called_once_with(board, 35, cop_scent_field=scent)


crewai_missing = pytest.importorskip.__module__  # just to use pytest


class TestOrchestratoreGameStateTracking:
    def test_last_revealed_cop_pos_in_observation(self):
        """_build_observation must include last_revealed_cop_pos for thief."""
        pytest.importorskip("crewai", reason="crewai not installed")
        from cop_worker.orchestrator_crew import CrewMixin  # noqa: F401

        mixin = CrewMixin.__new__(CrewMixin)
        mixin.role = "thief"

        game_state = {
            "cop_position": [3, 3],
            "thief_position": [1, 1],
            "turn": 5,
            "last_revealed_cop_pos": [2, 2],
        }
        obs = mixin._build_observation(game_state)
        assert "last_revealed_cop_pos" in obs
        assert obs["last_revealed_cop_pos"] == [2, 2]

    def test_cop_observation_has_no_last_revealed_key(self):
        """_build_observation for cop must not include last_revealed_cop_pos."""
        pytest.importorskip("crewai", reason="crewai not installed")
        from cop_worker.orchestrator_crew import CrewMixin  # noqa: F401

        mixin = CrewMixin.__new__(CrewMixin)
        mixin.role = "cop"

        game_state = {
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "turn": 0,
        }
        obs = mixin._build_observation(game_state)
        assert "last_revealed_cop_pos" not in obs
