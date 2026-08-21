"""Pocketer lab: the operator's recorded cop strategies as scripted cops.

Three arms modeled on the recorded human-vs-model games (2026-08-21/22):
adaptive pocketing, the line-partition hunt, and the cage-cork. Each runs
against the old cut-blind thief and the current production thief.

MEASUREMENT RULE: verdicts are only valid at IDLE CPU with the 5s search
budgets below. Earlier runs under training load throttled the scripted
cops' minimax and reported false thief survivals (the 1ff0ed4 "cage
survival" was such an artifact). Idle truth at 1ff0ed4: pocket SURVIVAL,
line-hunt capture @20, cage capture @32 — a full-depth wall cop still
beats the thief endgame, consistent with walls flipping the 7x7 game
value. The counters that map to real opponents (line_sweep_lab,
corridor_lab confined row) hold at idle.

Usage:  python scripts/pocketer_lab.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for _p in (str(_REPO), str(_REPO / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from cop_worker.rl.action_space import MOVE_DELTAS, PLACE_DIRS
from cop_worker.rl.line_escape import LineEscape
from cop_worker.rl.pursuit_search import best_cop_action, best_thief_action
from cop_worker.rl.sealability import ORTHO, sealability
from cop_worker.rl.stall_squeeze import survival_layers

N = 7
LEGAL_THIEF = ["N", "S", "E", "W", "STAY"]


class AdaptivePocketer:
    """The operator's recorded pattern: a SHORT herding line first (3-4 walls
    on the thief's side, like the recorded col-3 openings), then chase with
    the production minimax while opportunistically placing any adjacent wall
    that strictly reduces the thief's escape cut. Rule 47 finishes."""

    def __init__(self) -> None:
        self.b_left = 14
        self.line_col: int | None = None

    def _cut_wall(self, cop, thief, walls):
        base = sealability(thief, cop, walls, N)
        best_cell, best_val = None, base
        for dx, dy in ORTHO:
            cell = (cop[0] + dx, cop[1] + dy)
            if not (0 <= cell[0] < N and 0 <= cell[1] < N) or cell in walls or cell == thief:
                continue
            exits = sum(
                1
                for dx2, dy2 in ORTHO
                if 0 <= cop[0] + dx2 < N
                and 0 <= cop[1] + dy2 < N
                and (cop[0] + dx2, cop[1] + dy2) not in walls | {cell}
            )
            if exits < 2:
                continue
            val = sealability(thief, cop, walls | {cell}, N)
            if val < best_val:
                best_val, best_cell = val, cell
        return best_cell

    def act(self, cop, thief, walls):
        if self.b_left > 0:
            cell = self._cut_wall(cop, thief, walls)
            if cell is not None:
                self.b_left -= 1
                return ("place", cell)
        if self.line_col is None:
            self.line_col = min(N - 2, max(1, thief[0] - 2 if thief[0] >= cop[0] else thief[0] + 2))
        line = [(self.line_col, y) for y in range(4) if (self.line_col, y) not in walls]
        if line and self.b_left > 0 and len(walls) < 4:
            target = line[0]
            guard = (self.line_col - 1 if self.line_col > cop[0] else self.line_col + 1, target[1])
            if cop == guard or (abs(cop[0] - target[0]) + abs(cop[1] - target[1]) == 1):
                if target != thief:
                    self.b_left -= 1
                    return ("place", target)
            dx = (guard[0] > cop[0]) - (guard[0] < cop[0])
            dy = 0 if dx else (guard[1] > cop[1]) - (guard[1] < cop[1])
            q = (cop[0] + dx, cop[1] + dy)
            if 0 <= q[0] < N and 0 <= q[1] < N and q not in walls and q != thief:
                return ("move", q)
        act = best_cop_action(
            cop, thief, list(walls), self.b_left, 35, depth=4, n=N, time_budget_s=5.0
        )
        if act in PLACE_DIRS and self.b_left > 0:
            dx, dy = PLACE_DIRS[act]
            cell = (cop[0] + dx, cop[1] + dy)
            if 0 <= cell[0] < N and 0 <= cell[1] < N and cell not in walls:
                self.b_left -= 1
                return ("place", cell)
            return ("move", cop)
        dx, dy = MOVE_DELTAS.get(act, (0, 0))
        q = (cop[0] + dx, cop[1] + dy)
        return ("move", q) if 0 <= q[0] < N and 0 <= q[1] < N and q not in walls else ("move", cop)


class LineHunter:
    """The operator's SECOND winning strategy (record 20260821-203028): wall a
    column beside the thief (x=3, y=0..4), leaving a south door, then walk the
    thief's side and hunt with the production minimax + remaining walls. The
    pre-cross thief sat on the cop's side of the line and died in the strip."""

    def __init__(self) -> None:
        self.b_left = 14
        self.line = [(3, y) for y in range(5)]

    def act(self, cop, thief, walls):
        for cell in self.line:
            if cell in walls or self.b_left == 0:
                continue
            stand = (2, cell[1])  # build from the west lane, like the record
            if cop == stand and cell != thief:
                self.b_left -= 1
                return ("place", cell)
            dx = (stand[0] > cop[0]) - (stand[0] < cop[0])
            dy = 0 if dx else (stand[1] > cop[1]) - (stand[1] < cop[1])
            q = (cop[0] + dx, cop[1] + dy)
            if 0 <= q[0] < N and 0 <= q[1] < N and q not in walls and q != thief:
                return ("move", q)
            break
        act = best_cop_action(
            cop, thief, list(walls), self.b_left, 35, depth=4, n=N, time_budget_s=5.0
        )
        if act in PLACE_DIRS and self.b_left > 0:
            dx, dy = PLACE_DIRS[act]
            cell = (cop[0] + dx, cop[1] + dy)
            if 0 <= cell[0] < N and 0 <= cell[1] < N and cell not in walls:
                self.b_left -= 1
                return ("place", cell)
            return ("move", cop)
        dx, dy = MOVE_DELTAS.get(act, (0, 0))
        q = (cop[0] + dx, cop[1] + dy)
        return ("move", q) if 0 <= q[0] < N and 0 <= q[1] < N and q not in walls else ("move", cop)


class CageCop(AdaptivePocketer):
    """The operator's cage-cork (records 20260821-2122/2123, both wins):
    partial south column with a NORTH door, loop around it, then cork the
    thief's quadrant with two corner walls + the cop's own body as the
    door. The finish reuses the pocketer (whose cut walls, with cop-blocked
    sealability, are exactly the recorded cage corners)."""

    LINE = ((3, 3), (3, 4), (3, 5), (3, 6))

    def act(self, cop, thief, walls):
        for cell in self.LINE:
            if cell in walls or self.b_left == 0:
                continue
            stand = (2, cell[1])
            if cop == stand and cell != thief:
                self.b_left -= 1
                return ("place", cell)
            dx = (stand[0] > cop[0]) - (stand[0] < cop[0])
            dy = 0 if dx else (stand[1] > cop[1]) - (stand[1] < cop[1])
            q = (cop[0] + dx, cop[1] + dy)
            if 0 <= q[0] < N and 0 <= q[1] < N and q not in walls and q != thief:
                return ("move", q)
            break
        return super().act(cop, thief, walls)


def _blind_move(thief, cop, walls, steps_left, cache):
    """The OLD confined-mode scoring (no sealability): surv, mobility, dist."""
    wk = frozenset(walls)
    if wk not in cache:
        cache[wk] = survival_layers(wk, N)
    layers, idx = cache[wk]
    s = max(0, min(steps_left - 1, 35))
    best, key = thief, (-1, -1, -1)
    for dx, dy in (*ORTHO, (0, 0)):
        q = (thief[0] + dx, thief[1] + dy)
        if not (0 <= q[0] < N and 0 <= q[1] < N) or q in walls or q == cop or q not in idx:
            continue
        surv = 1 if layers[s][idx[cop]][idx[q]] else 0
        mob = sum(
            1
            for dx2, dy2 in ORTHO
            if 0 <= q[0] + dx2 < N and 0 <= q[1] + dy2 < N and (q[0] + dx2, q[1] + dy2) not in walls
        )
        k = (surv, mob, min(abs(q[0] - cop[0]) + abs(q[1] - cop[1]), 3))
        if k > key:
            key, best = k, q
    return best


HUNTERS = {"pocket": AdaptivePocketer, "line-hunt": LineHunter, "cage": CageCop}


def run(aware: bool, hunter: str = "pocket"):
    cop, thief = (0, 0), (3, 3)
    walls: set = set()
    pocketer = HUNTERS[hunter]()
    escape = LineEscape() if aware else None
    cache: dict = {}
    for step in range(1, 36):
        exits = [
            (thief[0] + dx, thief[1] + dy)
            for dx, dy in ORTHO
            if 0 <= thief[0] + dx < N and 0 <= thief[1] + dy < N
            and (thief[0] + dx, thief[1] + dy) not in walls
        ]  # fmt: skip
        if not exits:
            return f"capture @ {step} (rule 47)"
        if aware:
            act = best_thief_action(
                cop, thief, list(walls), 36 - step, depth=4, n=N,
                cop_barriers_left=pocketer.b_left, time_budget_s=5.0,
            )  # fmt: skip
            legal = [a for a, (dx, dy) in MOVE_DELTAS.items()
                     if 0 <= thief[0] + dx < N and 0 <= thief[1] + dy < N
                     and (thief[0] + dx, thief[1] + dy) not in walls]  # fmt: skip
            act = (
                escape.override(thief, cop, list(walls), pocketer.b_left, 36 - step, act, legal)
                or act
            )
            dx, dy = MOVE_DELTAS.get(act, (0, 0))
            q = (thief[0] + dx, thief[1] + dy)
            if 0 <= q[0] < N and 0 <= q[1] < N and q not in walls and q != cop:
                thief = q
        else:
            thief = _blind_move(thief, cop, walls, 36 - step, cache)
        kind, val = pocketer.act(cop, thief, walls)
        if kind == "place":
            walls.add(val)
            if val == thief:
                return f"capture @ {step} (rule 46)"
        else:
            cop = val
            if cop == thief:
                return f"capture @ {step} (move)"
    return "survival"


def main() -> None:
    for hunter in ("pocket", "line-hunt", "cage"):
        for label, aware in (("cut-BLIND thief (old scoring)", False), ("sealability-aware", True)):
            print(f"{label:<30} vs {hunter:<9} cop -> {run(aware, hunter)}")


if __name__ == "__main__":
    main()
