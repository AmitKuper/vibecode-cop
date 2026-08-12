#!/usr/bin/env python3
"""Human vs Agent interactive CLI — play against the production cop or thief policy.

Run from the vibecode-cop or vibecode-thief directory:

    uv run python scripts/human_vs_agent.py --human-role thief
    uv run python scripts/human_vs_agent.py --human-role cop
    uv run python scripts/human_vs_agent.py --human-role thief --reveal

Flags:
  --human-role {cop,thief}   Which role you play (agent plays the other)
  --reveal                   Show both positions after each turn (full board)
  --numeric                  Show scent/belief as floats instead of ░▒▓ chars
  --gamelets N               Number of gamelets to play (default 3)
"""

# Facade: implementation lives in scripts/human_play/ (agent_* modules); this
# file re-exports every original module-level name and keeps the CLI entry.

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

from agent.belief_engine import BeliefEngine  # noqa: E402, F401
from agent.domain.config_validator import GameConfig  # noqa: E402, F401
from agent.domain.transition import apply_joint_action  # noqa: E402, F401
from agent.domain.types import DomainState  # noqa: E402, F401
from agent.observation import LocalObservation  # noqa: E402, F401
from agent.rl.action_space import (  # noqa: E402, F401
    COP_ACTIONS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)
from agent.rl.recurrent_policy import load_recurrent_policy  # noqa: E402, F401
from agent.rules_outcomes import GameOutcome  # noqa: E402, F401
from human_play.agent_board import _legal_moves_for, _render_board  # noqa: E402, F401
from human_play.agent_gamelet import _run_gamelet  # noqa: E402, F401
from human_play.agent_moves import (  # noqa: E402, F401
    _CONTROLS_COP,
    _CONTROLS_THIEF,
    _get_agent_move,
    _get_human_move,
)
from human_play.agent_series import _run_series  # noqa: E402, F401
from human_play.keys import (  # noqa: E402, F401
    _CONTROLS_COP_BARRIER,
    _KEY_TO_MOVE,
    _KEY_TO_PLACE,
    _SCENT_RAMP,
    _clear,
    _get_key,
    _scent_ch,
)

# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Play against the production cop or thief AI policy.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--human-role",
        choices=["cop", "thief"],
        required=True,
        help="Which role you play (agent takes the other)",
    )
    parser.add_argument(
        "--reveal",
        action="store_true",
        help="Show both positions after each turn (removes hidden-info aspect)",
    )
    parser.add_argument(
        "--gamelets",
        type=int,
        default=3,
        metavar="N",
        help="Number of gamelets to play (default: 3)",
    )
    parser.add_argument(
        "--numeric",
        action="store_true",
        help="Show scent and belief as raw float values instead of ░▒▓ characters",
    )
    args = parser.parse_args()

    if args.gamelets < 1 or args.gamelets > 10:
        parser.error("--gamelets must be between 1 and 10")

    _run_series(args.human_role, args.gamelets, args.reveal, args.numeric)


if __name__ == "__main__":
    main()
