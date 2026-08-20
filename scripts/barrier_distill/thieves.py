"""Thief opponent pool for barrier distillation (evaders, minimax, scripted)."""

from __future__ import annotations

import random

from anti_evader_lab import VARIANTS, ResolvingEvader

from cop_worker.rl.action_space import MOVE_DELTAS
from cop_worker.rl.pursuit_search import best_thief_action

MAX_STEPS = 35
_DELTA_TO_NAME = {tuple(d): a for a, d in MOVE_DELTAS.items()}


def _cell_to_action(thief, cell) -> str:
    return _DELTA_TO_NAME.get((cell[0] - thief[0], cell[1] - thief[1]), "STAY")


class EvaderThief:
    """Wall-myopic exact evader (the SMNGRP05 class), as a joint-action policy."""

    def __init__(self, variant: str) -> None:
        self.variant = variant
        self._evader = ResolvingEvader(variant, MAX_STEPS)

    def reset(self) -> None:
        self._evader = ResolvingEvader(self.variant, MAX_STEPS)

    def action(self, state, rng: random.Random) -> str:
        walls = {tuple(b) for b in state.barriers}
        cell = self._evader.move(
            tuple(state.cop_position),
            tuple(state.thief_position),
            walls,
            max(1, MAX_STEPS - int(state.turn)),
        )
        if cell is None:  # enclosed — rule 47; the domain declares the outcome
            return "STAY"
        return _cell_to_action(tuple(state.thief_position), cell)


class MinimaxThief:
    """Production thief search (our own other half) at reduced depth for speed."""

    def __init__(self, depth: int = 3, time_budget_s: float = 0.8) -> None:
        self.depth = depth
        self.time_budget_s = time_budget_s

    def reset(self) -> None:
        pass

    def action(self, state, rng: random.Random) -> str:
        return best_thief_action(
            tuple(state.cop_position),
            tuple(state.thief_position),
            [tuple(b) for b in state.barriers],
            max(1, MAX_STEPS - int(state.turn)),
            depth=self.depth,
            n=state.grid_size,
            cop_barriers_left=int(state.cop_barriers_remaining),
            time_budget_s=self.time_budget_s,
        )


class ScriptedThief:
    """'away' maximizes distance from the cop; 'random' plays a legal move."""

    def __init__(self, style: str) -> None:
        self.style = style

    def reset(self) -> None:
        pass

    def action(self, state, rng: random.Random) -> str:
        walls = {tuple(b) for b in state.barriers}
        thief = tuple(state.thief_position)
        cop = tuple(state.cop_position)
        n = state.grid_size
        options = []
        for name, (dx, dy) in MOVE_DELTAS.items():
            q = (thief[0] + dx, thief[1] + dy)
            if 0 <= q[0] < n and 0 <= q[1] < n and q not in walls:
                options.append((name, q))
        if not options:
            return "STAY"
        if self.style == "random":
            return rng.choice(options)[0]
        return max(options, key=lambda o: abs(o[1][0] - cop[0]) + abs(o[1][1] - cop[1]))[0]


def make_pool() -> list:
    """One collection cycle: evader-heavy (that's where PLACE labels live)."""
    evaders = [EvaderThief(v) for v in VARIANTS] + [EvaderThief(v) for v in VARIANTS]
    return [*evaders, MinimaxThief(), ScriptedThief("away"), ScriptedThief("random")]
