"""Behavioral tests for cop_worker.rl.research_distillation (tiny nets, no GPU)."""

from __future__ import annotations

import pytest
import torch

from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.research_distillation import (
    _new_scent_decoder,
    _population,
    collect_teacher_sequences,
    train_sequence_distillation,
)
from cop_worker.rl.research_evaluation import (
    RecurrentResearchPolicy,
    ScriptedResearchPolicy,
    load_recurrent_network,
)

INPUT = 4 * 7 * 7 + 5


def _ckpt(tmp_path, role):
    n = len(COP_ACTIONS if role == "cop" else THIEF_ACTIONS)
    net = RecurrentActorCritic(INPUT, n, 8)
    path = tmp_path / f"{role}.pt"
    payload = {
        "role": role,
        "algorithm": "RecurrentA2C-GRU",
        "input_size": INPUT,
        "n_actions": n,
        "hidden_size": 8,
        "training_steps": 1,
        "state_dict": net.state_dict(),
    }
    torch.save(payload, path)
    return path


def test_population_composition(tmp_path):
    cop_opponents = _population("cop", _ckpt(tmp_path, "thief"))
    assert len(cop_opponents) == 12
    assert all(policy.role == "thief" for policy in cop_opponents)
    thief_opponents = _population("thief", _ckpt(tmp_path, "cop"))
    assert len(thief_opponents) == 7
    assert all(policy.role == "cop" for policy in thief_opponents)
    assert isinstance(thief_opponents[3], RecurrentResearchPolicy)
    assert isinstance(thief_opponents[0], ScriptedResearchPolicy)


def test_collect_teacher_sequences_shapes(tmp_path):
    incumbent = _ckpt(tmp_path, "cop")
    teachers = tuple(ScriptedResearchPolicy("thief", "anti_loop") for _ in range(7))
    sequences = collect_teacher_sequences(
        teachers, "thief", incumbent, episodes=2, seed=13, random_start_fraction=0.0
    )
    assert len(sequences) == 2
    features, labels = sequences[0]
    assert features.shape[1] == INPUT and features.shape[0] == labels.shape[0]
    assert labels.dtype == torch.int64
    assert int(labels.max()) < len(THIEF_ACTIONS)


def test_collect_uses_random_start_teacher(tmp_path):
    incumbent = _ckpt(tmp_path, "cop")
    teachers = tuple(ScriptedResearchPolicy("thief", "anti_loop") for _ in range(7))
    fallback = RecurrentResearchPolicy(
        load_recurrent_network(_ckpt(tmp_path, "thief"), "thief"), "thief", temperature=0.5
    )
    sequences = collect_teacher_sequences(
        teachers,
        "thief",
        incumbent,
        episodes=1,
        seed=3,
        random_start_fraction=1.0,
        random_start_teacher=fallback,
    )
    assert len(sequences) == 1 and sequences[0][0].shape[0] > 0


def test_collect_rejects_population_mismatch(tmp_path):
    incumbent = _ckpt(tmp_path, "cop")
    teachers = (ScriptedResearchPolicy("thief", "anti_loop"),)
    with pytest.raises(ValueError, match="must align"):
        collect_teacher_sequences(
            teachers, "thief", incumbent, episodes=1, seed=1, random_start_fraction=0.0
        )


def test_train_sequence_distillation_learns_batch(tmp_path):
    incumbent = _ckpt(tmp_path, "cop")
    teachers = tuple(ScriptedResearchPolicy("thief", "anti_loop") for _ in range(7))
    sequences = collect_teacher_sequences(
        teachers, "thief", incumbent, episodes=2, seed=21, random_start_fraction=0.0
    )
    network = RecurrentActorCritic(INPUT, len(THIEF_ACTIONS), 8)
    metrics = train_sequence_distillation(network, sequences, updates=2, seed=5, learning_rate=1e-3)
    assert metrics["updates"] == 2 and metrics["sequences"] == 2
    assert 0.0 <= metrics["mean_accuracy_last_50"] <= 1.0
    assert metrics["examples"] == sum(len(f) for f, _l in sequences)


def test_new_scent_decoder_env_switch(monkeypatch):
    monkeypatch.delenv("COPTHIEF_DECODED_SCENT", raising=False)
    assert _new_scent_decoder(7) is None
    monkeypatch.setenv("COPTHIEF_DECODED_SCENT", "1")
    decoder = _new_scent_decoder(7)
    assert decoder is not None and decoder.n == 7
