"""Line-sweep lab: our thief vs the partition cop that beat us (yanell11 g03/g05).

The cop clone builds the recorded wall line (guard col x=2, line col x=3,
sweeping y=0..6 on STAY-place turns) and then hunts with our FULL minimax —
i.e., it is a strictly stronger executor of their strategy than their actual
cop. Thief arms: production best_thief_action d4 with the LineEscape
override off/on.

Usage:  python scripts/line_sweep_lab.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from cop_worker.rl.action_space import MOVE_DELTAS
from cop_worker.rl.line_escape import LineEscape
from cop_worker.rl.pursuit_search import best_cop_action, best_thief_action

N = 7
GUARD_COL, LINE_COL = 2, 3
LEGAL_THIEF = ["N", "S", "E", "W", "STAY"]


class LineSweepCop:
    """Phase A: reach the guard column. Phase B: sweep the wall line.
    Phase C: hunt with production minimax on the partitioned board."""

    def __init__(self) -> None:
        self.b_left = 14

    def act(self, cop, thief, walls):
        line_open = [(LINE_COL, y) for y in range(N) if (LINE_COL, y) not in walls]
        if cop[0] < GUARD_COL:  # phase A
            q = (cop[0] + 1, cop[1])
            return ("move", q) if q not in walls and q != thief else ("move", cop)
        if len(line_open) > 1 and self.b_left > 0 and cop[0] == GUARD_COL:  # phase B
            # Seal the line down to ONE remaining cell — the cop's own door
            # for phase C (their recorded trick: gap at the thief-blocked row).
            target = (LINE_COL, cop[1])
            if target in line_open and target != thief:
                self.b_left -= 1
                return ("place", target)
            nxt = min(line_open, key=lambda c: abs(c[1] - cop[1]))
            dy = (nxt[1] > cop[1]) - (nxt[1] < cop[1])
            q = (cop[0], cop[1] + dy)
            if 0 <= q[1] < N and q not in walls and q != thief:
                return ("move", q)
            return ("move", cop)
        # phase C: hunt (minimax may also place pocket walls)
        act = best_cop_action(
            cop, thief, list(walls), self.b_left, 35, depth=4, n=N, time_budget_s=1.0
        )
        if act.startswith("PLACE_") and self.b_left > 0:
            from cop_worker.rl.action_space import PLACE_DIRS

            dx, dy = PLACE_DIRS[act]
            cell = (cop[0] + dx, cop[1] + dy)
            if 0 <= cell[0] < N and 0 <= cell[1] < N and cell not in walls:
                self.b_left -= 1
                return ("place", cell)
            return ("move", cop)
        dx, dy = MOVE_DELTAS.get(act, (0, 0))
        q = (cop[0] + dx, cop[1] + dy)
        return ("move", q) if 0 <= q[0] < N and 0 <= q[1] < N and q not in walls else ("move", cop)


def thief_move(thief, cop, walls, cop_b_left, steps_left, escape: LineEscape | None):
    barriers = list(walls)
    action = best_thief_action(
        cop, thief, barriers, steps_left, depth=4, n=N,
        cop_barriers_left=cop_b_left, time_budget_s=1.0,
    )  # fmt: skip
    fired = False
    if escape is not None:
        legal = [
            a
            for a, (dx, dy) in MOVE_DELTAS.items()
            if 0 <= thief[0] + dx < N
            and 0 <= thief[1] + dy < N
            and (thief[0] + dx, thief[1] + dy) not in walls
        ]
        override = escape.override(thief, cop, barriers, cop_b_left, steps_left, action, legal)
        if override is not None:
            action, fired = override, True
    dx, dy = MOVE_DELTAS.get(action, (0, 0))
    q = (thief[0] + dx, thief[1] + dy)
    if not (0 <= q[0] < N and 0 <= q[1] < N) or q in walls or q == cop:
        q = thief
    return q, fired


def run(with_escape: bool):
    cop, thief = (0, 0), (3, 3)
    walls: set = set()
    sweep = LineSweepCop()
    escape = LineEscape() if with_escape else None
    fires = 0
    for step in range(1, 36):
        # thief-first order, matching the wire
        exits = [
            (thief[0] + dx, thief[1] + dy)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
            if 0 <= thief[0] + dx < N and 0 <= thief[1] + dy < N
            and (thief[0] + dx, thief[1] + dy) not in walls
        ]  # fmt: skip
        if not exits:
            return f"capture @ {step} (rule 47)", fires
        thief, fired = thief_move(thief, cop, walls, sweep.b_left, 36 - step, escape)
        fires += int(fired)
        kind, val = sweep.act(cop, thief, walls)
        if kind == "place":
            walls.add(val)
            if val == thief:
                return f"capture @ {step} (rule 46)", fires
        else:
            cop = val
            if cop == thief:
                return f"capture @ {step} (move)", fires
    return "survival", fires


def main() -> None:
    for label, arm in (("escape OFF (the losing thief)", False), ("escape ON", True)):
        outcome, fires = run(arm)
        print(f"{label:<28} -> {outcome}   (escape fired {fires}x)")


if __name__ == "__main__":
    main()
