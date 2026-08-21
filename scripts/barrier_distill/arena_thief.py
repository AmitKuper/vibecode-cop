"""Thief-side arena: student checkpoint or search baseline vs the cop pool.

Usage: python scripts/barrier_distill/arena_thief.py --policy stack|minimax|<ckpt.pt>

Cop pool: four FIXED-seed sweep cops (deterministic parameter variants), the
production stack cop with and without the stall-squeeze, and a greedy
chaser. Same joint-action physics and observation pipeline as collect.py.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ["COPTHIEF_SCENT_MODEL"] = "chebyshev"
os.environ["COPTHIEF_UNIFORM_BELIEF"] = "1"

RESULTS = _REPO / "results" / "barrier_distill"


class StudentThief:
    def __init__(self, path: Path) -> None:
        from barrier_distill.models import load_student

        self.net, self.meta = load_student(str(path))
        self.hidden = None

    def reset(self) -> None:
        self.hidden = None

    def action(self, state, obs, mask, legal) -> str:
        import torch

        from cop_worker.rl.action_space import THIEF_ACTIONS

        with torch.no_grad():
            logits, _v, self.hidden = self.net(obs.unsqueeze(0), self.hidden)
        logits = logits[0].masked_fill(~mask, -1e9)
        return THIEF_ACTIONS[int(logits.argmax())]


class SearchThief:
    """Baseline: the production thief with or without confined-mode."""

    def __init__(self, escape: bool) -> None:
        from barrier_distill.teacher import ThiefStackTeacher

        self.teacher = ThiefStackTeacher(time_budget_s=1.0)
        if not escape:
            self.teacher.escape.override = lambda *a, **k: None  # minimax-only arm

    def reset(self) -> None:
        self.teacher.reset()

    def action(self, state, obs, mask, legal) -> str:
        return self.teacher.action(state, legal)


def play(thief_pol, cop_pol, seed: int) -> dict:
    from cop_worker.belief_engine import BeliefEngine
    from cop_worker.domain.transition import apply_joint_action
    from cop_worker.rl.train_recurrent.observation import _observation
    from cop_worker.rl.train_recurrent.sim import _initial_state, _legal
    from cop_worker.scent import make_scent_fields

    rng = random.Random(seed)
    state = _initial_state(rng, random_start=False)
    scent = make_scent_fields(state.grid_size)
    belief = BeliefEngine(state.grid_size, "thief")
    thief_pol.reset()
    cop_pol.reset()
    while state.turn < 35:
        legal = _legal(state, "thief")
        obs, mask = _observation(state, "thief", scent, belief, legal, 1)
        t_act = thief_pol.action(state, obs, mask, legal)
        c_act = cop_pol.action(state, rng)
        result = apply_joint_action(state, c_act, t_act)
        state = result.new_state
        scent = scent.update(state.cop_position, state.thief_position)
        if result.outcome.value != "ongoing":
            return {"outcome": result.outcome.value, "step": state.turn}
    return {"outcome": "thief_win", "step": 35}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True, help="stack | minimax | <checkpoint>")
    args = ap.parse_args()
    from barrier_distill.cops import (
        GreedyChaser,
        OperatorLineCop,
        OperatorPocketCop,
        StackCop,
        SweepCop,
    )

    if args.policy == "stack":
        thief = SearchThief(escape=True)
    elif args.policy == "minimax":
        thief = SearchThief(escape=False)
    else:
        thief = StudentThief(RESULTS / args.policy)
    opponents = [
        *((f"sweep{i}", SweepCop(random.Random(i))) for i in range(4)),
        ("op-pocket", OperatorPocketCop()),
        *((f"op-line{i}", OperatorLineCop(random.Random(10 + i))) for i in range(2)),
        ("stack-hook", StackCop(hook=True)),
        ("stack-plain", StackCop(hook=False)),
        ("greedy", GreedyChaser()),
    ]
    rows = []
    for name, cop in opponents:
        for i in range(2):
            r = play(thief, cop, seed=200 + i)
            rows.append({"cop": name, "run": i, **r})
            print(f"{args.policy:>12} vs {name:<12} run{i}: {r}", flush=True)
    wins = sum(r["outcome"] == "thief_win" for r in rows)
    out = RESULTS / f"arena_thief_{args.policy.replace('.pt', '')}.json"
    out.write_text(
        json.dumps(
            {"policy": args.policy, "thief_wins": wins, "games": len(rows), "rows": rows}, indent=1
        ),
        encoding="utf-8",
    )
    print(f"TOTAL {args.policy}: {wins}/{len(rows)} thief survivals -> {out}", flush=True)


if __name__ == "__main__":
    main()
