"""Single-game rollout and aggregate metrics."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

import numpy as np

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.rl.research_evaluation.policies_recurrent import ResearchPolicy
from cop_worker.rl.train_recurrent import _initial_state
from cop_worker.scent import make_scent_fields


@dataclass(frozen=True)
class GameResult:
    winner: str
    turns: int
    cop_score: int
    thief_score: int
    cop_latency_ms: tuple[float, ...]
    thief_latency_ms: tuple[float, ...]


def play_game(
    cop_policy: ResearchPolicy,
    thief_policy: ResearchPolicy,
    seed: int,
    random_start: bool,
    gamelet: int = 1,
) -> GameResult:
    """Play one game using canonical physics and symmetric local beliefs."""
    rng = random.Random(seed)
    state = _initial_state(rng, random_start=random_start, grid_size=7)
    scent = make_scent_fields(7)
    cop_belief = BeliefEngine(7, "cop")
    thief_belief = BeliefEngine(7, "thief")
    cop_policy.reset(seed + 1_000_003)
    thief_policy.reset(seed + 2_000_003)
    cop_latency: list[float] = []
    thief_latency: list[float] = []
    while state.turn < 35:
        started = time.perf_counter()
        cop_action = cop_policy.act(state, scent, cop_belief, rng, gamelet)
        cop_latency.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        thief_action = thief_policy.act(state, scent, thief_belief, rng, gamelet)
        thief_latency.append((time.perf_counter() - started) * 1000)
        result = apply_joint_action(state, cop_action, thief_action)
        state = result.new_state
        scent = scent.update(state.cop_position, state.thief_position)
        barriers = [tuple(item) for item in state.barriers]
        cop_belief = cop_belief.predict(barriers).observe_scent(
            scent.cop_observation_scent(), barriers
        )
        thief_belief = thief_belief.predict(barriers).observe_scent(
            scent.thief_observation_scent(), barriers
        )
        if result.outcome.value != "ongoing":
            winner = "cop" if result.outcome.value == "cop_win" else "thief"
            return GameResult(
                winner,
                state.turn,
                result.cop_score,
                result.thief_score,
                tuple(cop_latency),
                tuple(thief_latency),
            )
    raise RuntimeError("canonical transition failed to terminate by turn 35")


def _wilson(wins: int, games: int) -> list[float]:
    if games == 0:
        return [0.0, 0.0]
    z = 1.96
    p = wins / games
    denominator = 1 + z * z / games
    center = (p + z * z / (2 * games)) / denominator
    margin = z * math.sqrt(p * (1 - p) / games + z * z / (4 * games**2)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _metrics(results: list[GameResult], role: str) -> dict:
    wins = sum(result.winner == role for result in results)
    role_score = sum(
        result.cop_score if role == "cop" else result.thief_score for result in results
    )
    opponent_score = sum(
        result.thief_score if role == "cop" else result.cop_score for result in results
    )
    latency = [
        item
        for result in results
        for item in (result.cop_latency_ms if role == "cop" else result.thief_latency_ms)
    ]
    return {
        "games": len(results),
        "wins": wins,
        "win_rate": wins / len(results),
        "confidence_95": _wilson(wins, len(results)),
        "official_role_score": role_score,
        "official_opponent_score": opponent_score,
        "average_turns": sum(result.turns for result in results) / len(results),
        "inference_latency_ms": {
            "p50": float(np.percentile(latency, 50)),
            "p95": float(np.percentile(latency, 95)),
            "p99": float(np.percentile(latency, 99)),
        },
        "technical_failures": 0,
    }
