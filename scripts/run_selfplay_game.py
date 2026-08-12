"""Self-play game runner — cop vs thief in a single sub-game.

Usage:
    uv run python scripts/run_selfplay_game.py --board-size 7 --max-steps 20

This file is the entry point and public FACADE; the implementation lives in the
``selfplay_game`` package (<=150 lines per module).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add cop repo root and thief repo root to sys.path for in-process imports
_COP_REPO = Path(__file__).resolve().parents[1]
if str(_COP_REPO) not in sys.path:
    sys.path.insert(0, str(_COP_REPO))

THIEF_REPO = _COP_REPO.parent / "vibecode-thief"
if THIEF_REPO.is_dir() and str(THIEF_REPO) not in sys.path:
    sys.path.insert(0, str(THIEF_REPO))

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from selfplay_game.game import TERMS_TEMPLATE, cop_ms, run_one_game  # noqa: F401

logger = logging.getLogger(__name__)

__all__ = ["TERMS_TEMPLATE", "cop_ms", "main", "run_one_game"]


def main() -> int:
    """Run self-play game."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-steps", type=int, default=5)
    parser.add_argument("--game-uid", default="selfplay_001")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        result = run_one_game(args.game_uid, sub_game_number=1, max_steps=args.max_steps)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        logger.error("Self-play failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
