"""Behavioral tests for cop_worker.rl.research_evaluation and research_final_tournament."""

from __future__ import annotations

import json
import random

import pytest
import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.research_evaluation import (
    GameletEnsemblePolicy,
    RecurrentResearchPolicy,
    ScriptedResearchPolicy,
    _terminal_value,
    _wilson,
    evaluate_crossplay,
    load_recurrent_network,
    play_game,
)
from cop_worker.rl.research_evaluation import main as eval_main
from cop_worker.rl.research_final_tournament import load_policy
from cop_worker.rl.train_recurrent import _initial_state
from cop_worker.scent import make_scent_fields

INPUT = 4 * 7 * 7 + 5


def _ckpt(tmp_path, role, algorithm="RecurrentA2C-GRU"):
    n = len(COP_ACTIONS if role == "cop" else THIEF_ACTIONS)
    net = RecurrentActorCritic(INPUT, n, 8)
    path = tmp_path / f"{role}_{algorithm}.pt"
    payload = {
        "role": role,
        "algorithm": algorithm,
        "input_size": INPUT,
        "n_actions": n,
        "hidden_size": 8,
        "training_steps": 1,
        "state_dict": net.state_dict(),
    }
    torch.save(payload, path)
    return path


def test_load_recurrent_network_enforces_schema(tmp_path):
    path = _ckpt(tmp_path, "cop")
    assert isinstance(load_recurrent_network(path, "cop"), RecurrentActorCritic)
    with pytest.raises(ValueError, match="not a thief checkpoint"):
        load_recurrent_network(path, "thief")
    bad = _ckpt(tmp_path, "cop", algorithm="PPO")
    with pytest.raises(ValueError, match="unsupported recurrent algorithm"):
        load_recurrent_network(bad, "cop")


def test_recurrent_policy_argmax_temperature_and_search(tmp_path):
    state = _initial_state(random.Random(2), random_start=False)
    scent = make_scent_fields(7)
    for kwargs in (
        {},
        {"temperature": 0.5},
        {"search_strength": 2.0, "search_depth": 1, "search_particles": 4},
    ):
        policy = RecurrentResearchPolicy(
            load_recurrent_network(_ckpt(tmp_path, "cop"), "cop"), "cop", **kwargs
        )
        policy.reset(9)
        action = policy.act(state, scent, BeliefEngine(7, "cop"), random.Random(3), 1)
        assert action in COP_ACTIONS
    assert policy.actions == COP_ACTIONS


def test_scripted_policy_rejects_historical():
    with pytest.raises(ValueError, match="historical checkpoint"):
        ScriptedResearchPolicy("cop", "historical_checkpoint")


def test_gamelet_ensemble_validation_and_dispatch():
    policies = {g: ScriptedResearchPolicy("thief", "anti_loop") for g in range(1, 7)}
    ensemble = GameletEnsemblePolicy("thief", policies)
    ensemble.reset(5)
    state = _initial_state(random.Random(2), random_start=False)
    action = ensemble.act(
        state, make_scent_fields(7), BeliefEngine(7, "thief"), random.Random(1), 3
    )
    assert action in THIEF_ACTIONS
    with pytest.raises(ValueError, match="gamelets 1..6"):
        GameletEnsemblePolicy("thief", {1: policies[1]})
    wrong_role = {g: ScriptedResearchPolicy("cop", "anti_loop") for g in range(1, 7)}
    with pytest.raises(ValueError, match="match the ensemble role"):
        GameletEnsemblePolicy("thief", wrong_role)


def test_play_game_and_crossplay_metrics():
    cop = ScriptedResearchPolicy("cop", "scent_following")
    thief = ScriptedResearchPolicy("thief", "anti_loop")
    result = play_game(cop, thief, seed=42, random_start=False, gamelet=1)
    assert result.winner in ("cop", "thief") and 0 < result.turns <= 35
    report = evaluate_crossplay(cop, thief, series=1, seed=100, random_start=False)
    assert report["games"] == 6
    assert 0.0 <= report["cop"]["win_rate"] <= 1.0
    assert report["cop"]["confidence_95"][0] <= report["cop"]["confidence_95"][1]


def test_helper_values():
    assert _wilson(0, 0) == [0.0, 0.0]
    assert _terminal_value("cop_win", "cop", 10) > 0 > _terminal_value("cop_win", "thief", 10)
    with pytest.raises(ValueError, match="ongoing"):
        _terminal_value("ongoing", "cop", 1)


def test_evaluation_main_cli(tmp_path, monkeypatch, capsys):
    cop_path = _ckpt(tmp_path, "cop")
    thief_path = _ckpt(tmp_path, "thief")
    out = tmp_path / "report" / "crossplay.json"
    argv = [
        "research_evaluation",
        "--cop",
        str(cop_path),
        "--thief",
        str(thief_path),
        "--series",
        "1",
        "--seed",
        "5",
        "--output",
        str(out),
    ]
    monkeypatch.setattr("sys.argv", argv)
    eval_main()
    payload = json.loads(out.read_text())
    assert payload["crossplay"]["games"] == 6
    assert len(payload["cop_sha256"]) == 64
    assert "crossplay" in capsys.readouterr().out


def test_final_tournament_load_policy(tmp_path):
    recurrent = _ckpt(tmp_path, "cop")
    assert isinstance(load_policy(f"recurrent:{recurrent}", "cop"), RecurrentResearchPolicy)
    scripted = load_policy("scripted:anti_loop", "thief")
    assert isinstance(scripted, ScriptedResearchPolicy) and scripted.family == "anti_loop"
    with pytest.raises(ValueError, match="unsupported policy specification"):
        load_policy("hologram:foo", "cop")
