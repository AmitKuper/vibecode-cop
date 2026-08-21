"""Cop opponent pool for THIEF distillation (sweep cops, hook cops, chasers).

The sweep cop is the yanell11 strategy parameterized — line position,
orientation, and sweep direction are randomized per episode so students
learn partition-avoidance as a concept, not a memorized column.
"""

from __future__ import annotations

import random

from barrier_distill.teacher import SearchHookTeacher
from cop_worker.rl.action_space import MOVE_DELTAS, PLACE_DIRS
from cop_worker.rl.pursuit_search import best_cop_action

N = 7
_MOVE_NAME = {tuple(d): a for a, d in MOVE_DELTAS.items()}
_PLACE_NAME = {tuple(d): a for a, d in PLACE_DIRS.items()}


def _step_toward(src, dst):
    dx = (dst[0] > src[0]) - (dst[0] < src[0])
    dy = 0 if dx else (dst[1] > src[1]) - (dst[1] < src[1])
    return _MOVE_NAME.get((dx, dy), "STAY")


class SweepCop:
    """Guard-column line builder with one self-door, then a minimax hunt."""

    def __init__(self, rng: random.Random) -> None:
        self.axis = rng.choice((0, 1))  # 0: vertical line x=k, 1: horizontal
        self.k = rng.choice((2, 3, 4))
        self.guard = self.k + rng.choice((-1, 1))
        self.from_end = rng.choice((0, N - 1))

    def reset(self) -> None:
        pass

    def _ax(self, p):  # coordinate along the line axis / across it
        return (p[0], p[1]) if self.axis == 0 else (p[1], p[0])

    def _mk(self, across, along):
        return (across, along) if self.axis == 0 else (along, across)

    def action(self, state, rng: random.Random, scent=None) -> str:
        cop, thief = tuple(state.cop_position), tuple(state.thief_position)
        walls = {tuple(b) for b in state.barriers}
        b_left = int(state.cop_barriers_remaining)
        line_open = [self._mk(self.k, j) for j in range(N) if self._mk(self.k, j) not in walls]
        c_across, c_along = self._ax(cop)
        if c_across != self.guard:  # phase A: reach the guard lane
            return _step_toward(cop, self._mk(self.guard, c_along))
        if len(line_open) > 1 and b_left > 0:  # phase B: seal to one door
            target = self._mk(self.k, c_along)
            if target in line_open and target != thief:
                delta = (target[0] - cop[0], target[1] - cop[1])
                return _PLACE_NAME.get(delta, "STAY")
            order = sorted(line_open, key=lambda c: abs(self._ax(c)[1] - self.from_end))
            nxt = order[0] if order[0] != thief else (order[1] if len(order) > 1 else order[0])
            return _step_toward(cop, self._mk(self.guard, self._ax(nxt)[1]))
        return best_cop_action(  # phase C: hunt on the partitioned board
            cop, thief, list(walls), b_left, 35, depth=4, n=N, time_budget_s=1.0
        )


class OperatorPocketCop:
    """The operator's adaptive pocketing (2026-08-21, beat the champion 6-0):
    cut-reducing walls + a short herding line + minimax hunt. Wraps the
    reproducible lab cop so training sees the exact recorded strategy."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        from pocketer_lab import AdaptivePocketer

        self._p = AdaptivePocketer()

    def action(self, state, rng: random.Random, scent=None) -> str:
        cop, thief = tuple(state.cop_position), tuple(state.thief_position)
        self._p.b_left = int(state.cop_barriers_remaining)
        kind, val = self._p.act(cop, thief, {tuple(b) for b in state.barriers})
        delta = (val[0] - cop[0], val[1] - cop[1])
        return (_PLACE_NAME if kind == "place" else _MOVE_NAME).get(delta, "STAY")


class OperatorLineCop:
    """The operator's line-partition hunt (record 20260821-203028): wall a
    partial lane beside the thief leaving one door, cross, hunt with the
    production minimax. Parameterized (axis, lane, door end, length) so
    students learn the concept, not the recorded column."""

    def __init__(self, rng: random.Random) -> None:
        self.axis = rng.choice((0, 1))
        self.k = rng.choice((2, 3, 4))
        self.stand = self.k + rng.choice((-1, 1))
        door_at_far = rng.choice((True, False))
        length = rng.choice((4, 5))
        alongs = range(length) if door_at_far else range(N - length, N)
        self.line = [self._mk(self.k, j) for j in alongs]

    def reset(self) -> None:
        pass

    def _mk(self, across, along):
        return (across, along) if self.axis == 0 else (along, across)

    def action(self, state, rng: random.Random, scent=None) -> str:
        cop, thief = tuple(state.cop_position), tuple(state.thief_position)
        walls = {tuple(b) for b in state.barriers}
        b_left = int(state.cop_barriers_remaining)
        for cell in self.line:
            if cell in walls or b_left == 0:
                continue
            stand_cell = self._mk(self.stand, cell[1] if self.axis == 0 else cell[0])
            if cop == stand_cell and cell != thief:
                delta = (cell[0] - cop[0], cell[1] - cop[1])
                return _PLACE_NAME.get(delta, "STAY")
            step = _step_toward(cop, stand_cell)
            dx, dy = MOVE_DELTAS.get(step, (0, 0))
            q = (cop[0] + dx, cop[1] + dy)
            if q not in walls and q != thief:
                return step
            break  # build lane blocked: give up the line, hunt with what stands
        return best_cop_action(cop, thief, list(walls), b_left, 35, depth=4, n=N, time_budget_s=1.0)


class GreedyChaser:
    """Steps to minimize Manhattan distance; never places walls."""

    def reset(self) -> None:
        pass

    def action(self, state, rng: random.Random, scent=None) -> str:
        cop, thief = tuple(state.cop_position), tuple(state.thief_position)
        walls = {tuple(b) for b in state.barriers}
        best, best_d = "STAY", 99
        for name, (dx, dy) in MOVE_DELTAS.items():
            q = (cop[0] + dx, cop[1] + dy)
            if not (0 <= q[0] < N and 0 <= q[1] < N) or q in walls:
                continue
            d = abs(q[0] - thief[0]) + abs(q[1] - thief[1])
            if d < best_d:
                best_d, best = d, name
        return best


class StackCop:
    """The production cop stack (minimax + optional stall-squeeze) as opponent."""

    def __init__(self, hook: bool) -> None:
        self._teacher = SearchHookTeacher(hook=hook, time_budget_s=1.0)

    def reset(self) -> None:
        self._teacher.reset()

    def action(self, state, rng: random.Random, scent=None) -> str:
        from cop_worker.rl.action_space import COP_ACTIONS

        return self._teacher.action(state, list(COP_ACTIONS))


class FamilyCop:
    """A classic training-family cop (the legacy harness opponents)."""

    def __init__(self, family: str) -> None:
        self.family = family
        self.variant = family  # shows up in episode metadata
        self.reset()

    def reset(self) -> None:
        from cop_worker.belief_engine import BeliefEngine

        self._belief = BeliefEngine(N, "cop")

    def action(self, state, rng: random.Random, scent=None) -> str:
        import cop_worker.rl.train_recurrent as _pkg

        opp_scent = scent.cop_observation_scent() if scent is not None else None
        if opp_scent is not None:
            barriers = [tuple(b) for b in state.barriers]
            self._belief = self._belief.predict(barriers).observe_scent(opp_scent, barriers)
        return _pkg._opponent_action(
            state, "cop", self.family, rng,
            historical_policy=None, opponent_scent=opp_scent, opponent_belief=self._belief,
        )  # fmt: skip


LEGACY_FAMILIES = (
    "belief_pursuit_evasion",
    "anti_loop",
    "targeted_exploit",
    "deceptive_language",
    "scent_following",
    "local_adversarial_ensemble",
    "corridor_cutting",
    "random",
    "wall",
)


def make_cop_pool(rng: random.Random) -> list:
    """One thief-collection cycle: sweeps + BOTH recorded operator strategies
    + the FULL classic family set — the merged curriculum (the sweep-only
    corpus scored 0.374 on the legacy harness vs the champion's 0.827;
    narrow pools make narrow students)."""
    return [
        SweepCop(rng),
        SweepCop(rng),
        OperatorPocketCop(),
        OperatorLineCop(rng),
        OperatorLineCop(rng),
        StackCop(hook=True),
        GreedyChaser(),
        *(FamilyCop(f) for f in LEGACY_FAMILIES),
    ]
