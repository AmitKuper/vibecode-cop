"""Legacy-harness comparison: student vs manifest champion, identical protocol.

Answers "is the new learned model as good as the previous one?" with data:
both nets are driven through the SAME episode loop against the classic
training opponent families, same seeds, same observation pipeline.

Usage: python scripts/barrier_distill/legacy_eval.py --role thief \
           --student thief_gru_v1.pt [--episodes 27]
"""

from __future__ import annotations

import argparse
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


def _families():
    from cop_worker.rl.train_recurrent.schedules import FAMILIES

    return [f for f in FAMILIES if f != "historical_checkpoint"]


def _episode(net, role: str, family: str, seed: int) -> bool:
    """One episode net-vs-family; returns True when ``role`` wins."""
    import torch

    import cop_worker.rl.train_recurrent as _pkg
    from cop_worker.belief_engine import BeliefEngine
    from cop_worker.domain.transition import apply_joint_action
    from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
    from cop_worker.rl.train_recurrent.episode_steps import _advance_beliefs
    from cop_worker.rl.train_recurrent.observation import _observation
    from cop_worker.rl.train_recurrent.sim import _initial_state, _legal
    from cop_worker.scent import make_scent_fields

    rng = random.Random(seed)
    actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
    opp_role = "thief" if role == "cop" else "cop"
    state = _initial_state(rng, random_start=(seed % 2 == 1))
    scent = make_scent_fields(state.grid_size)
    belief = BeliefEngine(state.grid_size, role)
    opp_belief = BeliefEngine(state.grid_size, opp_role)
    hidden = None
    while state.turn < 35:
        legal = _legal(state, role)
        obs, mask = _observation(state, role, scent, belief, legal, (seed % 6) + 1)
        with torch.no_grad():
            logits, _v, hidden = net(obs.unsqueeze(0), hidden)
        act = actions[int(logits[0].masked_fill(~mask, -1e9).argmax())]
        opp_scent = (
            scent.thief_observation_scent()
            if opp_role == "thief"
            else scent.cop_observation_scent()
        )
        opp = _pkg._opponent_action(
            state, opp_role, family, rng,
            historical_policy=None, opponent_scent=opp_scent, opponent_belief=opp_belief,
        )  # fmt: skip
        cop_a, thief_a = (act, opp) if role == "cop" else (opp, act)
        result = apply_joint_action(state, cop_a, thief_a)
        state = result.new_state
        scent, belief, opp_belief = _advance_beliefs(
            scent, state, role, opp_role, belief, opp_belief
        )
        if result.outcome.value != "ongoing":
            return ("cop" in result.outcome.value) == (role == "cop")
    return role == "thief"


def _load_champion(role: str):
    import torch

    from cop_worker.rl.model_schema import load_manifest
    from cop_worker.rl.recurrent_policy import RecurrentActorCritic

    repo = _REPO if role == "cop" else _REPO.parent / "vibecode-thief"
    entry = load_manifest(str(repo / "models" / "MANIFEST.json"))[role]
    blob = torch.load(repo / "models" / entry.artifact, map_location="cpu", weights_only=False)
    sd = blob.get("state_dict", blob)
    n_actions = sd["policy_head.bias"].shape[0]
    net = RecurrentActorCritic(sd["encoder.0.weight"].shape[1], n_actions)
    net.load_state_dict(sd)
    return net.eval(), entry.artifact


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=["cop", "thief"], required=True)
    ap.add_argument("--student", required=True)
    ap.add_argument("--episodes", type=int, default=27)
    args = ap.parse_args()
    from barrier_distill.models import load_student

    student, _meta = load_student(str(RESULTS / args.student))
    champion, champ_name = _load_champion(args.role)
    print(f"{'family':<26} {'champion (' + champ_name[:18] + ')':>28} {'student':>10}")
    tot = {"champion": 0, "student": 0}
    n = 0
    for family in _families():
        wins = {"champion": 0, "student": 0}
        for i in range(args.episodes):
            for name, net in (("champion", champion), ("student", student)):
                wins[name] += int(_episode(net, args.role, family, seed=1000 + i))
        n += args.episodes
        for k in tot:
            tot[k] += wins[k]
        print(
            f"{family:<26} {wins['champion']:>14}/{args.episodes} {wins['student']:>9}/{args.episodes}"
        )
    print(
        f"{'TOTAL':<26} {tot['champion']:>14}/{n} ({tot['champion'] / n:.3f}) "
        f"{tot['student']:>6}/{n} ({tot['student'] / n:.3f})"
    )


if __name__ == "__main__":
    main()
