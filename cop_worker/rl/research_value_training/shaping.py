"""Reward shaping, belief updates, frozen opponents, and DDQN update step."""

from __future__ import annotations

from pathlib import Path

import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.types import DomainState
from cop_worker.rl.research_evaluation import (
    RecurrentResearchPolicy,
    ResearchPolicy,
    ScriptedResearchPolicy,
    load_recurrent_network,
)
from cop_worker.rl.research_value_training.networks import (
    load_dqn_policy,
)
from cop_worker.scent import ScentFields


def _expected_distance(own: tuple[int, int], belief: BeliefEngine, grid_size: int) -> float:
    probability = belief.belief.prob
    return sum(
        float(probability[y, x]) * (abs(own[0] - x) + abs(own[1] - y))
        for y in range(grid_size)
        for x in range(grid_size)
    )


def _local_shaping(
    role: str,
    before_state: DomainState,
    after_state: DomainState,
    before_belief: BeliefEngine,
    after_belief: BeliefEngine,
) -> float:
    before_own = before_state.cop_position if role == "cop" else before_state.thief_position
    after_own = after_state.cop_position if role == "cop" else after_state.thief_position
    before_distance = _expected_distance(before_own, before_belief, before_state.grid_size)
    after_distance = _expected_distance(after_own, after_belief, after_state.grid_size)
    progress = before_distance - after_distance
    reward = 0.035 * progress if role == "cop" else -0.035 * progress
    return reward - 0.002 if role == "cop" else reward + 0.002


def _update_beliefs(
    state: DomainState,
    scent: ScentFields,
    cop_belief: BeliefEngine,
    thief_belief: BeliefEngine,
) -> tuple[ScentFields, BeliefEngine, BeliefEngine]:
    scent = scent.update(state.cop_position, state.thief_position)
    barriers = [tuple(item) for item in state.barriers]
    cop_belief = cop_belief.predict(barriers).observe_scent(scent.cop_observation_scent(), barriers)
    thief_belief = thief_belief.predict(barriers).observe_scent(
        scent.thief_observation_scent(), barriers
    )
    return scent, cop_belief, thief_belief


def _frozen_opponent(
    role: str,
    family: str,
    incumbent_path: Path,
) -> ResearchPolicy:
    opponent_role = "thief" if role == "cop" else "cop"
    if family == "historical_checkpoint":
        metadata = torch.load(incumbent_path, map_location="cpu", weights_only=True)
        if metadata.get("algorithm") == "DuelingDoubleDQN":
            return load_dqn_policy(incumbent_path, opponent_role)
        return RecurrentResearchPolicy(
            load_recurrent_network(incumbent_path, opponent_role),
            opponent_role,
            temperature=0.5 if opponent_role == "thief" else None,
        )
    return ScriptedResearchPolicy(opponent_role, family)


def _default_population(role: str) -> tuple[str, ...]:
    if role == "cop":
        return (
            "historical_checkpoint",
            "historical_checkpoint",
            "historical_checkpoint",
            "anti_loop",
            "targeted_exploit",
            "scent_following",
            "local_adversarial_ensemble",
        )
    return (
        "anti_loop",
        "anti_loop",
        "anti_loop",
        "historical_checkpoint",
        "historical_checkpoint",
        "scent_following",
        "corridor_cutting",
    )


def _terminal_reward(winner: str, role: str) -> float:
    return 1.0 if winner == role else -1.0
