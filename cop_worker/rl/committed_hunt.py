"""Committed hunt: the operator's cage strategy as a production cop plan.

Measured 2026-08-22 (scripted ports of the operator's recorded games vs the
full evader roster): the COMMITTED plan — a 4-wall partial line from board
center to an edge, then an active hunt with cut-reducing walls — captures
the exact-table evaders that survive every reactive cop we have (confined
@20, minimax-dance @23 by rule 47 for the line variant; @32/@33 for the
cage variant). A greedy per-turn cage was tried first and thrashed exactly
like the thief-side greedy terms did: the dance de-synchronizes any cop
that re-derives its target every turn. Structure wins; this module is the
structure.

Phases: IDLE (defer to pursuit until the net-progress gate proves the
chase is going nowhere) -> BUILD (walk the stand lane, place the line,
mirrored to the thief's board half) -> HUNT (place any cop-adjacent wall
that strictly reduces a dance-target's escape cut; otherwise defer, so the
chain's minimax supplies the chase moves). The line is abandoned, never
forced, if its lane is blocked.
"""

from __future__ import annotations

from cop_worker.rl.action_space import MOVE_DELTAS
from cop_worker.rl.sealability import ORTHO, sealability
from cop_worker.rl.stall_squeeze import _PLACE

FUSE = 6  # consecutive no-net-progress turns before committing to the plan
MIN_BUDGET = 6  # walls needed: 4 line + at least 2 cage
MIN_STEPS = 18  # measured kill takes ~15-20 steps from commit
CUT_MAX = 4
MAX_HUNT_WALLS = 6

_MOVE_NAME = {tuple(d): a for a, d in MOVE_DELTAS.items()}


def _step_toward(src, dst) -> str:
    dx = (dst[0] > src[0]) - (dst[0] < src[0])
    dy = 0 if dx else (dst[1] > src[1]) - (dst[1] < src[1])
    return _MOVE_NAME.get((dx, dy), "STAY")


class CommittedHunt:
    """Per-sub-game committed line + hunt plan (cop only).

    ``endgame_only`` (production, behind CorridorPlan): never builds a line
    of its own — it exclusively closes stalled close-range endgames with
    cut walls. Every full-line + corridor pairing measured worse: the two
    plans race and interfere (mobility/mirror2 flipped to survival)."""

    def __init__(self, n: int = 7, endgame_only: bool = False) -> None:
        self.n = n
        self.endgame_only = endgame_only
        self.reset()

    def reset(self) -> None:
        self._min_d = None
        self._evade = 0
        self._prev_thief = None
        self._line: list | None = None
        self._stand = None
        self._axis = 0
        self._hunt_walls = 0

    def _trigger(self, cop, thief) -> None:
        """Commit once: line column at the thief, span from board center
        toward the thief's half, stand lane on the cop's side. (A
        between-the-lanes variant was tried and measured worse — mobility
        and confined both regressed to survival.)"""
        self._axis = 0
        k = min(self.n - 2, max(1, thief[0]))
        self._stand = k - 1 if cop[0] <= thief[0] else k + 1
        mid = self.n // 2
        ys = range(mid, self.n) if thief[1] >= mid else range(mid, -1, -1)
        self._line = [(k, y) for y in ys]

    def override(
        self, cop, thief, barriers, barriers_left, steps_left, legal_actions
    ) -> str | None:
        cop, thief = tuple(cop), tuple(thief)
        d = abs(cop[0] - thief[0]) + abs(cop[1] - thief[1])
        # Net-progress gate (the only evader signal that neither resets on
        # oscillation nor fires during a converging chase).
        if self._min_d is None or d < self._min_d:
            self._min_d = d
            self._evade = 0
        else:
            self._evade += 1
        prev, self._prev_thief = self._prev_thief, thief
        if d <= 1:  # capture-in-hand: pursuit takes it this half-move
            return None
        walls = frozenset(map(tuple, barriers))
        if self._line is None:
            if self._evade < FUSE:
                return None
            if self.endgame_only:
                # Close-range stalled dance only: ~2 cut walls + a few steps
                # (the corridor strip-stall this mode exists for: d=2, cut 3,
                # 8 walls in hand, game lost by clock).
                if d > 4 or int(barriers_left) < 2 or int(steps_left) < 4:
                    return None
                self._line = []
            elif int(barriers_left) >= MIN_BUDGET and int(steps_left) >= MIN_STEPS:
                self._trigger(cop, thief)
            else:
                return None
        # BUILD: walk the stand lane, place the next open line cell (a cell
        # the thief squats on is skipped, not hovered at — squatting would
        # deadlock the build)
        for cell in self._line:
            if cell in walls or cell == thief or int(barriers_left) <= 0:
                continue
            j = cell[1] if self._axis == 0 else cell[0]
            stand = (self._stand, j) if self._axis == 0 else (j, self._stand)
            if cop == stand:
                delta = (cell[0] - cop[0], cell[1] - cop[1])
                return _PLACE.get(delta)  # _PLACE maps delta -> PLACE_* name
            step = _step_toward(cop, stand)
            dx, dy = MOVE_DELTAS.get(step, (0, 0))
            q = (cop[0] + dx, cop[1] + dy)
            if q not in walls and q != thief and step in legal_actions:
                return step
            break  # lane blocked: abandon the rest of the line, hunt
        # HUNT: cut-reducing wall on either dance cell; else defer to pursuit
        if self._hunt_walls >= MAX_HUNT_WALLS or int(barriers_left) <= 0:
            return None
        targets = {thief: sealability(thief, cop, walls, self.n)}
        if prev is not None and prev != thief and prev not in walls:
            targets[prev] = sealability(prev, cop, walls, self.n)
        if min(targets.values()) > CUT_MAX:
            return None
        best_action, best_key = None, None
        for (dx, dy), name in _PLACE.items():
            if name not in legal_actions:
                continue
            cell = (cop[0] + dx, cop[1] + dy)
            if (
                not (0 <= cell[0] < self.n and 0 <= cell[1] < self.n)
                or cell in walls
                or cell == thief
            ):
                continue
            exits = sum(
                1
                for dx2, dy2 in ORTHO
                if 0 <= cop[0] + dx2 < self.n
                and 0 <= cop[1] + dy2 < self.n
                and (cop[0] + dx2, cop[1] + dy2) not in walls | {cell}
            )
            if exits < 2:  # never wall our own last exits
                continue
            gain = None
            for t, c0 in targets.items():
                if cell == t:
                    continue
                nc = sealability(t, cop, walls | {cell}, self.n)
                if nc < c0 and (gain is None or nc < gain):
                    gain = nc
            if gain is None:
                continue
            key = (gain, abs(cell[0] - thief[0]) + abs(cell[1] - thief[1]))
            if best_key is None or key < best_key:
                best_key, best_action = key, name
        if best_action is not None:
            self._hunt_walls += 1
        return best_action
