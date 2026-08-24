"""Scripted cops for pocketer_lab: the operator's recorded strategies.

Split out of pocketer_lab.py (150-line rule); the lab runner imports HUNTERS.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for _p in (str(_REPO), str(_REPO / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from cop_worker.rl.action_space import MOVE_DELTAS, PLACE_DIRS
from cop_worker.rl.pursuit_search import best_cop_action
from cop_worker.rl.sealability import ORTHO, sealability

N = 7


class AdaptivePocketer:
    """Operator pattern: short herding line, then minimax chase with
    opportunistic cut-reducing walls. Rule 47 finishes."""

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
    """Operator cage-cork (records 20260821-2122/2123): partial south column
    with a NORTH door, then the pocketer finish corks the quadrant."""

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


HUNTERS = {"pocket": AdaptivePocketer, "line-hunt": LineHunter, "cage": CageCop}
