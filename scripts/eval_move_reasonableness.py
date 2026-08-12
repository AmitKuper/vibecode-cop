#!/usr/bin/env python3
"""Behavioural audit: are the deployed policies' individual moves *reasonable*?

Win rate says whether a policy beats a given opponent; it does not say whether the moves
make sense. This script scores per-move signals that a win rate hides:

  scent_follow_rate  -- of the steps where the observed opponent-scent field is non-flat,
                        how often did the move reduce distance to the scent's argmax cell?
                        A blind or confused policy scores ~ chance (1/len(legal)).
  approach_rate      -- fraction of cop steps that reduced true Chebyshev distance
                        (ground truth, for diagnosis only -- never fed to the policy).
  oscillation_pct    -- revisits the cell occupied two steps earlier (A-B-A shuffle).
  frozen_tail_pct    -- share of the last 8 steps spent on a single cell.
  action_entropy     -- Shannon entropy over the action histogram, in bits.

Usage: python scripts/eval_move_reasonableness.py --games 30

This file is the entry point and public FACADE. The implementation lives in the
``eval_reasonableness`` package (one concern per module, ≤150 lines each):

    metrics    _DELTA, _scent_argmax, _cheb, _plateau_size, summarise
    audit      audit_game -- the per-game audit loop
    cli        main
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from eval_reasonableness.audit import audit_game
from eval_reasonableness.cli import main
from eval_reasonableness.metrics import (
    _DELTA,
    _cheb,
    _plateau_size,
    _scent_argmax,
    summarise,
)

__all__ = [
    "REPO_ROOT",
    "_DELTA",
    "_cheb",
    "_plateau_size",
    "_scent_argmax",
    "audit_game",
    "main",
    "summarise",
]

if __name__ == "__main__":
    main()
