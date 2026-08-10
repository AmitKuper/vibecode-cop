"""Belief-particle sampling and belief-search action scores."""

from __future__ import annotations

import numpy as np

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.domain.types import DomainState
from cop_worker.rl.research_evaluation.search_core import (
    _determinized_value,
    _fast_legal,
    _hypothetical_state,
    _terminal_value,
)


def _belief_particles(
    state: DomainState,
    role: str,
    belief: BeliefEngine,
    max_particles: int,
) -> list[tuple[tuple[int, int], float]]:
    probability = belief.belief.prob.copy()
    for x, y in state.barriers:
        probability[y, x] = 0.0
    own = state.cop_position if role == "cop" else state.thief_position
    probability[own[1], own[0]] = 0.0
    flat = probability.ravel()
    indices = np.argsort(flat)[::-1][:max_particles]
    masses = flat[indices]
    total = float(masses.sum())
    if total <= 1e-12:
        return []
    return [
        ((int(index % state.grid_size), int(index // state.grid_size)), float(mass / total))
        for index, mass in zip(indices, masses, strict=True)
        if mass > 0
    ]


def belief_search_scores(
    state: DomainState,
    role: str,
    belief: BeliefEngine,
    legal_actions: list[str],
    depth: int = 1,
    max_particles: int = 8,
) -> dict[str, float]:
    """Score root actions using belief-weighted determinized simultaneous search.

    Only positions sampled from the role's Bayesian belief enter the search; the
    real hidden coordinate in ``state`` is overwritten before every rollout.
    The method is an inexpensive approximation to public-belief search, not an
    exact POMDP solver.
    """
    particles = _belief_particles(state, role, belief, max_particles)
    if not particles:
        return dict.fromkeys(legal_actions, 0.0)
    opponent_role = "thief" if role == "cop" else "cop"
    scores: dict[str, float] = {}
    worlds = [
        (
            _hypothetical_state(state, role, position),
            mass,
        )
        for position, mass in particles
    ]
    worlds_with_replies = [
        (world, mass, _fast_legal(world, opponent_role)) for world, mass in worlds
    ]
    for own_action in legal_actions:
        expected = 0.0
        for hypothetical, mass, opponent_actions in worlds_with_replies:
            responses = []
            for opponent_action in opponent_actions:
                cop_action, thief_action = (
                    (own_action, opponent_action)
                    if role == "cop"
                    else (opponent_action, own_action)
                )
                result = apply_joint_action(hypothetical, cop_action, thief_action)
                outcome = result.outcome.value
                value = (
                    _terminal_value(outcome, role, result.new_state.turn)
                    if outcome != "ongoing"
                    else _determinized_value(result.new_state, role, depth - 1)
                )
                responses.append(value)
            # A mostly-adversarial response is less brittle than pure minimax
            # when the opponent model is stochastic or belief-greedy.
            expected += mass * (0.75 * min(responses) + 0.25 * float(np.mean(responses)))
        scores[own_action] = expected
    return scores
