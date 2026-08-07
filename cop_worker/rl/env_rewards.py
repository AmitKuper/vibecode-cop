"""Reward computation mixin for CopThiefEnv.

Extracted from environment.py to keep each file under 150 lines.
Used as a mixin by CopThiefEnv.
"""

from __future__ import annotations

from cop_worker.rl.env_helpers import manhattan_dist
from cop_worker.rules_engine import GameOutcome


class RewardsMixin:
    """Mixin providing terminal and shaped reward computation.

    Requires the host class to have:
        self.config  — RLGameConfig
        self._board  — Board
        self._prev_dist — int (Manhattan distance at previous step)
    """

    def _rewards(self, outcome: GameOutcome) -> tuple[float, float]:
        cfg = self.config
        if outcome == GameOutcome.COP_WIN:
            return cfg.cop_capture_reward, -cfg.thief_survival_reward
        if outcome == GameOutcome.THIEF_WIN:
            return -cfg.thief_survival_reward, cfg.cop_capture_reward
        # Ongoing: small per-step signals to encourage speed (cop) and survival (thief)
        return -cfg.step_penalty, cfg.step_penalty

    def _shaped_rewards(self, outcome: GameOutcome) -> tuple[float, float]:
        """Rewards with potential-based shaping: reward distance improvement."""
        base_cop, base_thief = self._rewards(outcome)
        if outcome != GameOutcome.ONGOING:
            return base_cop, base_thief
        curr_dist = manhattan_dist(self._board)
        delta = self._prev_dist - curr_dist  # positive when cop got closer
        scale = self.config.shaped_reward_scale
        self._prev_dist = curr_dist
        return base_cop + scale * delta, base_thief - scale * delta
