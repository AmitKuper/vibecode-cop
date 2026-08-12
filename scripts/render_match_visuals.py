"""Render real-engine match visuals: trajectory, chebyshev scent, search territory.

Plays a real game with the production physics (rule-46/47, ChebyshevTrail) between
the shipped hybrid-search policies, then renders three PNGs under assets/:
  1. match_trajectory.png     — both paths + barriers on the 7x7 board
  2. scent_heatmap.png        — the thief's transmitted chebyshev field mid-game
  3. search_territory.png     — the cop search engine's territory evaluation

Usage: python scripts/render_match_visuals.py [--seed 20260811] [--out assets]

This file is the entry point and public FACADE; the implementation lives in the
``match_visuals`` package (game replay + chart rendering, <=150 lines per module).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from match_visuals.charts import render
from match_visuals.play import N, _obs, make_policy, play_and_record

__all__ = ["N", "_obs", "main", "make_policy", "play_and_record", "render"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "assets" / "screenshots")
    args = parser.parse_args()
    history = play_and_record(args.seed)
    for path in render(history, args.out):
        print(path)


if __name__ == "__main__":
    main()
