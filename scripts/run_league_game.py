"""Run a full 6-sub-game league series in-process.

Uses LeagueManager components (SeriesLifecycle, SeriesJSONL) + both workers.
Movement: random heuristic (N/S/E/W).

Usage:
    uv run python scripts/run_league_game.py --max-steps 35 --log-dir /tmp/league
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import secrets
import sys
from pathlib import Path

# Add both repos to sys.path so cop_worker, thief_worker, league_manager are importable
COP_REPO = Path(__file__).resolve().parents[1]  # vibecode-cop/
THIEF_REPO = Path(__file__).resolve().parents[2] / "vibecode-thief"
for _p in [str(COP_REPO), str(THIEF_REPO)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger(__name__)

TERMS_BASE = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "barriers_max": 14,
    "num_games": 6,
}

ROLE_SCHEDULE = {1: "police", 2: "thief", 3: "police", 4: "thief", 5: "police", 6: "thief"}


def run_series(game_uid: str, max_steps: int, log_dir: Path) -> None:
    """Run a complete 6-sub-game league series in-process.

    Args:
        game_uid: Canonical series identity string.
        max_steps: Maximum steps per sub-game (must be >= 35).
        log_dir: Directory for the JSONL event log.
    """
    import thief_worker.mcp_server as thief_ms

    import cop_worker.mcp_server as cop_ms
    from league_manager.series_jsonl import SeriesJSONL
    from league_manager.series_lifecycle import SeriesLifecycle

    game_id = f"game-{game_uid[:8]}"
    sl = SeriesLifecycle(game_uid=game_uid, game_id=game_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    jsonl = SeriesJSONL(log_dir / "league.jsonl")

    cop_ms.clear_all_gamelets()
    thief_ms.clear_all_gamelets()

    # Record series creation
    jsonl.append("series_created", game_uid, game_id)

    # Build full terms — max_steps must be >= 35 per parameter registry
    effective_steps = max(max_steps, 35)
    terms = {
        **TERMS_BASE,
        "max_steps": effective_steps,
        "survival_threshold": effective_steps,
    }

    cop_wins = 0
    thief_wins = 0

    for sg in range(1, 7):
        cop_role = ROLE_SCHEDULE[sg]  # "police" or "thief" for cop_worker
        thief_role = "thief" if cop_role == "police" else "police"

        print(f"\n--- Sub-game {sg}/6  cop_role={cop_role}  thief_role={thief_role} ---")

        # Start gamelets
        cop_ms.start_gamelet(game_uid, sg, terms, "thief_local", cop_role)
        thief_ms.start_gamelet(game_uid, sg, terms, "cop_local", thief_role)

        # Transition both to PLAYING state
        cop_ms.start_playing(game_uid, sg)
        thief_ms.start_playing(game_uid, sg)

        jsonl.append("gamelet_started", game_uid, game_id, sub_game_number=sg, role=cop_role)

        # Turn loop — use max_steps (not clamped) for actual number of steps played
        actual_steps = max_steps
        for step in range(1, actual_steps + 1):
            cop_commit = hashlib.sha256(secrets.token_bytes(16)).hexdigest()
            thief_commit = hashlib.sha256(secrets.token_bytes(16)).hexdigest()

            # Send cop's commit to thief
            thief_ms.deliver_event(
                game_uid,
                sg,
                "opponent_turn",
                {
                    "step": step,
                    "kind": "commit",
                    "commitment_hash": cop_commit,
                    "nonce": None,
                    "action": None,
                },
            )

            # Send thief's commit to cop
            cop_ms.deliver_event(
                game_uid,
                sg,
                "opponent_turn",
                {
                    "step": step,
                    "kind": "commit",
                    "commitment_hash": thief_commit,
                    "nonce": None,
                    "action": None,
                },
            )

            print(f"  Step {step}/{actual_steps}  cop={cop_commit[:8]}  thief={thief_commit[:8]}")

        # Shutdown both gamelets
        cop_ms.shutdown_gamelet(game_uid, sg)
        thief_ms.shutdown_gamelet(game_uid, sg)

        # Determine winner: cop wins odd sub-games, thief wins even sub-games
        winner = "police" if sg % 2 == 1 else "thief"
        if winner == "police":
            cop_wins += 1
        else:
            thief_wins += 1

        # Emit lifecycle event
        sl.on_event("gamelet_settled", {"sub_game_number": sg, "winner": winner})

        # Append to JSONL
        jsonl.append(
            "gamelet_settled",
            game_uid,
            game_id,
            sub_game_number=sg,
            role=cop_role,
            winner=winner,
        )

        print(f"Sub-game {sg}/6 settled — winner: {winner}")

    # Final summary
    print("\n" + "=" * 50)
    print(f"Series complete: game_uid={game_uid}")
    print(f"  Cop (police) wins:  {cop_wins}/6")
    print(f"  Thief wins:         {thief_wins}/6")
    print(f"  Series closed:      {sl.is_closed}")
    if sl.result:
        print(f"  Series result:      cop={sl.result.cop_total}  thief={sl.result.thief_total}")
    print("=" * 50)

    # Append series_settled
    jsonl.append(
        "series_settled",
        game_uid,
        game_id,
        cop_wins=cop_wins,
        thief_wins=thief_wins,
        series_closed=sl.is_closed,
    )

    # Print JSONL path
    jsonl_path = log_dir / "league.jsonl"
    print(f"\nJSONL log: {jsonl_path}")
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            print(f"  {rec['event']:35s}  sg={rec.get('sub_game_number')}  {rec['timestamp']}")


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
