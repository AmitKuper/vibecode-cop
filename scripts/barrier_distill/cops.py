"""Cop opponent pool for THIEF distillation (sweep cops, hook cops, chasers).

Parameterized scripted cops live in cops_scripted.py (150-line rule); this
module keeps the operator/production/legacy wrappers and the pool factory,
re-exporting the scripted classes so existing imports keep working.
"""

from __future__ import annotations

import random

from barrier_distill.cops_scripted import (  # noqa: F401  (re-exports)
    _MOVE_NAME,
    _PLACE_NAME,
    GreedyChaser,
    N,
    OperatorLineCop,
    SweepCop,
    _step_toward,
)
from barrier_distill.teacher import SearchHookTeacher


class OperatorPocketCop:
    """The operator's adaptive pocketing (2026-08-21, beat the champion 6-0):
    cut-reducing walls + a short herding line + minimax hunt. Wraps the
    reproducible lab cop so training sees the exact recorded strategy."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        from pocketer_cops import AdaptivePocketer

        self._p = AdaptivePocketer()

    def action(self, state, rng: random.Random, scent=None) -> str:
        cop, thief = tuple(state.cop_position), tuple(state.thief_position)
        self._p.b_left = int(state.cop_barriers_remaining)
        kind, val = self._p.act(cop, thief, {tuple(b) for b in state.barriers})
        delta = (val[0] - cop[0], val[1] - cop[1])
        return (_PLACE_NAME if kind == "place" else _MOVE_NAME).get(delta, "STAY")


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
