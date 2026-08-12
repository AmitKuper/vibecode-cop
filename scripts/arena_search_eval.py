"""Head-to-head arena under chebyshev physics: search policy vs trained checkpoints.

Simulates the reference-v3 round (thief moves first, cop replies; each side observes the
other's transmitted post-decay frame) with rule-46/47 captures, and pits any pairing of
{search, checkpoint .pt} per role. This is the promotion evidence for `hybrid_search`.

Usage:
  python scripts/arena_search_eval.py --games 20 \
      --cop search|<ckpt.pt> --thief search|<ckpt.pt> [--depth 3] [--jitter]

This file is the entry point and public FACADE (``arena_archetypes.py`` and
``render_match_visuals.py`` import through it). The implementation lives in the
``arena_eval`` package: search_impl (N, CheckpointPolicy, make_policy, _obs),
search_play (play), search_cli (main).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from arena_eval.search_cli import main
from arena_eval.search_impl import CheckpointPolicy, N, _obs, make_policy
from arena_eval.search_play import play

__all__ = [
    "N",
    "REPO_ROOT",
    "CheckpointPolicy",
    "_obs",
    "main",
    "make_policy",
    "play",
]

if __name__ == "__main__":
    main()
