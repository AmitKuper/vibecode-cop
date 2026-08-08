"""Fast unit tests for RL config, env helpers, and reward mixin.

All pure/deterministic — no LLM, no network, no training loop.
"""

from __future__ import annotations

import random

from cop_worker.board import Board
from cop_worker.rl.config import RLGameConfig
from cop_worker.rl.env_helpers import apply_place_action, manhattan_dist, random_starts
from cop_worker.rl.env_rewards import RewardsMixin
from cop_worker.rules_engine import GameOutcome

# --- config -----------------------------------------------------------------


def test_config_defaults_match_mandatory_minimums():
    cfg = RLGameConfig()
    assert cfg.grid_size == 7
    assert cfg.max_steps == 35
    assert cfg.max_barriers == 14
    assert cfg.cop_capture_reward == 1.0 and cfg.thief_survival_reward == 1.0


def test_config_from_dict_overrides_and_falls_back():
    cfg = RLGameConfig.from_dict({"grid_size": 9, "max_steps": 50})
    assert cfg.grid_size == 9 and cfg.max_steps == 50
    # unspecified keys fall back to defaults
    assert cfg.max_barriers == 14 and cfg.thief_start == [3, 3]


# --- env_helpers ------------------------------------------------------------


def test_manhattan_dist():
    board = Board(cop_position=[0, 0], thief_position=[3, 4], turn=0, barriers=[], grid_size=7)
    assert manhattan_dist(board) == 7


def test_random_starts_are_distinct_and_avoid_barriers():
    random.seed(1)
    barriers = [[0, 0], [1, 1]]
    for _ in range(20):
        cop, thief = random_starts(7, barriers)
        assert cop != thief
        assert cop not in barriers and thief not in barriers
        assert all(0 <= c < 7 for c in cop + thief)


def test_apply_place_action_decrements_and_places_barrier():
    board = Board(cop_position=[2, 2], thief_position=[5, 5], turn=0, barriers=[], grid_size=7)
    remaining = apply_place_action(board, "PLACE_E", grid_size=7, barriers_remaining=3)
    assert remaining == 2
    assert [3, 2] in board.barriers


def test_apply_place_action_noop_when_quota_exhausted():
    board = Board(cop_position=[2, 2], thief_position=[5, 5], turn=0, barriers=[], grid_size=7)
    remaining = apply_place_action(board, "PLACE_E", grid_size=7, barriers_remaining=0)
    assert remaining == 0
    assert board.barriers == []


def test_apply_place_action_noop_when_target_already_barrier():
    # (3,2) is already a barrier → place_barrier returns False → quota unchanged.
    board = Board(
        cop_position=[2, 2], thief_position=[5, 5], turn=0, barriers=[[3, 2]], grid_size=7
    )
    remaining = apply_place_action(board, "PLACE_E", grid_size=7, barriers_remaining=2)
    assert remaining == 2
    assert board.barriers == [[3, 2]]


def test_apply_place_action_noop_off_board():
    # Cop at the east edge placing further east falls off the board → no placement.
    board = Board(cop_position=[6, 3], thief_position=[0, 0], turn=0, barriers=[], grid_size=7)
    remaining = apply_place_action(board, "PLACE_E", grid_size=7, barriers_remaining=2)
    assert remaining == 2
    assert board.barriers == []


# --- env_rewards ------------------------------------------------------------


class _Host(RewardsMixin):
    """Minimal host exposing the attributes RewardsMixin depends on."""

    def __init__(self, board, config):
        self.board = board
        self._board = board
        self.config = config
        self._prev_dist = manhattan_dist(board)


def _host(cop, thief, **cfg_over):
    cfg = RLGameConfig(**cfg_over)
    board = Board(
        cop_position=list(cop), thief_position=list(thief), turn=0, barriers=[], grid_size=7
    )
    return _Host(board, cfg)


def test_terminal_rewards_are_zero_sum_shaped():
    host = _host((0, 0), (0, 1))
    cop_r, thief_r = host._shaped_rewards(GameOutcome.COP_WIN)
    assert cop_r == 1.0 and thief_r == -1.0
    cop_r, thief_r = host._shaped_rewards(GameOutcome.THIEF_WIN)
    assert cop_r == -1.0 and thief_r == 1.0


def test_shaped_reward_rewards_cop_closing_distance():
    host = _host((0, 0), (5, 0))  # prev_dist = 5
    host._board.cop_position = [1, 0]  # cop moved closer → curr_dist = 4, delta = +1
    cop_r, thief_r = host._shaped_rewards(GameOutcome.ONGOING)
    scale = host.config.shaped_reward_scale
    assert cop_r == -host.config.step_penalty + scale * 1
    assert thief_r == host.config.step_penalty - scale * 1
    assert host._prev_dist == 4  # potential updated in place
