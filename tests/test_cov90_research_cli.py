"""Coverage of the research CLI mains and tournament wrappers (offline, fakes)."""

from __future__ import annotations

import json

import pytest


def test_value_training_cli_ddqn_and_qtable(monkeypatch, tmp_path):
    from cop_worker.rl.research_value_training import cli

    calls = {}

    def fake_ddqn(role, episodes, seed, incumbent_path, output, **kw):
        calls["ddqn"] = (role, episodes)
        output.write_bytes(b"x")
        return object(), {"algorithm": "DuelingDoubleDQN", "role": role}

    def fake_qtable(role, episodes, seed, incumbent_path, output, **kw):
        calls["qtable"] = (role, episodes)
        output.write_bytes(b"x")
        return object(), {"algorithm": "TabularQ", "role": role}

    monkeypatch.setattr(cli, "train_ddqn", fake_ddqn)
    monkeypatch.setattr(cli, "train_q_table", fake_qtable)
    monkeypatch.setattr(cli, "evaluate_crossplay", lambda *a, **kw: {"games": 0})
    monkeypatch.setattr(cli, "evaluate_families", lambda *a, **kw: {"role": "cop"})
    monkeypatch.setattr(cli, "load_dqn_policy", lambda *a: object())
    import torch

    torch.save({"algorithm": "DuelingDoubleDQN"}, tmp_path / "inc.pt")
    out, metrics = tmp_path / "o.pt", tmp_path / "m.json"
    for algo in ("ddqn", "qtable"):
        monkeypatch.setattr(
            "sys.argv",
            [
                "prog",
                "--algorithm",
                algo,
                "--role",
                "cop",
                "--episodes",
                "1",
                "--incumbent-opponent",
                str(tmp_path / "inc.pt"),
                "--output",
                str(out),
                "--metrics",
                str(metrics),
            ],
        )
        cli.main()
        assert json.loads(metrics.read_text())["role"] == "cop"
    assert "ddqn" in calls and "qtable" in calls


def test_tournaments_run_tiny_scripted_matchup():
    from cop_worker.rl.research_evaluation import (
        ScriptedResearchPolicy,
        evaluate_crossplay,
        evaluate_families,
    )

    cop = ScriptedResearchPolicy("cop", "belief_pursuit_evasion")
    thief = ScriptedResearchPolicy("thief", "belief_pursuit_evasion")
    cross = evaluate_crossplay(cop, thief, series=1, seed=7, random_start=False)
    assert cross["games"] == 6 and "cop" in cross and "thief" in cross
    fam = evaluate_families(cop, "cop", thief, series_per_family=1, seed=7, random_start=False)
    assert fam["role"] == "cop" and fam["held_out_series"] > 0


def test_distillation_cli_rejects_missing_teacher_artifact(monkeypatch, tmp_path):
    from cop_worker.rl.research_distillation import cli

    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--role",
            "thief",
            "--teacher",
            "ddqn",
            "--base",
            str(tmp_path / "missing.pt"),
            "--incumbent-opponent",
            str(tmp_path / "inc.pt"),
            "--output",
            str(tmp_path / "o.pt"),
            "--metrics",
            str(tmp_path / "m.json"),
        ],
    )
    with pytest.raises(Exception):
        cli.main()
