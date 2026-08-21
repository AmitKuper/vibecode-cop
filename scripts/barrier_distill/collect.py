"""Collect (observation, teacher-action) episodes for barrier distillation.

Usage: python scripts/barrier_distill/collect.py --seed 1 --episodes 44 --out shard_01.pt

Env is forced to the sighted production regime BEFORE any scent import:
chebyshev scent model + uniform belief (what production actually feeds).
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ["COPTHIEF_SCENT_MODEL"] = "chebyshev"
os.environ["COPTHIEF_UNIFORM_BELIEF"] = "1"

RESULTS = _REPO / "results" / "barrier_distill"


def collect(seed: int, episodes: int, out: Path, role: str = "cop") -> dict:
    """Roll episodes with the full-stack teacher for ``role`` vs its opponent pool."""
    import torch

    from barrier_distill.teacher import SearchHookTeacher, ThiefStackTeacher
    from barrier_distill.thieves import make_pool
    from cop_worker.belief_engine import BeliefEngine
    from cop_worker.domain.transition import apply_joint_action
    from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
    from cop_worker.rl.train_recurrent.observation import _observation
    from cop_worker.rl.train_recurrent.sim import _initial_state, _legal
    from cop_worker.scent import make_scent_fields

    rng = random.Random(seed)
    actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
    episodes_out, place_labels, outcomes = [], 0, {}
    t0 = time.time()
    for ep in range(episodes):
        if role == "cop":
            teacher, opponent = SearchHookTeacher(), None
            pool = make_pool()
            opponent = pool[ep % len(pool)]
        else:
            from barrier_distill.cops import make_cop_pool

            teacher = ThiefStackTeacher()
            pool = make_cop_pool(rng)
            opponent = pool[ep % len(pool)]
        opponent.reset()
        teacher.reset()
        state = _initial_state(rng, random_start=(ep % 2 == 1))
        scent = make_scent_fields(state.grid_size)
        belief = BeliefEngine(state.grid_size, role)  # unused under uniform belief
        feats, labels = [], []
        outcome = "steps"
        while state.turn < 35:
            legal = _legal(state, role)
            obs, _mask = _observation(state, role, scent, belief, legal, (ep % 6) + 1)
            action = teacher.action(state, legal)
            opp_action = opponent.action(state, rng)
            feats.append(obs)
            labels.append(actions.index(action))
            place_labels += int(action.startswith("PLACE_") or opp_action.startswith("PLACE_"))
            cop_a, thief_a = (action, opp_action) if role == "cop" else (opp_action, action)
            result = apply_joint_action(state, cop_a, thief_a)
            state = result.new_state
            scent = scent.update(state.cop_position, state.thief_position)
            if result.outcome.value != "ongoing":
                outcome = result.outcome.value
                break
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        episodes_out.append(
            {
                "features": torch.stack(feats),
                "labels": torch.tensor(labels, dtype=torch.long),
                "opponent": type(opponent).__name__ + getattr(opponent, "variant", ""),
                "outcome": outcome,
                "role": role,
            }
        )
        print(
            f"[shard {role}-{seed}] ep {ep + 1}/{episodes} {episodes_out[-1]['opponent']}"
            f" -> {outcome} ({time.time() - t0:.0f}s, walls {place_labels})",
            flush=True,
        )
    torch.save({"seed": seed, "role": role, "episodes": episodes_out}, out)
    return {"episodes": len(episodes_out), "walls": place_labels, "outcomes": outcomes}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--episodes", type=int, default=44)
    ap.add_argument("--role", choices=["cop", "thief"], default="cop")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    out_dir = RESULTS / f"shards_{args.role}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else out_dir / f"shard_{args.seed:02d}.pt"
    stats = collect(args.seed, args.episodes, out, role=args.role)
    print(f"[shard {args.role}-{args.seed}] DONE {stats}", flush=True)


if __name__ == "__main__":
    main()
