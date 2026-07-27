"""Tests that the thief RL observation never uses the true live cop position."""

import pytest

from agent.board import Board
from agent.rl.observation import thief_observation
from agent.rules_engine import RulesEngine


def _one_hot_pos(obs_channel, n=7) -> tuple[int, int]:
    for y in range(n):
        for x in range(n):
            if obs_channel[y][x] == 1.0:
                return x, y
    return -1, -1


class TestThiefObservationHiddenInfo:
    def _make_board(self, cop_pos=(0, 0), thief_pos=(3, 3)) -> Board:
        return Board(cop_position=list(cop_pos), thief_position=list(thief_pos))

    def test_without_last_revealed_falls_back_to_board(self):
        board = self._make_board(cop_pos=(2, 2), thief_pos=(4, 4))
        obs = thief_observation(board, max_steps=35)
        cx, cy = _one_hot_pos(obs[1])
        # Without explicit last_revealed_cop_pos, falls back to live board (training mode)
        assert (cx, cy) == (2, 2)

    def test_with_last_revealed_uses_old_pos(self):
        board = self._make_board(cop_pos=(2, 2), thief_pos=(4, 4))
        # Thief was last told cop is at (0, 0) (one step old)
        obs = thief_observation(board, max_steps=35, last_revealed_cop_pos=[0, 0])
        cx, cy = _one_hot_pos(obs[1])
        assert (cx, cy) == (0, 0), "Thief should see last-revealed cop pos, not live pos"

    def test_last_revealed_differs_from_live(self):
        board = self._make_board(cop_pos=(5, 5), thief_pos=(1, 1))
        obs_live = thief_observation(board, max_steps=35)
        obs_revealed = thief_observation(board, max_steps=35, last_revealed_cop_pos=[2, 3])
        assert _one_hot_pos(obs_live[1]) != _one_hot_pos(obs_revealed[1])

    def test_thief_position_channel_is_always_live(self):
        board = self._make_board(cop_pos=(0, 0), thief_pos=(4, 2))
        obs = thief_observation(board, max_steps=35, last_revealed_cop_pos=[0, 0])
        tx, ty = _one_hot_pos(obs[0])
        assert (tx, ty) == (4, 2), "Thief's own position is always live"


class TestRLPolicyHiddenInfo:
    def test_select_move_from_dict_accepts_last_revealed_cop_pos(self):
        """RLPolicy.select_move_from_dict must accept last_revealed_cop_pos without error."""
        import inspect
        from agent.rl.policy import RLPolicy
        sig = inspect.signature(RLPolicy.select_move_from_dict)
        assert "last_revealed_cop_pos" in sig.parameters

    def test_build_obs_uses_last_revealed_for_thief(self):
        """_build_obs must route last_revealed_cop_pos to thief_observation."""
        from unittest.mock import patch, MagicMock
        import torch
        from agent.rl.policy import RLPolicy

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

        with patch("agent.rl.policy.thief_observation") as mock_obs:
            mock_obs.return_value = [[[[0.0] * 7 for _ in range(7)] for _ in range(7)] for _ in range(4)]
            policy._build_obs(board, rules, last_revealed_cop_pos=[2, 3])
            mock_obs.assert_called_once_with(board, 35, last_revealed_cop_pos=[2, 3])


crewai_missing = pytest.importorskip.__module__  # just to use pytest


class TestOrchestratoreGameStateTracking:
    def test_last_revealed_cop_pos_in_observation(self):
        """_build_observation must include last_revealed_cop_pos for thief."""
        crewai = pytest.importorskip("crewai", reason="crewai not installed")
        from agent.orchestrator_crew import CrewMixin  # noqa: F401

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
        from agent.orchestrator_crew import CrewMixin  # noqa: F401

        mixin = CrewMixin.__new__(CrewMixin)
        mixin.role = "cop"

        game_state = {
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "turn": 0,
        }
        obs = mixin._build_observation(game_state)
        assert "last_revealed_cop_pos" not in obs
