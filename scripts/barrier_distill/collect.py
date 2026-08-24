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


def collect(
    seed: int,
    episodes: int,
    out: Path,
    role: str = "cop",
    driver_ckpt: str = "",
    pool_kind: str = "full",
) -> dict:
    """Roll episodes for ``role`` vs its opponent pool.

    Teacher labels every state. With ``driver_ckpt`` (DAgger), the STUDENT
    drives the trajectory — the corpus then covers the states the student
    actually reaches, labeled by the per-opponent expert.
    """
    import torch

    from barrier_distill.pool_select import pick_pool
    from barrier_distill.teacher import ChampionTeacher, SearchHookTeacher, ThiefStackTeacher
    from cop_worker.belief_engine import BeliefEngine
    from cop_worker.domain.transition import apply_joint_action
    from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
    from cop_worker.rl.train_recurrent.observation import _observation
    from cop_worker.rl.train_recurrent.sim import _initial_state, _legal
    from cop_worker.scent import make_scent_fields

    rng = random.Random(seed)
    actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
    episodes_out, place_labels, outcomes = [], 0, {}
    # Mixture of experts: the manifest champion teaches against the classic
    # families it was trained on (it beats the search stack there); the search
    # stack teaches everything else (sweeps, evaders — where IT is stronger).
    stack_teacher = SearchHookTeacher() if role == "cop" else ThiefStackTeacher()
    champion_teacher = ChampionTeacher(role)
    driver = None
    if driver_ckpt:
        from barrier_distill.models import load_student

        driver, _meta = load_student(str(RESULTS / driver_ckpt))
    t0 = time.time()
    for ep in range(episodes):
        pool = pick_pool(role, pool_kind, rng)
        opponent = pool[ep % len(pool)]
        is_family = type(opponent).__name__ in ("FamilyCop", "FamilyThief")
        teacher = champion_teacher if is_family else stack_teacher
        opponent.reset()
        teacher.reset()
        state = _initial_state(rng, random_start=(ep % 2 == 1))
        scent = make_scent_fields(state.grid_size)
        belief = BeliefEngine(state.grid_size, role)  # unused under uniform belief
        feats, labels = [], []
        hidden = None
        outcome = "steps"
        while state.turn < 35:
            legal = _legal(state, role)
            obs, mask = _observation(state, role, scent, belief, legal, (ep % 6) + 1)
            action = teacher.action(state, legal, obs=obs)  # the LABEL, always
            played = action
            if driver is not None:  # DAgger: the student drives, the expert labels
                with torch.no_grad():
                    logits, _v, hidden = driver(obs.unsqueeze(0), hidden)
                played = actions[int(logits[0].masked_fill(~mask, -1e9).argmax())]
            opp_action = opponent.action(state, rng, scent)
            feats.append(obs)
            labels.append(actions.index(action))
            place_labels += int(action.startswith("PLACE_") or opp_action.startswith("PLACE_"))
            cop_a, thief_a = (played, opp_action) if role == "cop" else (opp_action, played)
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
    ap.add_argument("--driver", default="", help="student checkpoint that DRIVES (DAgger)")
    ap.add_argument("--pool", default="full", choices=["full", "sweep", "weak"])
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    out_dir = RESULTS / (f"shards_{args.role}_dagger" if args.driver else f"shards_{args.role}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else out_dir / f"shard_{args.seed:02d}.pt"
    stats = collect(
        args.seed, args.episodes, out,
        role=args.role, driver_ckpt=args.driver, pool_kind=args.pool,
    )  # fmt: skip
    print(f"[shard {args.role}-{args.seed}] DONE {stats}", flush=True)


if __name__ == "__main__":
    main()
