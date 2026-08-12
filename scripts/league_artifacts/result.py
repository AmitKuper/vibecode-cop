"""The emailed final_game_result and its mutual-agreement hash."""

from __future__ import annotations

import hashlib
import json

from league_artifacts.core import OUR_REPOS


def mutual_agreement_sha(game_id: str, rows: list, final_result: dict) -> str:
    """anrbj666/imreeyal ADR-0012 symmetric-outcome scope — the two-team standard.

    Preimage keyed on game_id; aggregate {series_tie, sub_games_won, ties, total_score,
    winner_group}; rows {sub_game_number, roles, result, winner_group, score}. Serialized
    in the SETTLEMENT form: sort_keys=True, ensure_ascii=False, DEFAULT (spaced) separators
    (NOT the compact commit canonical).
    """
    preimage = {
        "game_id": game_id,
        "aggregate": {
            "series_tie": final_result["series_tie"],
            "sub_games_won": final_result["sub_games_won"],
            "ties": final_result["ties"],
            "total_score": final_result["total_score"],
            "winner_group": final_result["winner_group"],
        },
        "sub_games": [
            {
                "sub_game_number": r["sub_game_number"],
                "roles": r["roles"],
                "result": r["result"],
                "winner_group": r["winner_group"],
                "score": r["score"],
            }
            for r in rows
        ],
    }
    return hashlib.sha256(
        json.dumps(preimage, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def build_result(
    game_id: str,
    game_uid: str,
    opponent: str,
    rows: list,
    final_result: dict,
    opp_repos: dict | None = None,
) -> dict:
    """The emailed final_game_result (series aggregate). Key order mirrors anrbj666's."""
    confirmed = bool(rows) and all(r.get("audit", {}).get("log_verified") for r in rows)
    mutual = {"sha256": mutual_agreement_sha(game_id, rows, final_result), "confirmed": confirmed}
    return {
        "_schema": (
            "Summary and final result for the WHOLE series between two teams: "
            "per-sub-game scores + aggregate; identity lives in the declaration."
        ),
        "schema_version": "1.1",
        "report_type": "final_game_result",
        "game_id": game_id,
        "game_uid": game_uid,
        "links": {
            "declaration": f"declaration_{game_id}.json",
            "config": f"config_{game_id}_g<NN>.json",
            "log": f"log_{game_id}_g<NN>.json",
            "result": f"result_{game_id}.json",
            "github": {"vibecode": OUR_REPOS, opponent: opp_repos or {}},
        },
        "timezone": "Asia/Jerusalem",
        "groups": sorted(["vibecode", opponent]),
        "num_sub_games": len(rows),
        "sub_games": rows,
        "final_result": final_result,
        "mutual_agreement": mutual,
    }
