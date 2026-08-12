"""Ablation suite: the deployed role against every scripted opponent family."""

from __future__ import annotations

from pathlib import Path

from cop_worker.rl.research_evaluation import ScriptedResearchPolicy
from eval_quality.deployed import OPPONENT_FAMILIES, DeployedPolicy
from eval_quality.game import play


def suite(
    role: str,
    belief_mode: str,
    games: int,
    seed: int,
    scent_mode: str = "train",
    artifact: Path | None = None,
) -> dict:
    """Play the deployed `role` against every scripted opponent family.

    Only OUR policy's scent view is switched by ``scent_mode``; the scripted opponents keep
    the trainer's field so opponent strength is held constant across the ablation.
    """
    ours = DeployedPolicy(role, belief_mode, artifact)
    opp_role = "thief" if role == "cop" else "cop"
    per_family, wins_total, games_total = {}, 0, 0
    for family in OPPONENT_FAMILIES:
        opp = ScriptedResearchPolicy(opp_role, family)
        wins, turns_sum = 0, 0
        for i in range(games):
            gamelet = (i % 6) + 1
            s = seed + i * 7919
            if role == "cop":
                winner, turns = play(ours, opp, s, gamelet, scent_mode=scent_mode)
            else:
                winner, turns = play(opp, ours, s, gamelet, scent_mode=scent_mode)
            wins += int(winner == role)
            turns_sum += turns
        per_family[family] = {
            "win_rate": round(wins / games, 3),
            "avg_turns": round(turns_sum / games, 1),
        }
        wins_total += wins
        games_total += games
    return {
        "role": role,
        "belief_mode": belief_mode,
        "scent_mode": scent_mode,
        "overall_win_rate": round(wins_total / games_total, 4),
        "games": games_total,
        "per_family": per_family,
    }
