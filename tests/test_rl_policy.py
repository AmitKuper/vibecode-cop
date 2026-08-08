"""Fast unit tests for the RLPolicy live-inference wrapper.

Uses tiny in-memory DQN/PPO nets — no checkpoint files, no LLM, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cop_worker.board import Board
from cop_worker.rl.networks import DQNNet, PPONet
from cop_worker.rl.policy import RLPolicy
from cop_worker.rules_engine import RulesEngine

N = 7


def _board():
    return Board(cop_position=[1, 1], thief_position=[5, 5], turn=0, barriers=[], grid_size=N)


def test_dqn_thief_select_move_returns_legal_string():
    net = DQNNet(grid_size=N, n_actions=5, hidden=16, in_channels=4)
    policy = RLPolicy(net, role="thief", algo="dqn")
    board = _board()
    move = policy.select_move(board, RulesEngine(board))
    assert move in ("NORTH", "SOUTH", "EAST", "WEST", "STAY")


def test_ppo_cop_select_move_with_barrier_quota():
    net = PPONet(grid_size=N, n_actions=9, hidden=16, in_channels=5)
    policy = RLPolicy(net, role="cop", algo="ppo", barrier_quota=14, barriers_remaining=5)
    board = _board()
    move = policy.select_move(board, RulesEngine(board))
    assert isinstance(move, str) and move != ""


def test_select_action_ppo_interface_shape():
    net = PPONet(grid_size=N, n_actions=5, hidden=16, in_channels=4)
    policy = RLPolicy(net, role="thief", algo="ppo")
    board = _board()
    obs = policy._build_obs(board, RulesEngine(board))
    idx, lp, val = policy.select_action(obs, training=False)
    assert 0 <= idx < 5 and lp == 0.0 and val == 0.0


def test_select_action_dqn_is_deterministic_argmax():
    net = DQNNet(grid_size=N, n_actions=5, hidden=16, in_channels=4)
    policy = RLPolicy(net, role="thief", algo="dqn")
    board = _board()
    obs = policy._build_obs(board, RulesEngine(board))
    a1, _, _ = policy.select_action(obs)
    a2, _, _ = policy.select_action(obs)
    assert a1 == a2  # DQN argmax is deterministic


def test_select_move_from_dict_roundtrips():
    net = DQNNet(grid_size=N, n_actions=5, hidden=16, in_channels=4)
    policy = RLPolicy(net, role="thief", algo="dqn")
    move = policy.select_move_from_dict(_board().to_dict())
    assert move in ("NORTH", "SOUTH", "EAST", "WEST", "STAY")


def test_build_obs_channel_counts_per_role():
    board = _board()
    rules = RulesEngine(board)
    cop = RLPolicy(DQNNet(in_channels=5), role="cop", algo="dqn", barrier_quota=14)
    thief = RLPolicy(DQNNet(in_channels=4), role="thief", algo="dqn")
    assert len(cop._build_obs(board, rules)) == 5
    assert len(thief._build_obs(board, rules)) == 4


def test_load_raises_when_no_model_present(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        RLPolicy.load("thief", models_dir=tmp_path)
