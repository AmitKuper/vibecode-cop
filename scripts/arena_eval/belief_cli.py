"""CLI for the book-physics belief arena (scripts/arena_belief_eval.py)."""

from __future__ import annotations

import argparse

from arena_eval.belief_impl import _load_thief
from arena_eval.belief_play import play


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thief", required=True)
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--particles", type=int, default=6)
    ap.add_argument("--seed", type=int, default=20260811)
    ap.add_argument("--jitter", action="store_true")
    args = ap.parse_args()
    thief = _load_thief(args.thief)
    captures, steps, walls = 0, [], []
    for g in range(args.games):
        outcome, step, placed = play(thief, args.seed + g, args.depth, args.particles, args.jitter)
        captures += outcome == "capture"
        steps.append(step)
        walls.append(placed)
    print(
        f"belief-cop vs {args.thief}: games={args.games} captures={captures} "
        f"({captures / args.games:.3f}) mean_end={sum(steps) / len(steps):.1f} "
        f"mean_walls={sum(walls) / len(walls):.1f}"
    )
