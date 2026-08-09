"""Distil strong local-information teachers into deployable recurrent artifacts."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F  # noqa: N812

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.recurrent_policy import RecurrentActorCritic, file_sha256
from cop_worker.rl.research_evaluation import (
    RecurrentResearchPolicy,
    ResearchPolicy,
    ScriptedResearchPolicy,
    evaluate_crossplay,
    evaluate_families,
    load_recurrent_network,
)
from cop_worker.rl.research_value_training import load_dqn_policy
from cop_worker.rl.train_recurrent import _initial_state, _legal, _observation
from cop_worker.scent import make_scent_fields


def _new_scent_decoder(grid_size: int):
    """Fresh wire-scent inverse for one episode, or None when the switch is off."""
    from cop_worker.rl.obs_mode import decoded_scent_enabled
    from cop_worker.scent_decoder import EmitterDecoder

    return EmitterDecoder(grid_size) if decoded_scent_enabled() else None


def _actions(role: str) -> list[str]:
    return COP_ACTIONS if role == "cop" else THIEF_ACTIONS


def _population(role: str, incumbent_opponent: Path) -> tuple[ResearchPolicy, ...]:
    opponent_role = "thief" if role == "cop" else "cop"
    historical = RecurrentResearchPolicy(
        load_recurrent_network(incumbent_opponent, opponent_role),
        opponent_role,
        temperature=0.5 if opponent_role == "thief" else None,
    )
    if role == "cop":
        return (
            historical,
            historical,
            historical,
            historical,
            ScriptedResearchPolicy("thief", "anti_loop"),
            ScriptedResearchPolicy("thief", "targeted_exploit"),
            ScriptedResearchPolicy("thief", "scent_following"),
            ScriptedResearchPolicy("thief", "local_adversarial_ensemble"),
            ScriptedResearchPolicy("thief", "wall"),
            ScriptedResearchPolicy("thief", "random"),
            ScriptedResearchPolicy("thief", "corridor_cutting"),
            ScriptedResearchPolicy("thief", "deceptive_language"),
        )
    return (
        ScriptedResearchPolicy("cop", "anti_loop"),
        ScriptedResearchPolicy("cop", "anti_loop"),
        ScriptedResearchPolicy("cop", "anti_loop"),
        historical,
        historical,
        ScriptedResearchPolicy("cop", "scent_following"),
        ScriptedResearchPolicy("cop", "corridor_cutting"),
    )


def collect_teacher_sequences(
    teachers: tuple[ResearchPolicy, ...],
    role: str,
    incumbent_opponent: Path,
    episodes: int,
    seed: int,
    random_start_fraction: float,
    random_start_teacher: ResearchPolicy | None = None,
) -> list[tuple[torch.Tensor, torch.Tensor]]:
    """Collect legal local observations and teacher actions as full episodes.

    The student's observation goes through the same decoded-scent transform production uses,
    so behaviour cloning is learned on the channels it will actually be served. The TEACHER
    keeps its privileged view -- that asymmetry is the point of distillation.
    """
    rng = random.Random(seed)
    actions = _actions(role)
    opponents = _population(role, incumbent_opponent)
    if len(teachers) != len(opponents):
        raise ValueError("teacher and opponent populations must align")
    sequences: list[tuple[torch.Tensor, torch.Tensor]] = []
    for episode in range(episodes):
        opponent = opponents[episode % len(opponents)]
        teacher = teachers[episode % len(teachers)]
        random_start = rng.random() < random_start_fraction
        if random_start and random_start_teacher is not None:
            teacher = random_start_teacher
        gamelet = (episode % 6) + 1
        state = _initial_state(rng, random_start=random_start, grid_size=7)
        scent = make_scent_fields(7)
        cop_belief = BeliefEngine(7, "cop")
        thief_belief = BeliefEngine(7, "thief")
        teacher.reset(seed + episode * 101 + 1)
        opponent.reset(seed + episode * 101 + 2)
        # One decoder per episode: it differences consecutive scent frames, so leaking state
        # across episodes would corrupt the first steps of the next game.
        decoder = _new_scent_decoder(7)
        episode_features: list[torch.Tensor] = []
        episode_labels: list[int] = []
        while state.turn < 35:
            belief = cop_belief if role == "cop" else thief_belief
            legal = _legal(state, role)
            features, _mask = _observation(
                state, role, scent, belief, legal, gamelet, decoder=decoder
            )
            teacher_action = teacher.act(
                state, scent, belief, rng, gamelet
            )
            episode_features.append(features)
            episode_labels.append(actions.index(teacher_action))
            opponent_belief = thief_belief if role == "cop" else cop_belief
            opponent_action = opponent.act(
                state, scent, opponent_belief, rng, gamelet
            )
            cop_action, thief_action = (
                (teacher_action, opponent_action)
                if role == "cop"
                else (opponent_action, teacher_action)
            )
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
                break
        sequences.append((torch.stack(episode_features), torch.tensor(episode_labels)))
    return sequences


def train_sequence_distillation(
    network: RecurrentActorCritic,
    sequences: list[tuple[torch.Tensor, torch.Tensor]],
    updates: int,
    seed: int,
    learning_rate: float,
) -> dict:
    """Truncated full-episode BPTT behaviour cloning."""
    rng = random.Random(seed)
    optimizer = torch.optim.Adam(network.parameters(), lr=learning_rate)
    batch_size = min(32, len(sequences))
    losses: list[float] = []
    accuracies: list[float] = []
    network.train()
    for _update in range(updates):
        batch = rng.sample(sequences, batch_size)
        max_length = max(len(features) for features, _labels in batch)
        hidden: torch.Tensor | None = None
        step_losses: list[torch.Tensor] = []
        correct = examples = 0
        for step in range(max_length):
            active = [
                index
                for index, (features, _labels) in enumerate(batch)
                if step < len(features)
            ]
            if not active:
                continue
            # GRU state is maintained for the full padded batch.  Inactive rows
            # receive zeros and are ignored by the loss.
            input_size = batch[0][0].shape[1]
            inputs = torch.zeros((batch_size, input_size), dtype=torch.float32)
            labels = torch.zeros(batch_size, dtype=torch.long)
            active_mask = torch.zeros(batch_size, dtype=torch.bool)
            for index in active:
                features, target = batch[index]
                inputs[index] = features[step]
                labels[index] = target[step]
                active_mask[index] = True
            logits, _values, hidden = network(inputs, hidden)
            active_logits = logits[active_mask]
            active_labels = labels[active_mask]
            step_losses.append(F.cross_entropy(active_logits, active_labels))
            correct += int((active_logits.argmax(dim=1) == active_labels).sum().item())
            examples += len(active_labels)
        loss = torch.stack(step_losses).mean()
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(network.parameters(), 0.5)
        optimizer.step()
        losses.append(float(loss.item()))
        accuracies.append(correct / examples)
    network.eval()
    return {
        "mean_loss_last_50": float(np.mean(losses[-50:])),
        "mean_accuracy_last_50": float(np.mean(accuracies[-50:])),
        "updates": updates,
        "sequences": len(sequences),
        "examples": sum(len(features) for features, _labels in sequences),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("cop", "thief"), required=True)
    parser.add_argument(
        "--teacher",
        choices=("anti_loop", "search_hybrid", "population_oracle", "ddqn"),
        required=True,
    )
    parser.add_argument("--teacher-artifact", type=Path)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--incumbent-opponent", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=1_000)
    parser.add_argument("--updates", type=int, default=300)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--random-start-fraction", type=float, default=0.2)
    parser.add_argument("--preserve-random-base", action="store_true")
    parser.add_argument("--seed", type=int, default=20260809)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    args = parser.parse_args()
    base_checkpoint = torch.load(args.base, map_location="cpu", weights_only=True)
    network = load_recurrent_network(args.base, args.role)
    opponents = _population(args.role, args.incumbent_opponent)
    if args.teacher == "anti_loop":
        teachers: tuple[ResearchPolicy, ...] = tuple(
            ScriptedResearchPolicy(args.role, "anti_loop") for _ in opponents
        )
    elif args.teacher == "search_hybrid":
        teachers = tuple(
            RecurrentResearchPolicy(
                load_recurrent_network(args.base, args.role),
                args.role,
                temperature=0.5 if args.role == "thief" else None,
                search_strength=3.0,
                search_depth=1,
                search_particles=4,
            )
            for _ in opponents
        )
    elif args.teacher == "ddqn":
        if args.teacher_artifact is None:
            raise ValueError("--teacher-artifact is required for DDQN distillation")
        teachers = tuple(
            load_dqn_policy(args.teacher_artifact, args.role) for _ in opponents
        )
    elif args.role == "cop":
        oracle_names = (
            "anti_loop",
            "anti_loop",
            "anti_loop",
            "anti_loop",
            "scent_following",
            "targeted_exploit",
            "targeted_exploit",
            "scent_following",
            "wall",
            "local_adversarial_ensemble",
            "targeted_exploit",
            "anti_loop",
        )
        teachers = tuple(
            ScriptedResearchPolicy(args.role, name) for name in oracle_names
        )
    else:
        raise ValueError("population_oracle is currently defined only for cop")
    sequences = collect_teacher_sequences(
        teachers,
        args.role,
        args.incumbent_opponent,
        args.episodes,
        args.seed,
        args.random_start_fraction,
        RecurrentResearchPolicy(
            load_recurrent_network(args.base, args.role),
            args.role,
            temperature=0.5 if args.role == "thief" else None,
        )
        if args.preserve_random_base
        else None,
    )
    metrics = train_sequence_distillation(
        network,
        sequences,
        args.updates,
        args.seed + 1_000_000,
        args.learning_rate,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "role": args.role,
            "algorithm": "RecurrentA2C-GRU",
            "input_size": int(base_checkpoint["input_size"]),
            "n_actions": int(base_checkpoint["n_actions"]),
            "hidden_size": int(base_checkpoint["hidden_size"]),
            "training_steps": int(base_checkpoint["training_steps"])
            + sum(len(features) for features, _labels in sequences),
            "state_dict": network.state_dict(),
            "research_method": f"sequence distillation from {args.teacher}",
        },
        args.output,
    )
    opponent_role = "thief" if args.role == "cop" else "cop"
    incumbent_opponent = RecurrentResearchPolicy(
        load_recurrent_network(args.incumbent_opponent, opponent_role),
        opponent_role,
        temperature=0.5 if opponent_role == "thief" else None,
    )
    candidate = RecurrentResearchPolicy(
        network,
        args.role,
        temperature=0.5 if args.role == "thief" else None,
    )
    cop, thief = (
        (candidate, incumbent_opponent)
        if args.role == "cop"
        else (incumbent_opponent, candidate)
    )
    metrics.update(
        {
            "role": args.role,
            "teacher": args.teacher,
            "base_sha256": file_sha256(args.base),
            "artifact_sha256": file_sha256(args.output),
            "fixed_start_crossplay": evaluate_crossplay(
                cop, thief, 20, args.seed + 2_000_000, False
            ),
            "random_start_crossplay": evaluate_crossplay(
                cop, thief, 20, args.seed + 3_000_000, True
            ),
            "fixed_start_families": evaluate_families(
                candidate,
                args.role,
                incumbent_opponent,
                2,
                args.seed + 4_000_000,
                False,
            ),
        }
    )
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
