"""Collect teacher action sequences for distillation."""

from __future__ import annotations

import random
from pathlib import Path

import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.transition import apply_joint_action
from cop_worker.rl.research_distillation.population import (
    _actions,
    _new_scent_decoder,
    _population,
)
from cop_worker.rl.research_evaluation import (
    ResearchPolicy,
)
from cop_worker.rl.train_recurrent import _initial_state, _legal, _observation
from cop_worker.scent import make_scent_fields


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
            teacher_action = teacher.act(state, scent, belief, rng, gamelet)
            episode_features.append(features)
            episode_labels.append(actions.index(teacher_action))
            opponent_belief = thief_belief if role == "cop" else cop_belief
            opponent_action = opponent.act(state, scent, opponent_belief, rng, gamelet)
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
