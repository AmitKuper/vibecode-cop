"""Fast unit tests for asymmetric cop/thief observation builders.

Pure list construction — no LLM, no network. Asserts channel layout, shapes,
and the local-observation invariant (thief never sees the live cop position).
"""

from __future__ import annotations

from cop_worker.board import Board
from cop_worker.rl.observation import (
    cop_observation,
    local_thief_observation,
    observation_shape,
    thief_observation,
)
from cop_worker.rules_engine import RulesEngine

N = 7


def _board():
    return Board(cop_position=[1, 2], thief_position=[5, 6], turn=3, barriers=[[0, 0]], grid_size=N)


def test_cop_observation_four_channels_without_quota():
    board = _board()
    rules = RulesEngine(board, max_turns=35)
    obs = cop_observation(board, rules, max_steps=35)
    assert len(obs) == 4
    assert all(len(ch) == N and len(ch[0]) == N for ch in obs)
    # channel 0 is cop position one-hot at [y][x] = [2][1]
    assert obs[0][2][1] == 1.0
    assert sum(sum(row) for row in obs[0]) == 1.0
    # channel 1 marks the barrier at (0,0)
    assert obs[1][0][0] == 1.0


def test_cop_observation_five_channels_with_quota():
    board = _board()
    rules = RulesEngine(board, max_turns=35)
    obs = cop_observation(board, rules, max_steps=35, barriers_remaining=7, barrier_quota=14)
    assert len(obs) == 5
    # channel 4 broadcasts remaining/quota = 0.5
    assert obs[4][0][0] == 0.5


def test_thief_observation_hides_live_cop_position():
    board = _board()
    obs = thief_observation(board, max_steps=35)
    assert len(obs) == 4
    # channel 0 is thief one-hot at [6][5]; cop cell [2][1] must NOT be flagged anywhere
    assert obs[0][6][5] == 1.0
    assert obs[0][2][1] == 0.0
    # with no scent supplied, the cop-scent channel is all zeros (no GPS leak)
    assert all(v == 0.0 for row in obs[1] for v in row)


def test_thief_observation_uses_supplied_cop_scent():
    board = _board()
    scent = [[0.0] * N for _ in range(N)]
    scent[3][3] = 0.5
    obs = local_thief_observation(board, max_steps=35, cop_scent_field=scent)
    assert obs[1][3][3] == 0.5


def test_turns_remaining_normalisation():
    board = _board()  # turn=3
    obs = thief_observation(board, max_steps=35)
    assert abs(obs[3][0][0] - (35 - 3) / 35) < 1e-9


def test_observation_shape():
    assert observation_shape(7, role="thief") == (4, 7, 7)
    assert observation_shape(7, role="cop", barrier_quota=0) == (4, 7, 7)
    assert observation_shape(7, role="cop", barrier_quota=14) == (5, 7, 7)
