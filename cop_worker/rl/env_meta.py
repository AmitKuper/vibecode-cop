"""Action constants and metadata/observation helpers for the self-play environment.

Split out of ``cop_worker.rl.environment`` (which remains the public facade and
re-exports the constants); ``CopThiefEnv`` mixes ``EnvMetaMixin`` in.
"""

from __future__ import annotations

from cop_worker.rl.env_helpers import manhattan_dist, random_starts
from cop_worker.rl.observation import cop_observation, thief_observation

ACTIONS = ["NORTH", "SOUTH", "EAST", "WEST", "STAY"]
N_ACTIONS = len(ACTIONS)
COP_ACTIONS = ["NORTH", "SOUTH", "EAST", "WEST", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"]  # noqa: E501
N_COP_ACTIONS = len(COP_ACTIONS)
_PLACE_DELTAS = {"PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"}  # barrier actions set


class EnvMetaMixin:
    """Action-space/channel metadata and observation building for ``CopThiefEnv``."""

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
        return 4  # thief: position, cop_last_revealed, barriers, turns_remaining

    def _random_starts(self) -> tuple[list[int], list[int]]:
        return random_starts(self.config.grid_size, self.config.barriers)

    def _manhattan_dist(self) -> int:
        return manhattan_dist(self._board)

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
            self._board,
            self._rules,
            cfg.max_steps,
            barriers_remaining=self._cop_barriers_remaining,
            barrier_quota=cfg.cop_barrier_quota,
        )
        thief_obs = thief_observation(
            self._board,
            cfg.max_steps,
        )
        return cop_obs, thief_obs
