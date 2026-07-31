"""Helper functions and greedy/random heuristic strategies."""

from __future__ import annotations

import math
import random

from agent.rl.environment import ACTIONS, N_ACTIONS


def _argmax2d(grid: list[list[float]]) -> tuple[int, int]:
    """Return (x, y) of the maximum value in a 2-D grid."""
    best_val = -math.inf
    best_x, best_y = 0, 0
    for y, row in enumerate(grid):
        for x, val in enumerate(row):
            if val > best_val:
                best_val = val
                best_x, best_y = x, y
    return best_x, best_y


def _decode_1hot(grid: list[list[float]]) -> tuple[int, int]:
    """Return (x, y) of the single 1-hot cell (highest value wins on ties)."""
    return _argmax2d(grid)


def _chebyshev(ax: int, ay: int, bx: int, by: int) -> int:
    return max(abs(ax - bx), abs(ay - by))


def _legal_from_obs(pos: tuple[int, int], barriers_ch: list[list[float]], grid_size: int) -> list[int]:
    """Return action indices legal from pos given a barrier channel."""
    x, y = pos
    legal = []
    for i, act in enumerate(ACTIONS):
        if act == "STAY":
            legal.append(i)
            continue
        dx, dy = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}[act]
        nx, ny = x + dx, y + dy
        if 0 <= nx < grid_size and 0 <= ny < grid_size and barriers_ch[ny][nx] < 0.5:
            legal.append(i)
    return legal or [ACTIONS.index("STAY")]


_DELTA = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0), "STAY": (0, 0)}


class RandomStrategy:
    """Uniform random action selection — used as a baseline."""

    def __init__(self, n_actions: int = N_ACTIONS):
        self.n_actions = n_actions

    def select_action(self, obs: list, training: bool = False) -> int:
        return random.randrange(self.n_actions)


class GreedyCopStrategy:
    """Move toward the cell with the highest scent value.

    Cop observation layout (4 channels):
        0  cop position  (1-hot)
        1  barriers
        2  scent field   (float, peak = thief's likely location)
        3  turns remaining
    """

    def select_action(self, obs: list, training: bool = False) -> int:
        cop_ch, barrier_ch, scent_ch = obs[0], obs[1], obs[2]
        grid_size = len(cop_ch)
        cx, cy = _decode_1hot(cop_ch)
        tx, ty = _argmax2d(scent_ch)
        legal = _legal_from_obs((cx, cy), barrier_ch, grid_size)
        best_idx = legal[0]
        best_dist = math.inf
        for i in legal:
            dx, dy = _DELTA[ACTIONS[i]]
            d = _chebyshev(cx + dx, cy + dy, tx, ty)
            if d < best_dist:
                best_dist = d
                best_idx = i
        return best_idx


class GreedyThiefStrategy:
    """Move to maximize Chebyshev distance from the last-revealed cop position.

    Thief observation layout (4 channels):
        0  thief position        (1-hot)
        1  last revealed cop pos (1-hot)
        2  barriers
        3  turns remaining
    """

    def select_action(self, obs: list, training: bool = False) -> int:
        thief_ch, cop_ch, barrier_ch = obs[0], obs[1], obs[2]
        grid_size = len(thief_ch)
        tx, ty = _decode_1hot(thief_ch)
        cx, cy = _decode_1hot(cop_ch)
        legal = _legal_from_obs((tx, ty), barrier_ch, grid_size)
        best_idx = legal[0]
        best_dist = -1
        for i in legal:
            dx, dy = _DELTA[ACTIONS[i]]
            d = _chebyshev(tx + dx, ty + dy, cx, cy)
            if d > best_dist:
                best_dist = d
                best_idx = i
        return best_idx
