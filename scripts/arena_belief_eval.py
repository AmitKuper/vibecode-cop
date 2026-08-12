"""Head-to-head arena under BOOK physics: belief-pursuit cop vs any thief.

The book-frame counterpart of arena_search_eval.py: same reference-v3 round
(thief first, cop replies), rule-46/47 captures, but the wire law is the
CLAMPED BOOK model and the cop plays cop_worker.rl.belief_pursuit over a live
BeliefEngine posterior instead of an exact fix. This is the promotion harness
for the ``hybrid_search_belief`` policy — DO NOT run during a game window.

Usage:
  python scripts/arena_belief_eval.py --games 20 \
      --thief <ckpt.pt>|ddqn:<ckpt.pt> [--depth 3] [--particles 6] [--jitter]

This file is the entry point and public FACADE. The implementation lives in the
``arena_eval`` package: belief_impl (_RecurrentThief, _load_thief, _book_field),
belief_play (N, play), belief_cli (main).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from arena_eval.belief_cli import main
from arena_eval.belief_impl import _book_field, _load_thief, _RecurrentThief
from arena_eval.belief_play import N, play

__all__ = [
    "N",
    "REPO_ROOT",
    "_RecurrentThief",
    "_book_field",
    "_load_thief",
    "main",
    "play",
]

if __name__ == "__main__":
    main()
