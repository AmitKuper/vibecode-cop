"""Evaluate a cop policy (student checkpoint or search baseline) in the lab arena.

Usage: python scripts/barrier_distill/arena.py --policy gru_v1.pt
       python scripts/barrier_distill/arena.py --policy minimax|hook

Same joint-action domain loop and observation pipeline as collect.py, so
student and baselines are compared under identical physics.
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
STARTS = [((0, 0), (3, 3)), ((6, 6), (3, 3)), ((0, 6), (3, 2)), ((5, 1), (2, 4))]


class StudentCop:
    """Greedy legal argmax over the trained student, hidden state per episode."""

    def __init__(self, path: Path) -> None:
        from barrier_distill.models import load_student

        self.net, self.meta = load_student(str(path))
        self.hidden = None

    def reset(self) -> None:
        self.hidden = None

    def action(self, state, obs, mask, legal) -> str:
        import torch

        from cop_worker.rl.action_space import COP_ACTIONS

        with torch.no_grad():
            logits, _v, self.hidden = self.net(obs.unsqueeze(0), self.hidden)
        logits = logits[0].masked_fill(~mask, -1e9)
        return COP_ACTIONS[int(logits.argmax())]


class SearchCop:
    """Baseline: the teacher with or without the stall-squeeze hook."""

    def __init__(self, hook: bool) -> None:
        from barrier_distill.teacher import SearchHookTeacher

        self.teacher = SearchHookTeacher(hook=hook, time_budget_s=1.0)

    def reset(self) -> None:
        self.teacher.reset()

    def action(self, state, obs, mask, legal) -> str:
        return self.teacher.action(state, legal)


def play(cop_pol, thief_pol, start, seed: int) -> dict:
    from cop_worker.belief_engine import BeliefEngine
    from cop_worker.domain.transition import apply_joint_action
    from cop_worker.domain.types import DomainState
    from cop_worker.rl.train_recurrent.observation import _observation
    from cop_worker.rl.train_recurrent.sim import _legal
    from cop_worker.scent import make_scent_fields

    rng = random.Random(seed)
    state = DomainState(
        turn=0, grid_size=7, cop_position=start[0], thief_position=start[1],
        barriers=[], cop_barriers_remaining=14, move_history=[],
        scent_grid=[[0.0] * 7 for _ in range(7)],
    )  # fmt: skip
    scent = make_scent_fields(7)
    belief = BeliefEngine(7, "cop")
    cop_pol.reset()
    thief_pol.reset()
    walls = 0
    while state.turn < 35:
        legal = _legal(state, "cop")
        obs, mask = _observation(state, "cop", scent, belief, legal, 1)
        action = cop_pol.action(state, obs, mask, legal)
        walls += int(action.startswith("PLACE_"))
        result = apply_joint_action(state, action, thief_pol.action(state, rng))
        state = result.new_state
        scent = scent.update(state.cop_position, state.thief_position)
        if result.outcome.value != "ongoing":
            return {"outcome": result.outcome.value, "step": state.turn, "walls": walls}
    return {"outcome": "thief_survived", "step": 35, "walls": walls}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True, help="minimax | hook | <checkpoint in results dir>")
    args = ap.parse_args()
    from barrier_distill.thieves import EvaderThief, MinimaxThief, ScriptedThief

    if args.policy in {"minimax", "hook"}:
        cop = SearchCop(hook=args.policy == "hook")
    else:
        cop = StudentCop(RESULTS / args.policy)
    opponents = [
        *(EvaderThief(v) for v in ("mobility", "distance", "center", "mirror2")),
        MinimaxThief(),
        ScriptedThief("away"),
        ScriptedThief("random"),
    ]
    rows = []
    for thief in opponents:
        name = type(thief).__name__ + getattr(thief, "variant", getattr(thief, "style", ""))
        for i, start in enumerate(STARTS):
            r = play(cop, thief, start, seed=100 + i)
            rows.append({"opponent": name, "start": i, **r})
            print(f"{args.policy:>12} vs {name:<20} start{i}: {r}", flush=True)
    wins = sum(r["outcome"] == "cop_win" for r in rows)
    summary = {"policy": args.policy, "wins": wins, "games": len(rows), "rows": rows}
    out = RESULTS / f"arena_{args.policy.replace('.pt', '')}.json"
    out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"TOTAL {args.policy}: {wins}/{len(rows)} cop wins -> {out}", flush=True)


if __name__ == "__main__":
    main()
