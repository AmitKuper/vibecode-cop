"""Run a full 6-sub-game league series in-process.

Uses LeagueManager components (SeriesLifecycle, SeriesJSONL) + both workers.
Movement: random heuristic (N/S/E/W).

Usage:
    uv run python scripts/run_league_game.py --max-steps 35 --log-dir /tmp/league

This file is the entry point and public FACADE; the implementation lives in the
``league_game`` package (series driver + turn loop, <=150 lines per module).
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import secrets
import sys
from pathlib import Path

# Add both repos to sys.path so cop_worker, thief_worker, league_manager are importable
COP_REPO = Path(__file__).resolve().parents[1]  # vibecode-cop/
THIEF_REPO = Path(__file__).resolve().parents[2] / "vibecode-thief"
for _p in [str(COP_REPO), str(THIEF_REPO), str(Path(__file__).resolve().parent)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from league_game.series import ROLE_SCHEDULE, TERMS_BASE, run_series

logger = logging.getLogger(__name__)

__all__ = ["ROLE_SCHEDULE", "TERMS_BASE", "main", "run_series"]


def main() -> None:
    """CLI entry point for run_league_game."""
    parser = argparse.ArgumentParser(description="Run a 6-sub-game league series in-process.")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=35,
        help="Steps per sub-game (default 35; clamped to >= 35 for parameter registry)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs/league"),
        help="Directory for JSONL event log",
    )
    parser.add_argument(
        "--game-uid",
        type=str,
        default=None,
        help="Game UID (auto-generated if not provided)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
    )

    game_uid = args.game_uid or hashlib.sha256(secrets.token_bytes(16)).hexdigest()[:32]
    print(f"Starting series  game_uid={game_uid}  max_steps={args.max_steps}")

    run_series(game_uid=game_uid, max_steps=args.max_steps, log_dir=args.log_dir)


if __name__ == "__main__":
    main()
