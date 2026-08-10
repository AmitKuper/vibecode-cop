"""Confidence intervals, per-family summaries, and the promotion gate."""

from __future__ import annotations

import math

import numpy as np

from cop_worker.rl.train_recurrent.schedules import WORST_FAMILY_PROMOTION_FLOOR


def _wilson(wins: int, games: int) -> list[float]:
    if games == 0:
        return [0.0, 0.0]
    z = 1.96
    p = wins / games
    denominator = 1 + z * z / games
    center = (p + z * z / (2 * games)) / denominator
    margin = z * math.sqrt(p * (1 - p) / games + z * z / (4 * games * games)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _family_summary(
    role: str,
    series_per_family: int,
    wins: int,
    turns: int,
    series_wins: int,
    family_role_score: int,
    family_opponent_score: int,
    family_metrics: dict[str, int],
    series_results: list[dict],
) -> dict:
    games = series_per_family * 6
    return {
        "series": series_per_family,
        "games": games,
        "wins": wins,
        "win_rate": wins / games,
        "confidence_95": _wilson(wins, games),
        "series_wins": series_wins,
        "series_win_rate": series_wins / series_per_family,
        "series_confidence_95": _wilson(series_wins, series_per_family),
        "official_role_score": family_role_score,
        "official_opponent_score": family_opponent_score,
        "average_turns": turns / games,
        "capture_rate": (wins if role == "cop" else games - wins) / games,
        "survival_rate": (games - wins if role == "cop" else wins) / games,
        "barrier_placements": family_metrics.get("barrier_placements", 0),
        "barrier_efficiency": wins / max(family_metrics.get("barrier_placements", 0), 1),
        "risk_mask_pruned_rate": family_metrics.get("risk_pruned", 0)
        / max(family_metrics.get("legal_candidates", 0), 1),
        "series_results": series_results,
    }


def _promotion_comparison(candidate: dict, baseline: dict, seed: int) -> dict:
    candidate_scores = []
    baseline_scores = []
    for family in candidate["families"]:
        candidate_scores.extend(
            item["role_score"] for item in candidate["families"][family]["series_results"]
        )
        baseline_scores.extend(
            item["role_score"] for item in baseline["families"][family]["series_results"]
        )
    differences = np.array(candidate_scores) - np.array(baseline_scores)
    rng = np.random.default_rng(seed + 90_000)
    bootstrap_means = np.array(
        [
            differences[rng.integers(0, len(differences), len(differences))].mean()
            for _ in range(5000)
        ]
    )
    confidence = np.percentile(bootstrap_means, [2.5, 97.5]).tolist()
    no_zero_family = all(item["win_rate"] > 0 for item in candidate["families"].values())
    p99 = candidate["inference_latency_ms"]["p99"]
    role = candidate.get("role")
    worst_family_floor = WORST_FAMILY_PROMOTION_FLOOR.get(role, 0.0)
    worst_family = min(item["win_rate"] for item in candidate["families"].values())
    baseline_worst = min(item.get("win_rate", 0.0) for item in baseline["families"].values())
    no_catastrophic_regression = worst_family >= max(worst_family_floor, baseline_worst - 0.05)
    passed = (
        confidence[0] > 0
        and no_zero_family
        and candidate["technical_failures"] == 0
        and p99 is not None
        and p99 < 30.0
        and no_catastrophic_regression
    )
    return {
        "criterion": (
            "paired bootstrap 95% lower official-score bound > 0; every family nonzero; "
            "zero technical failures; p99 inference < 30 ms; role worst-family floor met"
        ),
        "candidate_official_role_score": candidate["official_role_score"],
        "baseline_official_role_score": baseline["official_role_score"],
        "mean_series_role_score_improvement": float(differences.mean()),
        "bootstrap_95": confidence,
        "worst_family_win_rate": worst_family,
        "predeclared_worst_family_floor": worst_family_floor,
        "baseline_worst_family_win_rate": baseline_worst,
        "no_catastrophic_worst_family_regression": no_catastrophic_regression,
        "passed": passed,
    }
