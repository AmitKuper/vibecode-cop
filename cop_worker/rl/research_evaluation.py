"""Reproducible local-information tournaments for RL research.

This module is deliberately outside the counted protocol path.  It uses the
canonical :func:`apply_joint_action` transition and the deployed observation
adapter, but it never sends a ``DomainState`` to a policy.  The additional
fixed-start suite mirrors ``config/game.json``; the historical trainer's suite
randomises starts and is retained as a robustness test.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.domain.types import DomainState
from cop_worker.rl.action_space import (
    COP_ACTIONS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)
from cop_worker.rl.recurrent_policy import RecurrentActorCritic, file_sha256
from cop_worker.rl.train_recurrent import FAMILIES, _initial_state, _legal, _observation
from cop_worker.scent import ScentFields, make_scent_fields


class ResearchPolicy(Protocol):
    """A policy receiving only role-local observation state."""

    role: str

    def reset(self, seed: int) -> None: ...

    def act(
        self,
        state: DomainState,
        scent: ScentFields,
        belief: BeliefEngine,
        rng: random.Random,
        gamelet: int,
    ) -> str: ...


def load_recurrent_network(path: str | Path, expected_role: str) -> RecurrentActorCritic:
    """Load a recurrent artifact directly and enforce its embedded schema."""
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if checkpoint.get("role") != expected_role:
        raise ValueError(f"{path} is not a {expected_role} checkpoint")
    if checkpoint.get("algorithm") != "RecurrentA2C-GRU":
        raise ValueError(f"unsupported recurrent algorithm in {path}")
    network = RecurrentActorCritic(
        int(checkpoint["input_size"]),
        int(checkpoint["n_actions"]),
        int(checkpoint["hidden_size"]),
    )
    network.load_state_dict(checkpoint["state_dict"])
    return network.eval()


class RecurrentResearchPolicy:
    """Stateful checkpoint inference with optional belief-search logit guidance."""

    def __init__(
        self,
        network: RecurrentActorCritic,
        role: str,
        temperature: float | None = None,
        search_strength: float = 0.0,
        search_depth: int = 1,
        search_particles: int = 8,
    ) -> None:
        self.network = network.eval()
        self.role = role
        self.temperature = temperature
        self.search_strength = float(search_strength)
        self.search_depth = int(search_depth)
        self.search_particles = int(search_particles)
        self.hidden: torch.Tensor | None = None
        self.generator = torch.Generator(device="cpu")
        # Per-episode inverse of the clamped wire scent law; inert unless
        # COPTHIEF_DECODED_SCENT=1. Rebuilt on reset() so no state leaks between games.
        self._decoder = None

    def reset(self, seed: int) -> None:
        self.hidden = None
        self.generator.manual_seed(seed)
        if self._decoder is not None:
            self._decoder.reset()

    def _scent_decoder(self, grid_size: int):
        from cop_worker.rl.obs_mode import decoded_scent_enabled
        from cop_worker.scent_decoder import EmitterDecoder

        if not decoded_scent_enabled():
            return None
        if self._decoder is None or self._decoder.n != grid_size:
            self._decoder = EmitterDecoder(grid_size)
        return self._decoder

    def act(
        self,
        state: DomainState,
        scent: ScentFields,
        belief: BeliefEngine,
        rng: random.Random,
        gamelet: int,
    ) -> str:
        legal = _legal(state, self.role)
        features, mask = _observation(
            state,
            self.role,
            scent,
            belief,
            legal,
            gamelet,
            decoder=self._scent_decoder(state.grid_size),
        )
        with torch.no_grad():
            logits, _value, self.hidden = self.network(features.unsqueeze(0), self.hidden)
        masked = logits.squeeze(0).masked_fill(~mask, -1e9)
        if self.search_strength:
            search = belief_search_scores(
                state,
                self.role,
                belief,
                legal,
                depth=self.search_depth,
                max_particles=self.search_particles,
            )
            search_tensor = torch.tensor(
                [search.get(action, -1e6) for action in self.actions], dtype=masked.dtype
            )
            finite = search_tensor > -1e5
            if bool(finite.any()):
                values = search_tensor[finite]
                scale = values.std(unbiased=False).clamp_min(0.25)
                search_tensor[finite] = (values - values.mean()) / scale
                masked = masked + self.search_strength * search_tensor
        if self.temperature is None:
            index = int(masked.argmax().item())
        else:
            probabilities = torch.softmax(masked / self.temperature, dim=-1)
            index = int(torch.multinomial(probabilities, 1, generator=self.generator).item())
        return self.actions[index]

    @property
    def actions(self) -> list[str]:
        return COP_ACTIONS if self.role == "cop" else THIEF_ACTIONS


class ScriptedResearchPolicy:
    """Adapter for the existing local-belief opponent families."""

    def __init__(self, role: str, family: str) -> None:
        if family == "historical_checkpoint":
            raise ValueError("historical checkpoint needs a real recurrent policy")
        self.role = role
        self.family = family

    def reset(self, seed: int) -> None:
        del seed

    def act(
        self,
        state: DomainState,
        scent: ScentFields,
        belief: BeliefEngine,
        rng: random.Random,
        gamelet: int,
    ) -> str:
        del gamelet
        from cop_worker.rl.train_recurrent import _opponent_action

        observed_scent = (
            scent.cop_observation_scent() if self.role == "cop" else scent.thief_observation_scent()
        )
        return _opponent_action(
            state,
            self.role,
            self.family,
            rng,
            opponent_scent=observed_scent,
            opponent_belief=belief,
        )


class GameletEnsemblePolicy:
    """Select a local policy by the public gamelet number."""

    def __init__(self, role: str, policies: dict[int, ResearchPolicy]) -> None:
        if set(policies) != set(range(1, 7)):
            raise ValueError("gamelet ensemble requires policies for gamelets 1..6")
        if any(policy.role != role for policy in policies.values()):
            raise ValueError("all gamelet policies must match the ensemble role")
        self.role = role
        self.policies = policies

    def reset(self, seed: int) -> None:
        for gamelet, policy in self.policies.items():
            policy.reset(seed + gamelet * 10_007)

    def act(
        self,
        state: DomainState,
        scent: ScentFields,
        belief: BeliefEngine,
        rng: random.Random,
        gamelet: int,
    ) -> str:
        return self.policies[gamelet].act(state, scent, belief, rng, gamelet)


class LegacyResearchPolicy:
    """Evaluate checked-in feed-forward PPO/DQN checkpoints on local scent."""

    def __init__(self, artifact: str | Path, role: str) -> None:
        from cop_worker.rl.policy_loader import load_checkpoint

        self.policy = load_checkpoint(Path(artifact), role, max_steps=35)
        self.role = role

    def reset(self, seed: int) -> None:
        torch.manual_seed(seed)
        self.policy.barriers_remaining = self.policy.barrier_quota

    def act(
        self,
        state: DomainState,
        scent: ScentFields,
        belief: BeliefEngine,
        rng: random.Random,
        gamelet: int,
    ) -> str:
        del belief, rng, gamelet
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
        if self.role == "cop":
            rules._scent_grid = scent.cop_observation_scent()
            observation = self.policy._build_obs(board, rules)
        else:
            observation = self.policy._build_obs(
                board,
                rules,
                cop_scent_field=scent.thief_observation_scent(),
            )
        tensor = torch.tensor(observation, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            output = self.policy.net(tensor)
            logits = output[0] if isinstance(output, tuple) else output
        actions = COP_ACTIONS if logits.shape[-1] == len(COP_ACTIONS) else THIEF_ACTIONS
        legal = _legal(state, self.role)
        mask = torch.tensor([action in legal for action in actions], dtype=torch.bool)
        index = int(logits.squeeze(0).masked_fill(~mask, -1e9).argmax().item())
        return actions[index]


def _hypothetical_state(
    state: DomainState, role: str, opponent_position: tuple[int, int]
) -> DomainState:
    field = "thief_position" if role == "cop" else "cop_position"
    return state.model_copy(update={field: opponent_position})


def _leaf_value(state: DomainState, role: str) -> float:
    """Bounded perfect-information leaf value used only inside belief particles."""
    distance = abs(state.cop_position[0] - state.thief_position[0]) + abs(
        state.cop_position[1] - state.thief_position[1]
    )
    barriers = set(state.barriers)
    tx, ty = state.thief_position
    exits = sum(
        0 <= tx + dx < state.grid_size
        and 0 <= ty + dy < state.grid_size
        and (tx + dx, ty + dy) not in barriers
        for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0))
    )
    time_fraction = state.turn / 35.0
    cop_value = (
        -0.30 * distance
        + 0.55 * (4 - exits)
        + 0.08 * state.cop_barriers_remaining
        - 0.80 * time_fraction
    )
    return cop_value if role == "cop" else -cop_value


def _terminal_value(outcome: str, role: str, turn: int) -> float:
    if outcome == "ongoing":
        raise ValueError("terminal value requested for ongoing state")
    winner = "cop" if outcome == "cop_win" else "thief"
    speed = (35 - min(turn, 35)) / 35.0
    return (12.0 + speed) if winner == role else (-12.0 - speed)


def _fast_legal(state: DomainState, role: str) -> list[str]:
    """Equivalent local legality calculation for inner search nodes."""
    barriers = [tuple(item) for item in state.barriers]
    if role == "cop":
        actions = COP_ACTIONS
        mask = compute_legal_mask_cop(
            state.cop_position,
            barriers,
            state.cop_barriers_remaining,
            state.grid_size,
        )
    else:
        actions = THIEF_ACTIONS
        mask = compute_legal_mask_thief(state.thief_position, barriers, state.grid_size)
    return [action for action, allowed in zip(actions, mask, strict=True) if allowed]


def _determinized_value(state: DomainState, role: str, depth: int) -> float:
    """Small simultaneous expectiminimax search inside one belief particle."""
    if depth <= 0:
        return _leaf_value(state, role)
    own_actions = _fast_legal(state, role)
    opponent_role = "thief" if role == "cop" else "cop"
    opponent_actions = _fast_legal(state, opponent_role)
    best = -math.inf
    for own in own_actions:
        worst = math.inf
        for opponent in opponent_actions:
            cop_action, thief_action = (own, opponent) if role == "cop" else (opponent, own)
            result = apply_joint_action(state, cop_action, thief_action)
            outcome = result.outcome.value
            value = (
                _terminal_value(outcome, role, result.new_state.turn)
                if outcome != "ongoing"
                else _determinized_value(result.new_state, role, depth - 1)
            )
            worst = min(worst, value)
        best = max(best, worst)
    return best


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cop", type=Path, required=True)
    parser.add_argument("--thief", type=Path, required=True)
    parser.add_argument("--series", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260809)
    parser.add_argument("--random-start", action="store_true")
    parser.add_argument("--cop-search-strength", type=float, default=0.0)
    parser.add_argument("--thief-search-strength", type=float, default=0.0)
    parser.add_argument("--search-depth", type=int, choices=(1, 2), default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cop = RecurrentResearchPolicy(
        load_recurrent_network(args.cop, "cop"),
        "cop",
        search_strength=args.cop_search_strength,
        search_depth=args.search_depth,
    )
    thief = RecurrentResearchPolicy(
        load_recurrent_network(args.thief, "thief"),
        "thief",
        temperature=0.5,
        search_strength=args.thief_search_strength,
        search_depth=args.search_depth,
    )
    result = {
        "seed": args.seed,
        "cop_artifact": str(args.cop),
        "cop_sha256": file_sha256(args.cop),
        "thief_artifact": str(args.thief),
        "thief_sha256": file_sha256(args.thief),
        "crossplay": evaluate_crossplay(cop, thief, args.series, args.seed, args.random_start),
    }
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered)


if __name__ == "__main__":
    main()
