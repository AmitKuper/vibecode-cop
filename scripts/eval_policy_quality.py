#!/usr/bin/env python3
"""Quality audit of the DEPLOYED cop/thief policies, exactly as production feeds them.

Unlike ``research_evaluation.py`` (which hands the net a live ``BeliefEngine``), this
harness drives the policies through ``load_counted_policy`` and builds the observation
the way ``scripts/live_match_ref3.py::RLMover.decide`` does -- including whatever belief
production actually supplies. A ``--belief`` switch flips between the production value
and the training-time live belief so the train/serve gap is measurable, not asserted.

Usage:
    python scripts/eval_policy_quality.py --games 40
    python scripts/eval_policy_quality.py --trace          # one annotated game per role

This file is the entry point and public FACADE: tests and sibling scripts import
through it. The implementation lives in the ``eval_quality`` package
(one concern per module, ≤150 lines each):

    scent_laws    ClampedScent (wire law) + ChebyshevScent (subtractive_chebyshev_v1)
    deployed      DeployedPolicy + manifests/opponent-family constants
    game          play (canonical-physics loop) + move_stats
    suites        suite -- the per-family ablation harness
    cli           main -- trace, 2x2 ablation, head-to-head
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from eval_quality.cli import main
from eval_quality.deployed import (
    COP_MANIFEST,
    OPPONENT_FAMILIES,
    THIEF_MANIFEST,
    DeployedPolicy,
)
from eval_quality.game import move_stats, play
from eval_quality.scent_laws import ChebyshevScent, ClampedScent
from eval_quality.suites import suite

__all__ = [
    "COP_MANIFEST",
    "OPPONENT_FAMILIES",
    "REPO_ROOT",
    "THIEF_MANIFEST",
    "ChebyshevScent",
    "ClampedScent",
    "DeployedPolicy",
    "main",
    "move_stats",
    "play",
    "suite",
]

if __name__ == "__main__":
    main()
