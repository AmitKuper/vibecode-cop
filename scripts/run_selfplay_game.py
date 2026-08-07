"""Self-play game runner — cop vs thief in a single sub-game.

Usage:
    uv run python scripts/run_selfplay_game.py --board-size 7 --max-steps 20
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

from cop_worker import mcp_server as cop_ms

logger = logging.getLogger(__name__)

TERMS_TEMPLATE = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "max_steps": 35,
    "survival_threshold": 35,
    "barriers_max": 14,
    "num_games": 6,
}


def run_one_game(game_uid: str, sub_game_number: int, max_steps: int) -> dict:
    """Run a single sub-game between cop (police) and thief in-process.

    Args:
        game_uid: Unique identifier for the game series.
        sub_game_number: Sub-game index (1-based).
        max_steps: Maximum number of steps to simulate.

    Returns:
        Dict with game result summary including steps_played and step_results.
    """
    try:
        from thief_worker import mcp_server as thief_ms
    except ImportError:
        logger.error("thief_worker not importable — add vibecode-thief to sys.path")
        raise

    cop_ms.clear_all_gamelets()
    thief_ms.clear_all_gamelets()

    # Always use valid terms (max_steps >= 35 is required by parameter_registry).
    # The max_steps argument controls how many steps we actually simulate, not the
    # declared game length — the game would continue if we kept sending events.
    terms = dict(TERMS_TEMPLATE)

    # Start both gamelets
    cop_ms.start_gamelet(
        game_uid=game_uid,
        sub_game_number=sub_game_number,
        terms=terms,
        opponent_group="thief_local",
        role="police",
    )
    thief_ms.start_gamelet(
        game_uid=game_uid,
        sub_game_number=sub_game_number,
        terms=terms,
        opponent_group="cop_local",
        role="thief",
    )

    # Transition both gamelets from LOCKED to PLAYING
    cop_ms.start_playing(game_uid, sub_game_number)
    thief_ms.start_playing(game_uid, sub_game_number)

    cop_status = cop_ms.get_status(game_uid, sub_game_number)
    thief_status = thief_ms.get_status(game_uid, sub_game_number)
    logger.info("Cop state: %s, Thief state: %s", cop_status["state"], thief_status["state"])

    step_results = []
    for step in range(1, max_steps + 1):
        # Cop receives a dummy opponent commit and responds with its own commit
        cop_event = cop_ms.deliver_event(
            game_uid=game_uid,
            sub_game_number=sub_game_number,
            event_type="opponent_turn",
            payload={
                "step": step,
                "kind": "commit",
                "commitment_hash": "a" * 64,
                "nonce": None,
                "action": None,
            },
        )
        cop_commit = cop_event.get("response_payload", {})
        cop_hash = cop_commit.get("commitment_hash", "a" * 64)
        logger.debug("Step %d: cop commit=%s", step, cop_hash[:8])

        # Thief receives cop's commit, responds with its own commit
        thief_event = thief_ms.deliver_event(
            game_uid=game_uid,
            sub_game_number=sub_game_number,
            event_type="opponent_turn",
            payload={
                "step": step,
                "kind": "commit",
                "commitment_hash": cop_hash,
                "nonce": None,
                "action": None,
            },
        )
        thief_commit = thief_event.get("response_payload", {})
        thief_hash = thief_commit.get("commitment_hash", "a" * 64)
        logger.debug("Step %d: thief commit=%s", step, thief_hash[:8])

        step_results.append(
            {
                "step": step,
                "cop_commit": cop_hash[:8],
                "thief_commit": thief_hash[:8],
            }
        )

    logger.info("Game complete. Steps: %d", len(step_results))
    return {
        "game_uid": game_uid,
        "sub_game_number": sub_game_number,
        "steps_played": len(step_results),
        "status": "COMPLETE",
        "step_results": step_results[:3],  # first 3 steps only
    }


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
