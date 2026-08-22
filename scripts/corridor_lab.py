"""Corridor lab: old cop stack vs new (corridor plan) across the thief spectrum.

Sequential thief-first order (the wire's), 35 steps. The regression matrix:
the new cop must capture everything the old cop captured, and convert
evader/confined survivals into captures where the plan can.

Usage:  python scripts/corridor_lab.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for _p in (str(_REPO), str(_REPO / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anti_evader_lab import VARIANTS, ResolvingEvader

from cop_worker.rl.action_space import MOVE_DELTAS, PLACE_DIRS
from cop_worker.rl.corridor_plan import CorridorPlan
from cop_worker.rl.line_escape import LineEscape
from cop_worker.rl.pursuit_search import best_cop_action, best_thief_action
from cop_worker.rl.stall_squeeze import StallSqueeze

N = 7
LEGAL_COP = [*MOVE_DELTAS, *PLACE_DIRS]


def _legal_thief_moves(thief, cop, walls):
    out = []
    for name, (dx, dy) in MOVE_DELTAS.items():
        q = (thief[0] + dx, thief[1] + dy)
        if name == "STAY" or (0 <= q[0] < N and 0 <= q[1] < N and q not in walls and q != cop):
            out.append((name, q))
    return out


def make_thief(kind: str):
    if kind in VARIANTS:
        ev = ResolvingEvader(kind, 35)
        return lambda cop, thief, walls, b_left, sl: ev.move(cop, thief, walls, sl)

    esc = LineEscape() if kind == "confined" else None

    def searcher(cop, thief, walls, b_left, sl, escape=esc):
        act = best_thief_action(
            cop, thief, list(walls), sl, depth=4, n=N,
            cop_barriers_left=b_left, time_budget_s=5.0,
        )  # fmt: skip
        if escape is not None:
            legal = [name for name, _q in _legal_thief_moves(thief, cop, walls)]
            act = escape.override(thief, cop, list(walls), b_left, sl, act, legal) or act
        dx, dy = MOVE_DELTAS.get(act, (0, 0))
        q = (thief[0] + dx, thief[1] + dy)
        return q if (0 <= q[0] < N and 0 <= q[1] < N and q not in walls and q != cop) else thief

    def away(cop, thief, walls, b_left, sl):
        opts = [q for _n, q in _legal_thief_moves(thief, cop, walls)]
        return max(opts, key=lambda q: abs(q[0] - cop[0]) + abs(q[1] - cop[1]))

    return searcher if kind in ("minimax", "confined") else away


def run(kind: str, mode: str):
    """mode: 'old' (squeeze+minimax), 'corridor' (wire default), 'hunt'
    (COPTHIEF_HUNT_MODE / GUI chain)."""
    from cop_worker.rl.committed_hunt import CommittedHunt

    cop, thief = (0, 0), (3, 3)
    walls: set = set()
    b_left = 14
    thief_fn = make_thief(kind)
    plan = CorridorPlan() if mode == "corridor" else None
    hunt = CommittedHunt() if mode == "hunt" else None
    squeeze = StallSqueeze()
    for step in range(1, 36):
        exits = [q for n_, q in _legal_thief_moves(thief, cop, walls) if n_ != "STAY"]
        if not exits:
            return f"capture @ {step} (rule 47)"
        nxt = thief_fn(cop, thief, walls, b_left, 36 - step)
        if nxt is None:
            return f"capture @ {step} (rule 47)"
        thief = nxt
        act = None
        if plan is not None:
            act = plan.override(cop, thief, list(walls), b_left, step, LEGAL_COP)
        if act is None and hunt is not None:
            act = hunt.override(cop, thief, list(walls), b_left, 36 - step, LEGAL_COP)
        if act is None:
            act = squeeze.override(cop, thief, list(walls), b_left, 36 - step, LEGAL_COP)
        if act is None:
            act = best_cop_action(
                cop, thief, list(walls), b_left, 36 - step, depth=4, n=N, time_budget_s=5.0
            )
        if act in PLACE_DIRS and b_left > 0:
            dx, dy = PLACE_DIRS[act]
            cell = (cop[0] + dx, cop[1] + dy)
            if 0 <= cell[0] < N and 0 <= cell[1] < N and cell not in walls:
                walls.add(cell)
                b_left -= 1
                if cell == thief:
                    return f"capture @ {step} (rule 46)"
        elif act in MOVE_DELTAS:
            dx, dy = MOVE_DELTAS[act]
            q = (cop[0] + dx, cop[1] + dy)
            if 0 <= q[0] < N and 0 <= q[1] < N and q not in walls:
                cop = q
            if cop == thief:
                return f"capture @ {step} (move)"
    return "survival"


def main() -> None:
    kinds = [*VARIANTS, "confined", "minimax", "away"]
    print(f"{'thief':<10} {'OLD stack':>16} {'corridor (wire)':>16} {'hunt (GUI)':>16}")
    for kind in kinds:
        row = [run(kind, mode) for mode in ("old", "corridor", "hunt")]
        print(f"{kind:<10} {row[0]:>16} {row[1]:>16} {row[2]:>16}")


if __name__ == "__main__":
    main()
