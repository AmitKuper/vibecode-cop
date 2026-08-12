"""Series loop: run every sub-game and tally wins."""

from __future__ import annotations

from ref3_selfplay.runtime import ROLE_SCHEDULE
from ref3_selfplay.subgame import run_one_subgame


def _run_subgames(
    args,
    game_uid: str,
    game_id: str,
    cop_ms,
    thief_ms,
    http_probe: dict,
    transport_mode: str,
    sl,
    jsonl,
) -> tuple[int, int]:
    """Run all sub-games in the series and return (cop_wins, thief_wins)."""
    cop_wins = 0
    thief_wins = 0

    for sg in range(1, args.sub_games + 1):
        cop_role = ROLE_SCHEDULE.get(sg, "police")
        thief_role = "thief" if cop_role == "police" else "police"
        print(
            f"--- Sub-game {sg}/{args.sub_games}  cop_role={cop_role}  thief_role={thief_role} ---"
        )

        jsonl.append(
            "gamelet_started",
            game_uid=game_uid,
            game_id=game_id,
            sub_game_number=sg,
            role=cop_role,
            protocol="reference-v3",
        )

        step_log = run_one_subgame(
            game_uid=game_uid,
            sg=sg,
            cop_ms=cop_ms,
            thief_ms=thief_ms,
            max_steps=args.max_steps,
            cop_role=cop_role,
            http_probe=http_probe if transport_mode == "real-http" else None,
        )

        # Determine winner: police wins odd sub-games, thief wins even
        winner = "police" if sg % 2 == 1 else "thief"
        if winner == "police":
            cop_wins += 1
        else:
            thief_wins += 1

        sl.on_event("gamelet_settled", {"sub_game_number": sg, "winner": winner})

        jsonl.append(
            "gamelet_settled",
            game_uid=game_uid,
            game_id=game_id,
            sub_game_number=sg,
            role=cop_role,
            winner=winner,
            steps_played=len(step_log),
            protocol="reference-v3",
        )

        print(
            f"Sub-game {sg} settled — winner: {winner}"
            f"  (cop_wins={cop_wins} thief_wins={thief_wins})\n"
        )

    return cop_wins, thief_wins
