"""Appendix-F series scoring: per-sub-game rows + the final_game_result aggregate."""

from __future__ import annotations

from cop_worker.language import token_ledger
from league_artifacts.core import load_constitution


def score_series(
    sub_games: list,
    opponent: str,
    game_id: str,
    *,
    our_played: int = 0,
    opp_played: int = 0,
    counted: bool = False,
) -> tuple:
    """Return (rows, final_result) in the final_game_result schema.

    Appendix-F scoring: capture -> cop 20 / thief 5; survival -> thief 10 / cop 5.
    github_commit is per-sub-game (each side's repo HEAD for the role it played).
    games_played_including_this increments by 1 ONLY for a counted game (rules 37-38).
    """
    rows, tot_us, tot_them, won_us, won_them = [], 0, 0, 0, 0
    # OUR real LLM spend from the process-wide ledger (template hints record nothing,
    # so this is 0 with the LLM off — byte-identical to the old hardcoded zeros).
    # The opponent's spend is unknowable from our side and stays 0.
    our_gamelet_tokens = token_ledger.gamelet_history()
    for idx, sg in enumerate(sub_games):
        n, role = sg["sub_game"], sg["role"]
        cop_s, thief_s = (20, 5) if sg.get("outcome") == "capture" else (5, 10)
        us, them = (cop_s, thief_s) if role == "police" else (thief_s, cop_s)
        tot_us += us
        tot_them += them
        won_us += us > them
        won_them += them > us
        opp_commit = (sg.get("opp_identity") or {}).get("github_commit", "unknown")
        rows.append(
            {
                "sub_game_number": n,
                "roles": {"vibecode": role, opponent: "thief" if role == "police" else "police"},
                "started_at": sg.get("started_at", ""),
                "ended_at": sg.get("ended_at", ""),
                "result": sg.get("outcome"),
                "winner_group": "vibecode" if us > them else opponent,
                "tie": False,
                "github_commit": {
                    "vibecode": sg.get("our_commit", "unknown"),
                    opponent: opp_commit,
                },
                "tokens": {
                    "vibecode": our_gamelet_tokens[idx] if idx < len(our_gamelet_tokens) else 0,
                    opponent: 0,
                },
                "score": {"vibecode": us, opponent: them},
                "log_files": {
                    "vibecode": f"log_{game_id}_g{n:02d}.json",
                    opponent: f"log_{game_id}_g{n:02d}.json",
                },
                "audit": {"log_verified": bool(sg.get("audit_ok")), "tampered": False},
            }
        )
    inc = 1 if counted else 0
    # Tie rule: SERIES-LEVEL ADDITIVE (`series_add`) — on a level accumulated score each
    # team's total gains the App-F tie score (2). The book puts the award at the series
    # level (ch.9, App. F table 17 row 5); the reference sums per sub-game instead; course
    # staff ruled it a documented-choice contradiction. Every checked league team
    # (imreeyal, anrbj666, best2934) and the kit play series_add, and we DECLARE the rule
    # to the opponent before the first window (WARNINGS §6a) — a tie surfacing it
    # mid-series is the rule-35 two-reports shape.
    series_tie = tot_us == tot_them
    tie_score_each = int(load_constitution().get("scoring", {}).get("tie_score", 2))
    if series_tie:
        tot_us += tie_score_each
        tot_them += tie_score_each
    winner = "vibecode" if tot_us > tot_them else opponent if tot_them > tot_us else None
    # Diversity incentive (Appendix F, rule: "a win against a new opponent receives the full
    # diversity reward = 10"). Rule 52 allows only ONE counted match per rival, so a counted
    # series is by definition the first counted meeting with this opponent — a counted WIN is
    # always a win against a new counted opponent. Flag the winner; the +10 is a standings
    # bonus the league applies from this flag (per-series total_score is unchanged). Friendlies
    # (counted=False) and series ties (no winner) stay {False, False}.
    diversity = {"vibecode": False, opponent: False}
    if counted and winner is not None:
        diversity[winner] = True
    final_result = {
        "total_score": {"vibecode": tot_us, opponent: tot_them},
        "sub_games_won": {"vibecode": won_us, opponent: won_them},
        "ties": 0,
        "winner_group": winner,
        # tie_rule series_add is DECLARED in the written pairing agreement, never as an
        # extra result field — the grader's template is the authority (imreeyal §3.17).
        "series_tie": series_tie,
        "tokens_total_series": {"vibecode": token_ledger.series_total(), opponent: 0},
        "games_played_including_this": {"vibecode": our_played + inc, opponent: opp_played + inc},
        "first_meeting_between_groups": True,
        "diversity_reward_applied": diversity,
    }
    return rows, final_result
