"""Family and cross-play tournaments."""

from __future__ import annotations

from cop_worker.rl.research_evaluation.game_play import GameResult, _metrics, play_game
from cop_worker.rl.research_evaluation.policies_recurrent import ResearchPolicy
from cop_worker.rl.research_evaluation.policies_scripted import ScriptedResearchPolicy
from cop_worker.rl.train_recurrent import FAMILIES


def evaluate_families(
    policy: ResearchPolicy,
    role: str,
    historical_opponent: ResearchPolicy,
    series_per_family: int,
    seed: int,
    random_start: bool,
) -> dict:
    """Evaluate one role in exact six-game series against every family."""
    families: dict[str, dict] = {}
    all_results: list[GameResult] = []
    for family_index, family in enumerate(FAMILIES):
        opponent = (
            historical_opponent
            if family == "historical_checkpoint"
            else ScriptedResearchPolicy("thief" if role == "cop" else "cop", family)
        )
        results: list[GameResult] = []
        for series in range(series_per_family):
            for gamelet in range(1, 7):
                game_seed = seed + 100_000 * family_index + 10 * series + gamelet
                cop, thief = (policy, opponent) if role == "cop" else (opponent, policy)
                results.append(play_game(cop, thief, game_seed, random_start, gamelet))
        families[family] = _metrics(results, role)
        all_results.extend(results)
    overall = _metrics(all_results, role)
    overall.update(
        {
            "role": role,
            "start_mode": "random" if random_start else "game_json_fixed",
            "series_per_family": series_per_family,
            "held_out_series": series_per_family * len(FAMILIES),
            "worst_family_win_rate": min(item["win_rate"] for item in families.values()),
            "families": families,
        }
    )
    return overall


def evaluate_crossplay(
    cop_policy: ResearchPolicy,
    thief_policy: ResearchPolicy,
    series: int,
    seed: int,
    random_start: bool,
) -> dict:
    results = [
        play_game(
            cop_policy,
            thief_policy,
            seed + 10 * series_index + gamelet,
            random_start,
            gamelet,
        )
        for series_index in range(series)
        for gamelet in range(1, 7)
    ]
    cop = _metrics(results, "cop")
    thief = _metrics(results, "thief")
    return {
        "start_mode": "random" if random_start else "game_json_fixed",
        "series": series,
        "games": len(results),
        "cop": cop,
        "thief": thief,
    }
