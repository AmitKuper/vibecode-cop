"""Scripted opponent families the policy trains and evaluates against."""

from __future__ import annotations

import random

import numpy as np

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.domain.types import DomainState
from cop_worker.rl.train_recurrent.expert import _belief_expert_action
from cop_worker.rl.train_recurrent.opponents_historical import _historical_action
from cop_worker.rl.train_recurrent.sim import _action_position, _legal, _local_exit_count


def _opponent_action(
    state: DomainState,
    role: str,
    family: str,
    rng: random.Random,
    historical_policy=None,
    opponent_scent: list[list[float]] | None = None,
    opponent_belief: BeliefEngine | None = None,
) -> str:
    legal = _legal(state, role)
    if family == "historical_checkpoint":
        return _historical_action(
            state, role, legal, historical_policy, opponent_scent, opponent_belief
        )
    if family == "random":
        return rng.choice(legal)
    if family == "wall":
        scored = []
        for action in legal:
            result = (
                apply_joint_action(state, action, "STAY")
                if role == "cop"
                else apply_joint_action(state, "STAY", action)
            )
            pos = (
                result.new_state.cop_position if role == "cop" else result.new_state.thief_position
            )
            gs1 = state.grid_size - 1
            wall_score = min(pos[0], pos[1], gs1 - pos[0], gs1 - pos[1])
            scored.append((wall_score, action))
        return min(scored)[1]
    own_position = state.cop_position if role == "cop" else state.thief_position
    if family == "scent_following":
        if not opponent_scent or not any(any(row) for row in opponent_scent):
            return rng.choice(legal)
        target_y, target_x = np.unravel_index(
            np.asarray(opponent_scent).argmax(), np.asarray(opponent_scent).shape
        )
        scored = []
        for action in legal:
            pos = _action_position(own_position, action)
            distance = abs(pos[0] - target_x) + abs(pos[1] - target_y)
            score = -distance if role == "cop" else distance
            scored.append((score, rng.random(), action))
        return max(scored)[2]
    if opponent_belief is None:
        raise RuntimeError(f"{family} opponent requires a local Bayesian belief")
    belief_action = _belief_expert_action(own_position, role, opponent_belief, legal)
    if family == "belief_pursuit_evasion":
        return belief_action
    if family == "local_adversarial_ensemble":
        # Alternate a belief-optimal action with a wall-biased branch. Both use
        # local/public information only, but the mixture resists overfitting.
        if state.turn % 4:
            return belief_action
        wall_scored = []
        for action in legal:
            result = (
                apply_joint_action(state, action, "STAY")
                if role == "cop"
                else apply_joint_action(state, "STAY", action)
            )
            pos = (
                result.new_state.cop_position if role == "cop" else result.new_state.thief_position
            )
            gs1 = state.grid_size - 1
            wall_distance = min(pos[0], pos[1], gs1 - pos[0], gs1 - pos[1])
            wall_scored.append((-wall_distance, rng.random(), action))
        return max(wall_scored)[2]
    if family == "corridor_cutting":
        target_y, target_x = np.unravel_index(
            opponent_belief.belief.prob.argmax(), opponent_belief.belief.prob.shape
        )
        scored = []
        for action in legal:
            pos = _action_position(own_position, action)
            distance = abs(pos[0] - target_x) + abs(pos[1] - target_y)
            exits = _local_exit_count(pos, list(state.barriers), state.grid_size)
            if role == "cop":
                placement_bonus = 1.5 if action.startswith("PLACE_") and distance <= 2 else 0.0
                score = -distance + placement_bonus - 0.1 * exits
            else:
                score = distance + 0.45 * exits
            scored.append((score, rng.random(), action))
        return max(scored)[2]
    if family == "anti_loop":
        # Alternate among the best two local-belief actions and prefer cells with exits.  This
        # defeats deterministic two-cell cycles without consulting the hidden rival coordinate.
        target_y, target_x = np.unravel_index(
            opponent_belief.belief.prob.argmax(), opponent_belief.belief.prob.shape
        )
        ranked = []
        for action in legal:
            pos = _action_position(own_position, action)
            distance = abs(pos[0] - target_x) + abs(pos[1] - target_y)
            exits = _local_exit_count(pos, list(state.barriers), state.grid_size)
            score = (-distance if role == "cop" else distance) + 0.25 * exits
            ranked.append((score, action))
        ranked.sort(reverse=True)
        return ranked[state.turn % min(2, len(ranked))][1]
    if family == "targeted_exploit":
        if role == "cop":
            # The strongest local-information pursuer used to attack the historical thief gap.
            return belief_action
        from cop_worker.rl.risk_mask import belief_safe_actions

        safe = belief_safe_actions(
            own_position,
            opponent_belief.belief,
            legal,
            list(state.barriers),
            keep_fraction=0.4,
        )
        return safe[state.turn % len(safe)]
    if family == "deceptive_language":
        # Movement remains separate from language: noisy/deceptive hints alter trust, modelled
        # here as controlled uncertainty between the belief expert and another legal action.
        return belief_action if state.turn % 3 else rng.choice(legal)
    raise RuntimeError(f"unknown opponent family {family!r}")
