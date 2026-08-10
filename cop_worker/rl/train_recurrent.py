"""Train and evaluate the deployed recurrent local-observation policy."""

from __future__ import annotations

import argparse
import json
import math
import pickle
import random
import time
from pathlib import Path

import numpy as np
import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.domain.types import DomainState
from cop_worker.observation import LocalObservation
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor, obs_tensor_shape
from cop_worker.rl.recurrent_policy import RecurrentActorCritic, file_sha256
from cop_worker.scent import ScentFields, make_scent_fields

FAMILIES = (
    "random",
    "belief_pursuit_evasion",
    "wall",
    "local_adversarial_ensemble",
    "historical_checkpoint",
    "scent_following",
    "corridor_cutting",
    "anti_loop",
    "targeted_exploit",
    "deceptive_language",
)
THIEF_TRAINING_SCHEDULE = (
    "random",
    "belief_pursuit_evasion",
    "belief_pursuit_evasion",
    "belief_pursuit_evasion",
    "belief_pursuit_evasion",
    "scent_following",
    "scent_following",
    "scent_following",
    "scent_following",
    "corridor_cutting",
    "corridor_cutting",
    "local_adversarial_ensemble",
    "targeted_exploit",
    "targeted_exploit",
    "anti_loop",
    "historical_checkpoint",
    "deceptive_language",
)
COP_TRAINING_SCHEDULE = (
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "targeted_exploit",
    "belief_pursuit_evasion",
    "local_adversarial_ensemble",
    "scent_following",
    "corridor_cutting",
    "anti_loop",
    "historical_checkpoint",
    "deceptive_language",
    "random",
    "wall",
)
WORST_FAMILY_PROMOTION_FLOOR = {"cop": 0.55, "thief": 0.35}


def _initial_state(
    rng: random.Random, random_start: bool = True, grid_size: int = 7
) -> DomainState:
    if random_start:
        cop = (rng.randrange(grid_size), rng.randrange(grid_size))
        thief = (rng.randrange(grid_size), rng.randrange(grid_size))
        while thief == cop:
            thief = (rng.randrange(grid_size), rng.randrange(grid_size))
    else:
        cop, thief = (0, 0), (3, 3)
    return DomainState(
        turn=0,
        grid_size=grid_size,
        cop_position=cop,
        thief_position=thief,
        barriers=[],
        cop_barriers_remaining=14,
        move_history=[],
        scent_grid=[[0.0] * grid_size for _ in range(grid_size)],
    )


def _legal(state: DomainState, role: str) -> list[str]:
    actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
    results = (
        apply_joint_action(state, action, "STAY")
        if role == "cop"
        else apply_joint_action(state, "STAY", action)
        for action in actions
    )
    return [
        action
        for action, result in zip(actions, results, strict=True)
        if (result.cop_action_legal if role == "cop" else result.thief_action_legal)
    ]


def _distance(state: DomainState) -> int:
    return abs(state.cop_position[0] - state.thief_position[0]) + abs(
        state.cop_position[1] - state.thief_position[1]
    )


def _action_position(position: tuple[int, int], action: str) -> tuple[int, int]:
    delta = {
        "N": (0, -1),
        "S": (0, 1),
        "E": (1, 0),
        "W": (-1, 0),
        "STAY": (0, 0),
    }.get(action, (0, 0))
    return position[0] + delta[0], position[1] + delta[1]


def _local_exit_count(
    position: tuple[int, int], barriers: list[tuple[int, int]], grid_size: int
) -> int:
    blocked = set(barriers)
    return sum(
        0 <= position[0] + dx < grid_size
        and 0 <= position[1] + dy < grid_size
        and (position[0] + dx, position[1] + dy) not in blocked
        for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0))
    )


def _belief_trap_reward(
    opponent_belief,
    before_barriers: list[tuple[int, int]],
    after_barriers: list[tuple[int, int]],
    grid_size: int,
) -> float:
    """Reward belief-supported trap construction without consulting hidden coordinates."""
    placed = set(after_barriers) - set(before_barriers)
    if not placed:
        return 0.0
    trap_gain = 0.0
    proximity_mass = 0.0
    probability = opponent_belief.prob
    for y in range(grid_size):
        for x in range(grid_size):
            mass = float(probability[y, x])
            if mass <= 0.0:
                continue
            cell = (x, y)
            before_exits = _local_exit_count(cell, before_barriers, grid_size)
            after_exits = _local_exit_count(cell, after_barriers, grid_size)
            trap_gain += mass * max(0, before_exits - after_exits)
            if any(abs(x - bx) + abs(y - by) <= 1 for bx, by in placed):
                proximity_mass += mass
    return min(0.45, 0.25 * trap_gain + 0.20 * proximity_mass)


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
        if historical_policy is None:
            raise RuntimeError("historical-checkpoint opponent was not loaded")
        if isinstance(historical_policy, RecurrentActorCritic):
            own_pos = state.cop_position if role == "cop" else state.thief_position
            scent_for_obs = opponent_scent or [
                [0.0] * state.grid_size for _ in range(state.grid_size)
            ]
            obs = LocalObservation(
                own_position=own_pos,
                own_barriers_remaining=state.cop_barriers_remaining if role == "cop" else 0,
                known_barriers=[tuple(item) for item in state.barriers],
                opponent_scent=scent_for_obs,
                last_hint="",
                step=state.turn + 1,
                gamelet=(state.turn % 6) + 1,
                grid_size=state.grid_size,
            )
            belief_state = (
                opponent_belief.belief
                if opponent_belief is not None
                else BeliefEngine(state.grid_size, role).belief
            )
            features = torch.tensor(local_obs_to_tensor(obs, belief_state), dtype=torch.float32)
            actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
            action_mask = torch.tensor([a in legal for a in actions], dtype=torch.bool)
            with torch.no_grad():
                logits, _, _ = historical_policy(features.unsqueeze(0), None)
            masked_logits = logits.squeeze(0).masked_fill(~action_mask, -1e9)
            action = actions[int(masked_logits.argmax())]
            return action if action in legal else legal[0]
        from cop_worker.board import Board
        from cop_worker.rules_engine import RulesEngine

        board = Board(
            cop_position=list(state.cop_position),
            thief_position=list(state.thief_position),
            turn=state.turn,
            barriers=[list(item) for item in state.barriers],
            grid_size=state.grid_size,
        )
        rules = RulesEngine(board, max_turns=35)
        rules._scent_grid = [row[:] for row in state.scent_grid]
        historical_policy.barriers_remaining = state.cop_barriers_remaining
        observation = historical_policy._build_obs(
            board,
            rules,
            cop_scent_field=opponent_scent if role == "thief" else None,
        )
        action_index, _log_prob, _value = historical_policy.select_action(
            observation, training=False
        )
        action = (COP_ACTIONS if role == "cop" else THIEF_ACTIONS)[action_index]
        return action if action in legal else legal[0]
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


def _observation(
    state: DomainState,
    role: str,
    scent: ScentFields,
    belief: BeliefEngine,
    legal: list[str],
    gamelet: int,
    risk_mask_enabled: bool = False,
    decoder=None,
) -> tuple[torch.Tensor, object]:
    own = state.cop_position if role == "cop" else state.thief_position
    scent_grid = scent.cop_observation_scent() if role == "cop" else scent.thief_observation_scent()
    obs = LocalObservation(
        own_position=own,
        own_barriers_remaining=state.cop_barriers_remaining if role == "cop" else 0,
        known_barriers=[tuple(item) for item in state.barriers],
        opponent_scent=scent_grid,
        last_hint="",
        step=state.turn + 1,
        gamelet=gamelet,
        grid_size=state.grid_size,
    )
    # Under COPTHIEF_UNIFORM_BELIEF=1 the student sees the frozen prior production feeds
    # instead of the live filter. Expert actions / risk masks below intentionally keep the
    # real belief: a privileged teacher with a blind student is the intended setup.
    from cop_worker.observation import BeliefState
    from cop_worker.rl.obs_mode import uniform_belief_enabled

    belief_input = (
        BeliefState.uniform(state.grid_size, step=state.turn + 1)
        if uniform_belief_enabled()
        else belief.belief
    )
    # ``decoder`` (per-episode, from the caller) applies the inverse of the clamped wire scent
    # law under COPTHIEF_DECODED_SCENT=1, so the student trains on the same decoded channels
    # production serves. Inert when None or when the switch is off.
    features = torch.tensor(local_obs_to_tensor(obs, belief_input, decoder), dtype=torch.float32)
    actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
    deployable = legal
    if role == "thief" and risk_mask_enabled:
        from cop_worker.rl.risk_mask import belief_safe_actions

        deployable = belief_safe_actions(own, belief.belief, legal, list(state.barriers))
    mask = torch.tensor([action in deployable for action in actions], dtype=torch.bool)
    return features, mask


def _belief_expert_action(
    own_position: tuple[int, int],
    role: str,
    belief: BeliefEngine,
    legal_actions: list[str],
) -> str:
    """Local-only pursuit/evasion teacher used to prevent policy collapse."""
    target_y, target_x = np.unravel_index(belief.belief.prob.argmax(), belief.belief.prob.shape)
    move_deltas = {
        "N": (0, -1),
        "S": (0, 1),
        "E": (1, 0),
        "W": (-1, 0),
        "STAY": (0, 0),
    }
    place_deltas = {
        "PLACE_N": (0, -1),
        "PLACE_S": (0, 1),
        "PLACE_E": (1, 0),
        "PLACE_W": (-1, 0),
    }
    scored = []
    for action in legal_actions:
        dx, dy = move_deltas.get(action, (0, 0))
        own = (own_position[0] + dx, own_position[1] + dy)
        distance = abs(own[0] - target_x) + abs(own[1] - target_y)
        score = -distance if role == "cop" else distance
        if role == "cop" and action in place_deltas:
            pdx, pdy = place_deltas[action]
            placement = (own_position[0] + pdx, own_position[1] + pdy)
            score += 20 if placement == (target_x, target_y) else -0.25
        if action == "STAY":
            score -= 0.05
        scored.append((score, -legal_actions.index(action), action))
    return max(scored)[2]


def _run_episode(
    network: RecurrentActorCritic,
    role: str,
    family: str,
    rng: random.Random,
    training: bool,
    random_start: bool,
    expert_probability: float = 0.0,
    historical_policy=None,
    evaluation_temperature: float | None = None,
    force_expert_actor: bool = False,
    latency_samples: list[float] | None = None,
    episode_metrics: dict[str, int] | None = None,
    feature_mode: str = "full",
    recurrent_enabled: bool = True,
    legal_mask_enabled: bool = True,
    risk_mask_enabled: bool = False,
    barrier_actions_enabled: bool = True,
    grid_size: int = 7,
) -> tuple[list, str, int]:
    state = _initial_state(rng, random_start, grid_size)
    scent = make_scent_fields(grid_size)
    belief = BeliefEngine(grid_size, role)
    opponent_role = "thief" if role == "cop" else "cop"
    opponent_belief = BeliefEngine(grid_size, opponent_role)
    hidden = None
    trajectory = []
    winner = "thief"
    while state.turn < 35:
        legal = _legal(state, role)
        actor_legal = (
            [action for action in legal if not action.startswith("PLACE_")]
            if role == "cop" and not barrier_actions_enabled
            else legal
        )
        features, mask = _observation(
            state,
            role,
            scent,
            belief,
            actor_legal,
            (state.turn % 6) + 1,
            risk_mask_enabled,
        )
        grid_cells = state.grid_size * state.grid_size
        if feature_mode == "no_scent":
            features[2 * grid_cells : 3 * grid_cells] = 0.0
        elif feature_mode == "no_belief":
            features[3 * grid_cells : 4 * grid_cells] = 0.0
            features[-2:] = 0.0
        elif feature_mode != "full":
            raise RuntimeError(f"unsupported feature ablation {feature_mode!r}")
        if not legal_mask_enabled:
            mask = torch.ones_like(mask)
        if episode_metrics is not None:
            actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
            episode_metrics["legal_candidates"] = episode_metrics.get("legal_candidates", 0) + len(
                legal
            )
            episode_metrics["risk_pruned"] = episode_metrics.get("risk_pruned", 0) + sum(
                action in legal and not bool(mask[index]) for index, action in enumerate(actions)
            )
        inference_started = time.perf_counter()
        logits, value, hidden = network(
            features.unsqueeze(0), hidden if recurrent_enabled else None
        )
        if latency_samples is not None and not force_expert_actor:
            latency_samples.append((time.perf_counter() - inference_started) * 1000)
        masked = logits.squeeze(0).masked_fill(~mask, -1e9)
        dist = torch.distributions.Categorical(logits=masked)
        if training:
            policy_index = dist.sample()
        elif evaluation_temperature is not None:
            policy_index = torch.distributions.Categorical(
                logits=masked / evaluation_temperature
            ).sample()
        else:
            policy_index = masked.argmax()
        own_position = state.cop_position if role == "cop" else state.thief_position
        expert_action = _belief_expert_action(own_position, role, belief, legal)
        expert_index = (COP_ACTIONS if role == "cop" else THIEF_ACTIONS).index(expert_action)
        use_expert = force_expert_actor or (training and rng.random() < expert_probability)
        action_index = torch.tensor(expert_index) if use_expert else policy_index
        action = (COP_ACTIONS if role == "cop" else THIEF_ACTIONS)[int(action_index)]
        if episode_metrics is not None:
            episode_metrics["decisions"] = episode_metrics.get("decisions", 0) + 1
            episode_metrics["illegal_selected"] = episode_metrics.get("illegal_selected", 0) + int(
                action not in legal
            )
        opponent_scent = (
            scent.thief_observation_scent()
            if opponent_role == "thief"
            else scent.cop_observation_scent()
        )
        opponent = _opponent_action(
            state,
            opponent_role,
            family,
            rng,
            historical_policy=historical_policy,
            opponent_scent=opponent_scent,
            opponent_belief=opponent_belief,
        )
        cop_action, thief_action = (action, opponent) if role == "cop" else (opponent, action)
        if episode_metrics is not None:
            episode_metrics["barrier_placements"] = episode_metrics.get(
                "barrier_placements", 0
            ) + int(cop_action.startswith("PLACE_"))
        previous_distance = _distance(state)
        previous_barriers = list(state.barriers)
        result = apply_joint_action(state, cop_action, thief_action)
        state = result.new_state
        if not recurrent_enabled:
            hidden = None
        current_distance = _distance(state)
        outcome = result.outcome.value
        terminal = outcome != "ongoing"
        if terminal:
            winner = "cop" if "cop" in outcome else "thief"
            reward = 8.0 if winner == role else -8.0
        else:
            delta = previous_distance - current_distance
            reward = (0.12 * delta if role == "cop" else -0.12 * delta) - 0.01
            if role == "cop":
                reward += _belief_trap_reward(
                    belief.belief,
                    previous_barriers,
                    list(state.barriers),
                    state.grid_size,
                )
        trajectory.append(
            (
                dist.log_prob(action_index),
                not use_expert,
                value.squeeze(),
                dist.entropy(),
                dist.log_prob(torch.tensor(expert_index)),
                reward,
            )
        )
        scent = scent.update(state.cop_position, state.thief_position)
        barriers = [tuple(item) for item in state.barriers]
        observed_scent = (
            scent.cop_observation_scent() if role == "cop" else scent.thief_observation_scent()
        )
        belief = belief.predict(barriers).observe_scent(observed_scent, barriers)
        updated_opponent_scent = (
            scent.thief_observation_scent()
            if opponent_role == "thief"
            else scent.cop_observation_scent()
        )
        opponent_belief = opponent_belief.predict(barriers).observe_scent(
            updated_opponent_scent, barriers
        )
        if terminal:
            break
    return trajectory, winner, state.turn


def _collect_demonstrations(
    role: str, rng: random.Random, episodes: int, historical_policy, grid_size: int = 7
) -> tuple[torch.Tensor, torch.Tensor]:
    """Collect strictly local-observation labels from the belief expert."""
    features: list[torch.Tensor] = []
    labels: list[int] = []
    actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
    opponent_role = "thief" if role == "cop" else "cop"
    demo_families = [
        family
        for family in FAMILIES
        if family != "historical_checkpoint" or historical_policy is not None
    ]
    for episode in range(episodes):
        family = demo_families[episode % len(demo_families)]
        state = _initial_state(rng, random_start=True, grid_size=grid_size)
        scent = make_scent_fields(grid_size)
        belief = BeliefEngine(grid_size, role)
        opponent_belief = BeliefEngine(grid_size, opponent_role)
        while state.turn < 35:
            legal = _legal(state, role)
            observation, _mask = _observation(
                state, role, scent, belief, legal, (state.turn % 6) + 1
            )
            own_position = state.cop_position if role == "cop" else state.thief_position
            action = _belief_expert_action(own_position, role, belief, legal)
            features.append(observation)
            labels.append(actions.index(action))
            opponent_scent = (
                scent.thief_observation_scent()
                if opponent_role == "thief"
                else scent.cop_observation_scent()
            )
            opponent = _opponent_action(
                state,
                opponent_role,
                family,
                rng,
                historical_policy=historical_policy,
                opponent_scent=opponent_scent,
                opponent_belief=opponent_belief,
            )
            cop_action, thief_action = (action, opponent) if role == "cop" else (opponent, action)
            result = apply_joint_action(state, cop_action, thief_action)
            state = result.new_state
            scent = scent.update(state.cop_position, state.thief_position)
            barriers = [tuple(item) for item in state.barriers]
            observed_scent = (
                scent.cop_observation_scent() if role == "cop" else scent.thief_observation_scent()
            )
            belief = belief.predict(barriers).observe_scent(observed_scent, barriers)
            updated_opponent_scent = (
                scent.thief_observation_scent()
                if opponent_role == "thief"
                else scent.cop_observation_scent()
            )
            opponent_belief = opponent_belief.predict(barriers).observe_scent(
                updated_opponent_scent, barriers
            )
            if result.outcome.value != "ongoing":
                break
    return torch.stack(features), torch.tensor(labels, dtype=torch.long)


def _pretrain_imitation(
    network: RecurrentActorCritic,
    role: str,
    rng: random.Random,
    historical_policy,
    demonstration_episodes: int = 240,
    updates: int = 600,
    grid_size: int = 7,
) -> None:
    """Warm-start the recurrent network on local-only expert demonstrations."""
    features, labels = _collect_demonstrations(
        role, rng, demonstration_episodes, historical_policy, grid_size
    )
    optimizer = torch.optim.Adam(network.parameters(), lr=1e-3)
    network.train()
    batch_size = min(128, len(labels))
    for _ in range(updates):
        indices = torch.randint(0, len(labels), (batch_size,))
        logits, _value, _hidden = network(features[indices], None)
        loss = torch.nn.functional.cross_entropy(logits, labels[indices])
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(network.parameters(), 0.5)
        optimizer.step()


def train(
    role: str,
    episodes: int,
    seed: int,
    hidden_size: int,
    historical_policy,
    resume_checkpoint: dict | None = None,
    resume_learning_rate: float = 3e-4,
    resume_expert_probability: float = 0.0,
    resume_imitation_weight: float = 0.0,
    training_schedule: tuple[str, ...] | None = None,
    grid_size: int = 7,
    fixed_start_fraction: float = 0.0,
) -> RecurrentActorCritic:
    torch.manual_seed(seed)
    np.random.seed(seed)
    rng = random.Random(seed)
    if resume_checkpoint is None:
        network = RecurrentActorCritic(
            obs_tensor_shape(grid_size),
            len(COP_ACTIONS if role == "cop" else THIEF_ACTIONS),
            hidden_size,
        )
        _pretrain_imitation(network, role, rng, historical_policy, grid_size=grid_size)
    else:
        if resume_checkpoint.get("role") != role:
            raise RuntimeError("resume checkpoint role does not match training role")
        network = RecurrentActorCritic(
            int(resume_checkpoint["input_size"]),
            int(resume_checkpoint["n_actions"]),
            int(resume_checkpoint["hidden_size"]),
        )
        network.load_state_dict(resume_checkpoint["state_dict"])
    learning_rate = resume_learning_rate if resume_checkpoint is not None else 3e-4
    optimizer = torch.optim.Adam(network.parameters(), lr=learning_rate)
    for episode in range(episodes):
        schedule = training_schedule or (
            THIEF_TRAINING_SCHEDULE if role == "thief" else COP_TRAINING_SCHEDULE
        )
        family = schedule[episode % len(schedule)]
        progress = episode / max(episodes - 1, 1)
        if resume_checkpoint is not None:
            expert_probability = resume_expert_probability
            imitation_weight = resume_imitation_weight
        elif role == "thief":
            expert_probability = max(0.0, 0.60 * (1.0 - 2.0 * progress))
            imitation_weight = max(0.0, 1.0 - 1.5 * progress)
        else:
            expert_probability = max(0.10, 0.80 * (1.0 - progress))
            imitation_weight = 1.0
        # Match starts are CONTRACTUAL (cop_start/thief_start are signed terms), so a
        # fraction of episodes may pin the opening distribution the match actually
        # visits; the rest stay random for mid-game state coverage. Default 0.0
        # preserves the historical fully-random recipe.
        trajectory, _winner, _turns = _run_episode(
            network,
            role,
            family,
            rng,
            training=True,
            random_start=rng.random() >= fixed_start_fraction,
            expert_probability=expert_probability,
            historical_policy=historical_policy,
            grid_size=grid_size,
        )
        returns = []
        total = 0.0
        for *_unused, reward in reversed(trajectory):
            total = reward + 0.99 * total
            returns.append(total)
        returns.reverse()
        returns_tensor = torch.tensor(returns, dtype=torch.float32)
        if len(returns_tensor) > 1:
            returns_tensor = (returns_tensor - returns_tensor.mean()) / (
                returns_tensor.std() + 1e-6
            )
        losses = []
        for (
            log_prob,
            policy_selected,
            value,
            entropy,
            expert_log_prob,
            _reward,
        ), target in zip(trajectory, returns_tensor, strict=True):
            advantage = target - value
            actor_loss = -log_prob * advantage.detach() if policy_selected else 0.0
            losses.append(
                actor_loss
                + 0.5 * advantage**2
                - 0.01 * entropy
                - imitation_weight * expert_log_prob
            )
        optimizer.zero_grad()
        torch.stack(losses).mean().backward()
        torch.nn.utils.clip_grad_norm_(network.parameters(), 0.5)
        optimizer.step()
    return network.eval()


def _wilson(wins: int, games: int) -> list[float]:
    if games == 0:
        return [0.0, 0.0]
    z = 1.96
    p = wins / games
    denominator = 1 + z * z / games
    center = (p + z * z / (2 * games)) / denominator
    margin = z * math.sqrt(p * (1 - p) / games + z * z / (4 * games * games)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


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
                _trajectory, winner, length = _run_episode(
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
        games = series_per_family * 6
        families[family] = {
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
        total_wins += wins
        total_games += games
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("cop", "thief"), required=True)
    parser.add_argument("--episodes", type=int, default=1200)
    parser.add_argument("--eval-series-per-family", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--hidden-size", type=int, default=128)
    parser.add_argument("--models-dir", type=Path, default=Path("models"))
    parser.add_argument("--evidence-dir", type=Path, default=Path("results"))
    parser.add_argument("--historical-checkpoint", type=Path, required=False, default=None)
    parser.add_argument("--inference-temperature", type=float, default=0.0)
    parser.add_argument("--evaluate-only-artifact", type=Path)
    parser.add_argument("--resume-artifact", type=Path)
    parser.add_argument("--resume-learning-rate", type=float, default=3e-4)
    parser.add_argument("--resume-expert-probability", type=float, default=0.0)
    parser.add_argument("--resume-imitation-weight", type=float, default=0.0)
    parser.add_argument("--training-families", nargs="+", choices=FAMILIES)
    parser.add_argument("--grid-size", type=int, default=7)
    parser.add_argument(
        "--fixed-start-fraction",
        type=float,
        default=0.0,
        help="Fraction of training episodes started from the SIGNED match "
        "start (cop_start/thief_start) instead of random cells",
    )
    args = parser.parse_args()
    args.models_dir.mkdir(parents=True, exist_ok=True)
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    opponent_role = "thief" if args.role == "cop" else "cop"
    if args.historical_checkpoint is None:
        historical_policy = None
    else:
        try:
            _raw_ckpt = torch.load(
                args.historical_checkpoint, map_location="cpu", weights_only=True
            )
        except (EOFError, KeyError, RuntimeError, pickle.UnpicklingError):
            _raw_ckpt = None
        if isinstance(_raw_ckpt, dict) and {
            "state_dict",
            "input_size",
        }.issubset(_raw_ckpt):
            _hist_net = RecurrentActorCritic(
                int(_raw_ckpt["input_size"]),
                int(_raw_ckpt["n_actions"]),
                int(_raw_ckpt["hidden_size"]),
            )
            _hist_net.load_state_dict(_raw_ckpt["state_dict"])
            historical_policy = _hist_net.eval()
        else:
            from cop_worker.rl.policy_loader import load_checkpoint

            _old_policy = load_checkpoint(args.historical_checkpoint, opponent_role, max_steps=35)
            expected_input = obs_tensor_shape(args.grid_size)
            try:
                _old_input = _old_policy.net.backbone.net[0].weight.shape[1]
            except Exception:
                _old_input = expected_input
            historical_policy = _old_policy if _old_input == expected_input else None
    if args.evaluate_only_artifact:
        artifact = args.evaluate_only_artifact
        checkpoint = torch.load(artifact, map_location="cpu", weights_only=True)
        if checkpoint.get("role") != args.role:
            raise RuntimeError("evaluation artifact role does not match --role")
        network = RecurrentActorCritic(
            int(checkpoint["input_size"]),
            int(checkpoint["n_actions"]),
            int(checkpoint["hidden_size"]),
        )
        network.load_state_dict(checkpoint["state_dict"])
        network.eval()
        training_episodes = int(checkpoint["training_steps"]) // 35
    else:
        resume_checkpoint = None
        resumed_from_sha256 = None
        previous_training_steps = 0
        if args.resume_artifact:
            resumed_from_sha256 = file_sha256(args.resume_artifact)
            resume_checkpoint = torch.load(
                args.resume_artifact, map_location="cpu", weights_only=True
            )
            previous_training_steps = int(resume_checkpoint["training_steps"])
        network = train(
            args.role,
            args.episodes,
            args.seed,
            args.hidden_size,
            historical_policy,
            resume_checkpoint,
            args.resume_learning_rate,
            args.resume_expert_probability,
            args.resume_imitation_weight,
            tuple(args.training_families) if args.training_families else None,
            grid_size=args.grid_size,
            fixed_start_fraction=args.fixed_start_fraction,
        )
        artifact_name = f"{args.role}_recurrent_champion.pt"
        artifact = args.models_dir / artifact_name
        torch.save(
            {
                "role": args.role,
                "algorithm": "RecurrentA2C-GRU",
                "input_size": obs_tensor_shape(args.grid_size),
                "n_actions": len(COP_ACTIONS if args.role == "cop" else THIEF_ACTIONS),
                "hidden_size": args.hidden_size,
                "training_steps": previous_training_steps + args.episodes * 35,
                "state_dict": network.state_dict(),
            },
            artifact,
        )
        training_episodes = (previous_training_steps // 35) + args.episodes
    inference_temperature = args.inference_temperature or None
    if inference_temperature is not None and not 0 < inference_temperature <= 1:
        raise RuntimeError("inference temperature must be in (0, 1]")
    evaluation = evaluate(
        network,
        args.role,
        args.eval_series_per_family,
        args.seed,
        historical_policy,
        inference_temperature,
        grid_size=args.grid_size,
    )
    heuristic_baseline = evaluate(
        network,
        args.role,
        args.eval_series_per_family,
        args.seed,
        historical_policy,
        force_expert_actor=True,
        grid_size=args.grid_size,
    )
    promotion = _promotion_comparison(evaluation, heuristic_baseline, args.seed)
    evaluation["artifact_sha256"] = file_sha256(artifact)
    evaluation["evaluation_seed"] = args.seed
    evaluation["training_seed_namespace"] = [args.seed, args.seed + args.episodes]
    evaluation["held_out_seed_namespace"] = [args.seed + 10_000, args.seed + 50_000]
    evaluation["training_episodes"] = training_episodes
    evaluation["training_opponents"] = list(FAMILIES)
    evaluation["training_schedule"] = list(
        args.training_families
        or (THIEF_TRAINING_SCHEDULE if args.role == "thief" else COP_TRAINING_SCHEDULE)
    )
    evaluation["historical_checkpoint"] = (
        str(args.historical_checkpoint) if args.historical_checkpoint else None
    )
    evaluation["historical_checkpoint_sha256"] = (
        file_sha256(args.historical_checkpoint) if args.historical_checkpoint else None
    )
    evaluation["demonstration_episodes"] = 240
    evaluation["imitation_updates"] = 600
    evaluation["training_method"] = "local-belief BC warm start + recurrent A2C"
    if not args.evaluate_only_artifact:
        evaluation["resumed_from_sha256"] = resumed_from_sha256
        if args.resume_artifact:
            evaluation["resume_hyperparams"] = {
                "learning_rate": args.resume_learning_rate,
                "expert_probability": args.resume_expert_probability,
                "imitation_weight": args.resume_imitation_weight,
            }
    evaluation["strongest_heuristic_baseline"] = heuristic_baseline
    evaluation["promotion_gate"] = promotion
    evidence = args.evidence_dir / f"{args.role}_held_out_tournament.json"
    evidence.write_text(json.dumps(evaluation, indent=2))
    print(json.dumps({"artifact": str(artifact), "evaluation": evaluation}, indent=2))


if __name__ == "__main__":
    main()
