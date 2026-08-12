"""CLI for the chebyshev arena (scripts/arena_search_eval.py)."""

from __future__ import annotations

import argparse

from arena_eval.search_impl import make_policy
from arena_eval.search_play import play


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cop", required=True)
    p.add_argument("--thief", required=True)
    p.add_argument("--games", type=int, default=20)
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--seed", type=int, default=20260810)
    p.add_argument(
        "--jitter", action="store_true", help="randomise the thief's first move so games differ"
    )
    args = p.parse_args()
    cop_policy = make_policy(args.cop, "cop", args.depth)
    thief_policy = make_policy(args.thief, "thief", args.depth)
    captures, steps = 0, []
    for g in range(args.games):
        outcome, step = play(cop_policy, thief_policy, args.seed + g, args.jitter)
        captures += outcome == "capture"
        steps.append(step)
    print(
        f"cop={args.cop} thief={args.thief} games={args.games} "
        f"captures={captures} ({captures / args.games:.3f}) "
        f"mean_end_step={sum(steps) / len(steps):.1f}"
    )
