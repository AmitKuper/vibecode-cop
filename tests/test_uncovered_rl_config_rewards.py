"""Tests for rl/config.py and rl/env_rewards.py.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""

import pytest


class TestRLGameConfig:
    def test_defaults(self):
        from cop_worker.rl.config import RLGameConfig

        c = RLGameConfig()
        assert c.grid_size == 7
        assert c.max_steps == 35
        assert c.cop_capture_reward == 1.0
        assert c.thief_survival_reward == 1.0
        assert c.step_penalty == 0.01
        assert c.use_shaped_rewards is False
        assert c.random_starts is False

    def test_from_dict_all_fields(self):
        from cop_worker.rl.config import RLGameConfig

        d = {
            "grid_size": 9,
            "cop_start": [1, 1],
            "thief_start": [5, 5],
            "barriers": [[2, 3]],
            "max_steps": 50,
            "survival_threshold": 50,
            "max_barriers": 10,
        }
        c = RLGameConfig.from_dict(d)
        assert c.grid_size == 9
        assert c.cop_start == [1, 1]
        assert c.thief_start == [5, 5]
        assert c.barriers == [[2, 3]]
        assert c.max_steps == 50

    def test_from_dict_empty(self):
        from cop_worker.rl.config import RLGameConfig

        c = RLGameConfig.from_dict({})
        assert c.grid_size == 7


class TestRewardsMixin:
    def _make_mixin(self, capture_reward=1.0, survival_reward=1.0, step_penalty=0.01):
        from cop_worker.rl.config import RLGameConfig
        from cop_worker.rl.env_rewards import RewardsMixin

        class FakeMixin(RewardsMixin):
            def __init__(self):
                self.config = RLGameConfig(
                    cop_capture_reward=capture_reward,
                    thief_survival_reward=survival_reward,
                    step_penalty=step_penalty,
                )
                self._prev_dist = 5

        return FakeMixin()

    def test_cop_win_rewards(self):
        from cop_worker.rules_outcomes import GameOutcome

        m = self._make_mixin()
        cop_r, thief_r = m._rewards(GameOutcome.COP_WIN)
        assert cop_r == 1.0
        assert thief_r == -1.0

    def test_thief_win_rewards(self):
        from cop_worker.rules_outcomes import GameOutcome

        m = self._make_mixin()
        cop_r, thief_r = m._rewards(GameOutcome.THIEF_WIN)
        assert cop_r == -1.0
        assert thief_r == 1.0

    def test_ongoing_rewards(self):
        from cop_worker.rules_outcomes import GameOutcome

        m = self._make_mixin(step_penalty=0.05)
        cop_r, thief_r = m._rewards(GameOutcome.ONGOING)
        assert cop_r == pytest.approx(-0.05)
        assert thief_r == pytest.approx(0.05)

    def test_shaped_rewards_terminal(self):
        from cop_worker.rules_outcomes import GameOutcome

        m = self._make_mixin()
        m.config.use_shaped_rewards = True
        m.config.shaped_reward_scale = 0.15
        # Terminal outcomes: shaped == base
        cop_r, thief_r = m._shaped_rewards(GameOutcome.COP_WIN)
        assert cop_r == pytest.approx(1.0)

    def test_shaped_rewards_ongoing(self):
        from cop_worker.board import Board
        from cop_worker.rules_outcomes import GameOutcome

        m = self._make_mixin()
        m.config.shaped_reward_scale = 0.1
        m._prev_dist = 6
        m._board = Board(cop_position=[0, 0], thief_position=[4, 4])

        # mock manhattan_dist in env_rewards module (where it's imported)
        import cop_worker.rl.env_rewards as er

        orig = er.manhattan_dist
        er.manhattan_dist = lambda b: 4  # cop closer now (was 6, now 4)
        try:
            cop_r, thief_r = m._shaped_rewards(GameOutcome.ONGOING)
            assert cop_r > -0.01  # step penalty offset by positive shaping
        finally:
            er.manhattan_dist = orig
