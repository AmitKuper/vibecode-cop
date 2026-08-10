"""Held-out tournament: exact six-gamelet series against every opponent family."""

from __future__ import annotations

import random
import time

import numpy as np
import torch

import cop_worker.rl.train_recurrent as _pkg
from cop_worker.rl.train_recurrent.schedules import FAMILIES
from cop_worker.rl.train_recurrent.stats import _family_summary, _wilson


def evaluate(
    network,
    role: str,
    series_per_family: int,
    seed: int,
    historical_policy,
    inference_temperature: float | None = None,
    force_expert_actor: bool = False,
    feature_mode: str = "full",
    recurrent_enabled: bool = True,
    legal_mask_enabled: bool = True,
    risk_mask_enabled: bool = False,
    barrier_actions_enabled: bool = True,
    grid_size: int = 7,
) -> dict:
    """Run held-out tournaments composed only of exact six-gamelet series."""
    families = {}
    total_wins = total_games = total_turns = total_series_wins = 0
    total_role_score = total_opponent_score = 0
    total_decisions = total_illegal_selected = 0
    latency_samples: list[float] = []
    eval_families = [
        family
        for family in FAMILIES
        if family != "historical_checkpoint" or historical_policy is not None
    ]
    torch.manual_seed(seed + 50_000)
    start = time.perf_counter()
    for family_index, family in enumerate(eval_families):
        rng = random.Random(seed + 10_000 + family_index)
        wins = turns = series_wins = family_role_score = family_opponent_score = 0
        series_results = []
        family_metrics: dict[str, int] = {}
        for series_index in range(series_per_family):
            series_role_score = series_opponent_score = series_gamelet_wins = 0
            for _gamelet in range(6):
                _trajectory, winner, length = _pkg._run_episode(
                    network,
                    role,
                    family,
                    rng,
                    training=False,
                    random_start=True,
                    historical_policy=historical_policy,
                    evaluation_temperature=inference_temperature,
                    force_expert_actor=force_expert_actor,
                    latency_samples=latency_samples,
                    episode_metrics=family_metrics,
                    feature_mode=feature_mode,
                    recurrent_enabled=recurrent_enabled,
                    legal_mask_enabled=legal_mask_enabled,
                    risk_mask_enabled=risk_mask_enabled,
                    barrier_actions_enabled=barrier_actions_enabled,
                    grid_size=grid_size,
                )
                won = winner == role
                wins += int(won)
                series_gamelet_wins += int(won)
                turns += length
                if role == "cop":
                    role_score, opponent_score = (20, 5) if won else (5, 10)
                else:
                    role_score, opponent_score = (10, 5) if won else (5, 20)
                series_role_score += role_score
                series_opponent_score += opponent_score
            series_won = series_role_score > series_opponent_score
            series_wins += int(series_won)
            family_role_score += series_role_score
            family_opponent_score += series_opponent_score
            series_results.append(
                {
                    "series": series_index + 1,
                    "gamelet_wins": series_gamelet_wins,
                    "role_score": series_role_score,
                    "opponent_score": series_opponent_score,
                    "series_won": series_won,
                }
            )
        families[family] = _family_summary(
            role,
            series_per_family,
            wins,
            turns,
            series_wins,
            family_role_score,
            family_opponent_score,
            family_metrics,
            series_results,
        )
        total_wins += wins
        total_games += series_per_family * 6
        total_turns += turns
        total_series_wins += series_wins
        total_role_score += family_role_score
        total_opponent_score += family_opponent_score
        total_decisions += family_metrics.get("decisions", 0)
        total_illegal_selected += family_metrics.get("illegal_selected", 0)
    elapsed = time.perf_counter() - start
    total_series = series_per_family * len(FAMILIES)
    percentiles = (
        np.percentile(latency_samples, [50, 95, 99]).tolist()
        if latency_samples
        else [None, None, None]
    )
    return {
        "role": role,
        "held_out_series": total_series,
        "held_out_games": total_games,
        "wins": total_wins,
        "win_rate": total_wins / total_games,
        "confidence_95": _wilson(total_wins, total_games),
        "series_wins": total_series_wins,
        "series_win_rate": total_series_wins / total_series,
        "series_confidence_95": _wilson(total_series_wins, total_series),
        "official_role_score": total_role_score,
        "official_opponent_score": total_opponent_score,
        "worst_family_win_rate": min(item["win_rate"] for item in families.values()),
        "worst_family_series_win_rate": min(item["series_win_rate"] for item in families.values()),
        "average_turns": total_turns / total_games,
        "average_inference_and_environment_ms": elapsed * 1000 / max(total_turns, 1),
        "inference_latency_ms": {
            "p50": percentiles[0],
            "p95": percentiles[1],
            "p99": percentiles[2],
        },
        "technical_failures": 0,
        "illegal_action_rate": total_illegal_selected / max(total_decisions, 1),
        "action_correction_rate": 0.0,
        "inference_mode": "low_temp" if inference_temperature else "argmax",
        "inference_temperature": inference_temperature,
        "families": families,
    }
