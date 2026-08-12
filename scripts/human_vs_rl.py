#!/usr/bin/env python3
"""Human vs RL-champion interactive CLI — informal local test tool.

NOT part of the graded assignment deliverable. Standalone, additive script
that only *reads* the production cop_worker package and the tracked model
champion artifact — it does not modify or depend on any other script.
Safe to delete at any time without affecting the rest of the repo.

Loads the manifest-selected ("champion") RecurrentA2C-GRU policy and lets a
human play the opposite role against it via direct keyboard input. Pure RL
inference only — no LLM calls anywhere in this path.

Run from the vibecode-cop directory (this repo only tracks the cop champion,
so the agent here always plays cop; you play thief):

    uv run python scripts/human_vs_rl.py --human-role thief
    uv run python scripts/human_vs_rl.py --human-role thief --reveal

Flags:
  --human-role thief         Which role you play (fixed: this repo's champion is cop)
  --reveal                   Show both positions after each turn (full board)
  --numeric                  Show scent/belief as floats instead of ░▒▓ chars
  --gamelets N                Number of gamelets to play (default 3)
"""

# Facade: implementation lives in scripts/human_play/ (rl_* modules); this
# file re-exports every original module-level name and keeps the CLI entry.

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

from human_play.keys import (  # noqa: F401
    _CONTROLS_COP_BARRIER,
    _KEY_TO_MOVE,
    _KEY_TO_PLACE,
    _SCENT_RAMP,
    _clear,
    _get_key,
    _scent_ch,
)
from human_play.rl_board import _legal_moves_for, _render_board  # noqa: F401
from human_play.rl_gamelet import _run_gamelet  # noqa: F401
from human_play.rl_moves import (  # noqa: F401
    _CONTROLS_COP,
    _CONTROLS_THIEF,
    _get_agent_move,
    _get_human_move,
)
from human_play.rl_series import _run_series  # noqa: F401

from cop_worker.belief_engine import BeliefEngine  # noqa: F401
from cop_worker.domain.config_validator import GameConfig  # noqa: F401
from cop_worker.domain.transition import apply_joint_action  # noqa: F401
from cop_worker.domain.types import DomainState  # noqa: F401
from cop_worker.observation import LocalObservation  # noqa: F401
from cop_worker.rl.action_space import (  # noqa: F401
    COP_ACTIONS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)
from cop_worker.rl.recurrent_policy import load_recurrent_policy  # noqa: F401
from cop_worker.rules_outcomes import GameOutcome  # noqa: F401

# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Play against this repo's RL champion policy (no LLM). Informal test tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--human-role",
        choices=["cop", "thief"],
        required=True,
        help="Which role you play (the champion tracked in this repo plays the other)",
    )
    parser.add_argument(
        "--reveal",
        action="store_true",
        help="Show both positions after each turn (removes hidden-info aspect)",
    )
    parser.add_argument(
        "--numeric",
        action="store_true",
        help="Show scent as numeric floats instead of ░▒▓ characters",
    )
    parser.add_argument(
        "--gamelets",
        type=int,
        default=3,
        metavar="N",
        help="Number of gamelets to play (default: 3)",
    )
    args = parser.parse_args()

    if args.gamelets < 1 or args.gamelets > 10:
        parser.error("--gamelets must be between 1 and 10")

    _run_series(args.human_role, args.gamelets, args.reveal, args.numeric)


if __name__ == "__main__":
    main()
