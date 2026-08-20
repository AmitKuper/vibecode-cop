"""Anti-evader lab: production cop stack vs wall-myopic exact evaders.

Reproduces the docs/ANTI_EVADER_ANALYSIS.md matrix from the repo alone.
Each evader re-solves the exact survival table on the CURRENT walls (the
SMNGRP05 class: "exact backward induction", myopic about future placements)
and differs only in its tie-break among surviving moves. The cop side is the
production pair exactly as SearchRolePolicy wires it: StallSqueeze.override
first, then pursuit_search.best_cop_action; actions are applied with the
production action_space deltas, so a convention bug shows up as a loss here.

Usage:  python scripts/anti_evader_lab.py [--hook {on,off,both}] [--steps 35]
"""

from __future__ import annotations

import argparse

from cop_worker.rl.action_space import MOVE_DELTAS, PLACE_DIRS
from cop_worker.rl.pursuit_search import best_cop_action
from cop_worker.rl.stall_squeeze import ORTHO, StallSqueeze, survival_layers

N = 7
LEGAL = [*MOVE_DELTAS, *PLACE_DIRS]


def _man(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _mobility(q, walls):
    return sum(
        1
        for dr, dc in ORTHO
        if 0 <= q[0] + dr < N and 0 <= q[1] + dc < N and (q[0] + dr, q[1] + dc) not in walls
    )


def _mirror_target(cop):
    col = cop[0] + 2 if cop[0] + 2 < N else cop[0] - 2
    return (col, cop[1])


VARIANTS = {
    "mobility": lambda q, cop, walls: (_mobility(q, walls), min(_man(cop, q), 3)),
    "distance": lambda q, cop, walls: (_man(cop, q),),
    "center": lambda q, cop, walls: (-(abs(q[0] - 3) + abs(q[1] - 3)),),
    "mirror2": lambda q, cop, walls: (-_man(q, _mirror_target(cop)), _mobility(q, walls)),
}


class ResolvingEvader:
    """Exact survival play on the CURRENT walls; blind to future placements."""

    def __init__(self, variant: str, steps: int = 35) -> None:
        self.tiebreak = VARIANTS[variant]
        self.steps = steps
        self._walls_key = None
        self._table = None

    def move(self, cop, thief, walls, steps_left):
        wk = frozenset(walls)
        if wk != self._walls_key:
            self._table = survival_layers(wk, N, self.steps)
            self._walls_key = wk
        layers, idx = self._table
        opts, blocked = [], 0
        for dr, dc in ORTHO:
            q = (thief[0] + dr, thief[1] + dc)
            if not (0 <= q[0] < N and 0 <= q[1] < N) or q in walls:
                blocked += 1
            elif q != cop:
                opts.append(q)
        if blocked == 4:
            return None  # rule 47: enclosed (STAY does not rescue)
        opts.append(thief)
        s = max(0, min(steps_left - 1, self.steps))
        key = lambda q: (1 if layers[s][idx[cop]][idx[q]] else 0, *self.tiebreak(q, cop, walls))  # noqa: E731
        return max(opts, key=key)


def run_match(variant: str, hook: bool, steps: int = 35, depth: int = 4):
    """One sub-game; returns 'survival' or 'capture @ N (reason)'."""
    cop, thief = (0, 0), (3, 3)
    walls, b_left = set(), 14
    evader = ResolvingEvader(variant, steps)
    squeeze = StallSqueeze() if hook else None
    hook_walls = []
    for step in range(1, steps + 1):
        nxt = evader.move(cop, thief, walls, steps - step + 1)
        if nxt is None:
            return f"capture @ {step} (rule 47)", hook_walls
        thief = nxt
        if thief == cop:
            return f"capture @ {step} (walked in)", hook_walls
        act = None
        if squeeze is not None:
            act = squeeze.override(cop, thief, list(walls), b_left, steps - step + 1, LEGAL)
            fired = act is not None
        else:
            fired = False
        if act is None:
            act = best_cop_action(
                cop,
                thief,
                list(walls),
                b_left,
                steps - step + 1,
                depth=depth,
                n=N,
                time_budget_s=3.0,
            )
        if act in MOVE_DELTAS:
            dx, dy = MOVE_DELTAS[act]
            q = (cop[0] + dx, cop[1] + dy)
            if 0 <= q[0] < N and 0 <= q[1] < N and q not in walls:
                cop = q
            if cop == thief:
                return f"capture @ {step} (move)", hook_walls
        elif act in PLACE_DIRS and b_left > 0:
            dx, dy = PLACE_DIRS[act]
            cell = (cop[0] + dx, cop[1] + dy)
            if 0 <= cell[0] < N and 0 <= cell[1] < N and cell not in walls:
                walls.add(cell)
                b_left -= 1
                if fired:
                    hook_walls.append((step, cell))
                if cell == thief:
                    return f"capture @ {step} (rule 46)", hook_walls
    return "survival", hook_walls


def main() -> None:
    """Print the (variant x hook) outcome matrix."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--hook", choices=["on", "off", "both"], default="both")
    ap.add_argument("--steps", type=int, default=35)
    args = ap.parse_args()
    arms = {"off": [False], "on": [True], "both": [False, True]}[args.hook]
    print(f"{'variant':<10} {'hook':<5} outcome")
    for variant in VARIANTS:
        for hook in arms:
            outcome, hook_walls = run_match(variant, hook, args.steps)
            extra = f"  hook walls: {hook_walls}" if hook_walls else ""
            print(f"{variant:<10} {'on' if hook else 'off':<5} {outcome}{extra}")


if __name__ == "__main__":
    main()
