"""Cover ablations and per-episode metric helpers in episode_steps."""

from __future__ import annotations

import random

import pytest
import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.rl.action_space import COP_ACTIONS
from cop_worker.rl.train_recurrent import _initial_state
from cop_worker.rl.train_recurrent.episode_steps import (
    _ablate_features,
    _note_barrier_metric,
    _note_choice_metrics,
    _note_decision_metrics,
    _step_reward,
)

CELLS = 49


def test_ablate_features_modes():
    base = torch.ones(4 * CELLS + 5)
    full = base.clone()
    _ablate_features(full, "full", CELLS)
    assert torch.equal(full, base)  # no-op

    no_scent = base.clone()
    _ablate_features(no_scent, "no_scent", CELLS)
    assert torch.all(no_scent[2 * CELLS : 3 * CELLS] == 0.0)
    assert no_scent[0] == 1.0

    no_belief = base.clone()
    _ablate_features(no_belief, "no_belief", CELLS)
    assert torch.all(no_belief[3 * CELLS : 4 * CELLS] == 0.0)
    assert torch.all(no_belief[-2:] == 0.0)

    with pytest.raises(RuntimeError, match="unsupported feature ablation"):
        _ablate_features(base.clone(), "bogus", CELLS)


def test_note_metrics_ignore_none():
    # None metrics dict is a fast no-op on every helper.
    _note_choice_metrics(None, ["STAY"], torch.tensor([True]), ("STAY",))
    _note_decision_metrics(None, "STAY", ["STAY"])
    _note_barrier_metric(None, "STAY")


def test_note_choice_and_decision_metrics():
    metrics: dict[str, int] = {}
    actions = ("NORTH", "SOUTH", "STAY")
    legal = ["NORTH", "SOUTH"]
    # SOUTH is legal but pruned by mask -> counts as risk_pruned.
    mask = torch.tensor([True, False, True])
    _note_choice_metrics(metrics, legal, mask, actions)
    assert metrics["legal_candidates"] == 2
    assert metrics["risk_pruned"] == 1

    _note_decision_metrics(metrics, "EAST", legal)  # illegal choice
    assert metrics["decisions"] == 1
    assert metrics["illegal_selected"] == 1


def test_note_barrier_metric_counts_placements():
    metrics: dict[str, int] = {}
    _note_barrier_metric(metrics, "PLACE_NORTH")
    _note_barrier_metric(metrics, "STAY")
    assert metrics["barrier_placements"] == 1


def test_step_reward_terminal_and_ongoing():
    state = _initial_state(random.Random(4), random_start=False)
    belief = BeliefEngine(state.grid_size, "cop")

    terminal, winner, reward = _step_reward("cop", "cop_win", 5, 4, [], state, belief)
    assert terminal is True and winner == "cop" and reward == 8.0

    terminal, winner, reward = _step_reward("thief", "cop_win", 5, 4, [], state, belief)
    assert terminal is True and winner == "cop" and reward == -8.0

    # Ongoing cop step: distance shrank -> positive shaped reward plus trap term.
    terminal, winner, reward = _step_reward(
        "cop", "ongoing", 6, 4, list(state.barriers), state, belief
    )
    assert terminal is False and winner is None
    assert isinstance(reward, float)
    assert COP_ACTIONS  # sanity import guard
