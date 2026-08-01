"""Self-play RL environment for cop-and-thief training.

Gym-compatible, simultaneous-action, mirrors the commit-reveal protocol.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from agent.board import Board
from agent.rl.config import RLGameConfig
from agent.rl.env_helpers import apply_place_action, manhattan_dist, random_starts
from agent.rl.env_rewards import RewardsMixin
from agent.rl.observation import cop_observation, thief_observation
from agent.rules_engine import GameOutcome, RulesEngine

logger = logging.getLogger(__name__)

ACTIONS = ["NORTH", "SOUTH", "EAST", "WEST", "STAY"]
N_ACTIONS = len(ACTIONS)
COP_ACTIONS = ["NORTH", "SOUTH", "EAST", "WEST", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"]  # noqa: E501
N_COP_ACTIONS = len(COP_ACTIONS)
_PLACE_DELTAS = {"PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"}  # barrier actions set


class CopThiefEnv(RewardsMixin):
    """Simultaneous-action self-play environment (mirrors the commit-reveal protocol)."""

    def __init__(self, config: RLGameConfig | None = None):
        self.config = config or RLGameConfig()
        self._board: Board | None = None
        self._rules: RulesEngine | None = None
        self._prev_dist: int = 0
        self._cop_barriers_remaining: int = 0

    @property
    def n_cop_actions(self) -> int:
        return N_COP_ACTIONS if self.config.cop_barrier_quota > 0 else N_ACTIONS

    @property
    def n_thief_actions(self) -> int:
        return N_ACTIONS

    @property
    def n_cop_channels(self) -> int:
        return 5 if self.config.cop_barrier_quota > 0 else 4

    @property
    def n_thief_channels(self) -> int:
        return 4

    # --- Gym interface ---

    def reset(self) -> tuple[list, list]:
        """Reset to initial state. Returns (cop_obs, thief_obs)."""
        cfg = self.config
        if cfg.random_starts:
            cop_start, thief_start = self._random_starts()
        else:
            cop_start = list(cfg.cop_start)
            thief_start = list(cfg.thief_start)

        self._board = Board(
            cop_position=cop_start,
            thief_position=thief_start,
            turn=0,
            barriers=copy.deepcopy(cfg.barriers),
            grid_size=cfg.grid_size,
        )
        self._rules = RulesEngine(self._board)
        self._prev_dist = self._manhattan_dist()
        self._cop_barriers_remaining = cfg.cop_barrier_quota
        return self._observations()

    def _random_starts(self) -> tuple[list[int], list[int]]:
        return random_starts(self.config.grid_size, self.config.barriers)

    def _manhattan_dist(self) -> int:
        return manhattan_dist(self._board)

    def step(
        self, cop_action: int, thief_action: int
    ) -> tuple[list, list, float, float, bool, dict[str, Any]]:
        """Apply both actions simultaneously and advance one turn."""
        assert self._board is not None, "Call reset() before step()"

        cop_actions = COP_ACTIONS if self.config.cop_barrier_quota > 0 else ACTIONS
        cop_move = cop_actions[cop_action]
        thief_move = ACTIONS[thief_action]

        if cop_move in _PLACE_DELTAS:  # barrier placement; then stay
            self._cop_barriers_remaining = apply_place_action(
                self._board, cop_move, self.config.grid_size, self._cop_barriers_remaining
            )
            cop_move = "STAY"
            if list(self._board.thief_position) in self._board.barriers:
                self._board.turn += 1
                cop_obs, thief_obs = self._observations()
                info = {"outcome": GameOutcome.COP_WIN.value, "winner": "cop",
                        "turn": self._board.turn, "cop_position": list(self._board.cop_position),
                        "thief_position": list(self._board.thief_position)}
                r = self._shaped_rewards(GameOutcome.COP_WIN) if self.config.use_shaped_rewards \
                    else self._rewards(GameOutcome.COP_WIN)
                return cop_obs, thief_obs, r[0], r[1], True, info
        if not self._rules.validate_move("cop", cop_move):  # illegal → STAY
            cop_move = "STAY"
        if not self._rules.validate_move("thief", thief_move):
            thief_move = "STAY"

        self._rules.apply_moves(cop_move, thief_move)
        outcome = self._rules.check_game_status()
        done = outcome != GameOutcome.ONGOING

        if self.config.use_shaped_rewards:
            cop_reward, thief_reward = self._shaped_rewards(outcome)
        else:
            cop_reward, thief_reward = self._rewards(outcome)

        info: dict[str, Any] = {
            "outcome": outcome.value,
            "winner": None,
            "turn": self._board.turn,
            "cop_position": list(self._board.cop_position),
            "thief_position": list(self._board.thief_position),
        }
        if done:
            info["winner"] = "cop" if outcome == GameOutcome.COP_WIN else "thief"

        cop_obs, thief_obs = self._observations()
        return cop_obs, thief_obs, cop_reward, thief_reward, done, info

    # --- Metadata helpers ---

    @property
    def n_actions(self) -> int:
        return N_ACTIONS

    def observation_shape(self, role: str = "thief") -> tuple[int, int, int]:
        """(channels, height, width) for building network input layers."""
        n = self.config.grid_size
        n_ch = self.n_cop_channels if role == "cop" else self.n_thief_channels
        return (n_ch, n, n)

    def action_meanings(self) -> list[str]:
        return list(ACTIONS)

    # --- Internal helpers ---

    def _observations(self) -> tuple[list, list]:
        cfg = self.config
        cop_obs = cop_observation(
            self._board, self._rules, cfg.max_steps,
            barriers_remaining=self._cop_barriers_remaining,
            barrier_quota=cfg.cop_barrier_quota,
        )
        thief_obs = thief_observation(self._board, cfg.max_steps)
        return cop_obs, thief_obs
