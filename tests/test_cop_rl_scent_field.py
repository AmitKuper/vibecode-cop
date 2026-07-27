"""Tests that cop RL observation uses scent field, not thief position directly."""

import inspect

import pytest

from agent.board import Board
from agent.rl.observation import cop_observation
from agent.rules_engine import RulesEngine


def _one_hot_pos(channel, n=7):
    for y in range(n):
        for x in range(n):
            if channel[y][x] == 1.0:
                return x, y
    return -1, -1


class TestCopObservationHiddenInfo:
    def _board(self, cop=(0, 0), thief=(3, 3)):
        return Board(cop_position=list(cop), thief_position=list(thief))

    def test_cop_obs_has_no_thief_one_hot_channel(self):
        """Cop observation must not contain a channel that is 1-hot at thief position."""
        board = self._board(cop=(0, 0), thief=(5, 5))
        rules = RulesEngine(board)
        obs = cop_observation(board, rules, max_steps=35)
        # Channel 0 = cop position, channel 2 = scent. None should be 1-hot at thief.
        thief_pos = board.thief_position  # [5, 5]
        for ch_idx, channel in enumerate(obs):
            val = channel[thief_pos[1]][thief_pos[0]]
            if val == 1.0:
                # Only cop_position channel (ch 0) is ever pure 1-hot; it's at cop pos, not thief pos
                # So if we find a 1.0 at thief pos, it must NOT be in the cop-one-hot channel
                # Actually — scent can be ≤0.9, never exactly 1.0
                one_hot_x, one_hot_y = _one_hot_pos(channel)
                assert (one_hot_x, one_hot_y) != (thief_pos[0], thief_pos[1]), (
                    f"Channel {ch_idx} is 1-hot at thief position — this leaks thief location!"
                )

    def test_cop_obs_channel_0_is_cop_position(self):
        board = self._board(cop=(2, 4), thief=(6, 0))
        rules = RulesEngine(board)
        obs = cop_observation(board, rules, max_steps=35)
        cx, cy = _one_hot_pos(obs[0])
        assert (cx, cy) == (2, 4), "Channel 0 must be cop position 1-hot"

    def test_cop_obs_scent_field_is_not_thief_one_hot(self):
        """Channel 2 (scent) must decay from thief — max value is < 1.0."""
        board = self._board(cop=(0, 0), thief=(3, 3))
        rules = RulesEngine(board)
        obs = cop_observation(board, rules, max_steps=35)
        scent = obs[2]
        max_val = max(cell for row in scent for cell in row)
        # Scent center is 0.9 (from PRD), never 1.0
        assert max_val <= 0.9, f"Scent max {max_val} suggests thief 1-hot encoding, not decay"

    def test_cop_obs_scent_centered_on_thief(self):
        """Scent field peak must be at thief's position (Chebyshev decay)."""
        thief_x, thief_y = 5, 1
        board = self._board(cop=(0, 0), thief=(thief_x, thief_y))
        rules = RulesEngine(board)
        obs = cop_observation(board, rules, max_steps=35)
        scent = obs[2]
        max_val = max(cell for row in scent for cell in row)
        assert scent[thief_y][thief_x] == max_val, "Scent peak must be at thief position"

    def test_cop_rl_policy_uses_cop_observation(self):
        """RLPolicy._build_obs for cop must call cop_observation (not thief_observation)."""
        from unittest.mock import patch, MagicMock
        import torch
        from agent.rl.policy import RLPolicy

        policy = RLPolicy.__new__(RLPolicy)
        policy.net = MagicMock()
        policy.role = "cop"
        policy.algo = "dqn"
        policy.max_steps = 35
        policy.barrier_quota = 0
        policy.barriers_remaining = 0
        policy.device = torch.device("cpu")

        board = Board(cop_position=[0, 0], thief_position=[3, 3])
        rules = RulesEngine(board)

        with patch("agent.rl.policy.cop_observation") as mock_cop_obs, \
             patch("agent.rl.policy.thief_observation") as mock_thief_obs:
            mock_cop_obs.return_value = [[[0.0] * 7 for _ in range(7)]] * 4
            try:
                policy._build_obs(board, rules)
            except Exception:
                pass
            mock_cop_obs.assert_called_once()
            mock_thief_obs.assert_not_called()
