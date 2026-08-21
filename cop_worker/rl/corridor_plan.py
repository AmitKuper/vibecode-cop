"""Corridor plan: the cop's line-partition strategy (yanell11's, industrialized).

Against an evader that plain pursuit provably cannot catch (open-board
pursuit is thief-win), the winning plan demonstrated live on 2026-08-21 is:
build a wall LINE across the board from a guard lane, leave exactly ONE
door, walk through it, and hunt in the halved region where the remaining
wall budget can pocket. This module drives phases A/B (reach the guard
lane, seal the line to one door); once the line stands, it goes silent and
the existing stack (minimax + stall-squeeze) hunts in the strip — the
combination that captured our own thief at 26 in the lab.

Floor discipline (same as the stall-squeeze): the plan activates only on a
sustained non-converging chase — never during a closing pursuit, never at
capture-in-hand, never without the wall budget to finish. A weak thief is
captured by minimax long before the trigger can fire.
"""

from __future__ import annotations

ORTHO = ((-1, 0), (1, 0), (0, -1), (0, 1))
_MOVE = {(-1, 0): "W", (1, 0): "E", (0, -1): "N", (0, 1): "S"}
_PLACE = {(-1, 0): "PLACE_W", (1, 0): "PLACE_E", (0, -1): "PLACE_N", (0, 1): "PLACE_S"}
MIN_STEP = 8  # never before minimax had a real chance to converge
MIN_BUDGET = 9  # line (<= 6 placements) + pocket reserve
STABLE_TURNS = 6


class CorridorPlan:
    """Per-sub-game stateful line builder (cop only)."""

    def __init__(self, n: int = 7) -> None:
        self.n = n
        self.reset()

    def reset(self) -> None:
        self._dists: list[int] = []
        self._active = False
        self._axis = 0
        self._k = 0
        self._guard = 0
        self._done = False

    def _trigger(self, d: int, step: int, barriers_left: int) -> bool:
        self._dists.append(d)
        if self._active or self._done:
            return self._active
        recent = self._dists[-STABLE_TURNS:]
        if (
            step >= MIN_STEP
            and barriers_left >= MIN_BUDGET
            and len(recent) == STABLE_TURNS
            and min(recent) >= 2
            and max(recent) <= 6  # a CLOSE stall — a far thief is not evading yet
            and max(recent) - min(recent) <= 1  # true oscillation, never a slow close
        ):
            self._active = True
        return self._active

    def _adopt(self, cop, thief) -> None:
        """Line 2 away from the thief on the widest axis; guard on our side."""
        axis = 0 if abs(thief[0] - cop[0]) >= abs(thief[1] - cop[1]) else 1
        sign = 1 if thief[axis] >= cop[axis] else -1
        k = min(self.n - 2, max(1, thief[axis] - 2 * sign))
        self._axis, self._k, self._guard = axis, k, k - sign

    def _cell(self, across: int, along: int):
        return (across, along) if self._axis == 0 else (along, across)

    def override(self, cop, thief, barriers, barriers_left, step, legal) -> str | None:
        """A build move/placement, or None (minimax + stall-squeeze play)."""
        d = abs(cop[0] - thief[0]) + abs(cop[1] - thief[1])
        if d <= 1:
            return None  # capture in hand — never preempt it
        if not self._trigger(d, step, barriers_left):
            return None
        if not self._active or self._done:
            return None
        if self._k == 0 and self._guard == 0 and not self._done:
            self._adopt(cop, thief)
        walls = set(map(tuple, barriers))
        line_open = [
            self._cell(self._k, j) for j in range(self.n) if self._cell(self._k, j) not in walls
        ]
        if len(line_open) <= 1 or barriers_left <= 2:
            self._done = True  # line stands (one door) — hand over to the hunt
            return None
        c_across = cop[self._axis]
        c_along = cop[1 - self._axis]
        if c_across != self._guard:  # phase A: reach the guard lane
            delta = (1 if self._guard > c_across else -1, 0)
            move = delta if self._axis == 0 else (0, delta[0])
            name = _MOVE[move]
            return name if name in legal else None
        target = self._cell(self._k, c_along)  # phase B: seal from the guard lane
        if target in line_open and target != tuple(thief):
            move = (self._k - self._guard, 0) if self._axis == 0 else (0, self._k - self._guard)
            name = _PLACE[move]
            return name if name in legal else None
        nxt = min(line_open, key=lambda c: abs(c[1 - self._axis] - c_along))
        along_delta = 1 if nxt[1 - self._axis] > c_along else -1
        move = (0, along_delta) if self._axis == 0 else (along_delta, 0)
        name = _MOVE[move]
        return name if name in legal else None
