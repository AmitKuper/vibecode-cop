"""Per-gamelet config and log artifacts (schemas mirror anrbj666's shipped files)."""

from __future__ import annotations

from league_artifacts.core import OUR_REPOS, config_sha256, load_constitution


def build_config(game_id: str, game_uid: str, sub_game: int, setting: str, opponent: str) -> dict:
    """Config artifact sourced entirely from the shared constitution (config/game.json).

    Every section (including agreed_between and the whole-file config_sha256) comes from the
    adopted file so the artifact can never drift from the hashed bytes. `setting` is retained
    for signature compatibility but ignored — map_area lives in the constitution.
    """
    g = load_constitution()
    return {
        "_schema": "p2p-police-artifacts",
        "agreed_between": g["agreed_between"],
        "board_and_agents": g["board_and_agents"],
        "config_name": f"config_{game_id}_g{sub_game:02d}.json",
        "config_sha256": config_sha256(),
        "game_id": game_id,
        "game_uid": game_uid,
        "links": OUR_REPOS,
        "movement_and_barriers": g["movement_and_barriers"],
        "network_and_league": g["network_and_league"],
        "pheromones": g["pheromones"],
        "rate_limiter_gatekeeper": g["rate_limiter_gatekeeper"],
        "report_type": "config",
        "schema_version": g["schema_version"],
        "scoring": g["scoring"],
        "sub_game_number": sub_game,
        "world": g["world"],
    }


def build_log(
    game_id: str,
    game_uid: str,
    sub_game: int,
    role: str,
    opponent: str,
    our_records: list,
    opp_records: list,
    summary: dict,
) -> dict:
    """Log artifact. records[0] is the REAL sealed step_zero that rode the wire in
    submit_audit (fresh nonce, commit = reference_commit(payload, nonce)) — no longer
    synthesized here; it comes straight from out_session.local_records.
    """
    return {
        "_schema": "p2p-police-artifacts",
        "game_id": game_id,
        "game_uid": game_uid,
        "links": {
            "config": f"config_{game_id}_g{sub_game:02d}.json",
            "declaration": f"declaration_{game_id}.json",
            "log": f"log_{game_id}_g{sub_game:02d}.json",
            "result": f"result_{game_id}.json",
        },
        "opponent_records": opp_records,
        "records": our_records,
        "report_type": "log",
        "schema_version": "1.3",
        "sub_game_number": sub_game,
        "summary": summary,
        "wire_shape": "reference",
    }
