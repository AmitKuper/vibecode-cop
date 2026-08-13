"""Cover the teacher-selection branches of the distillation CLI main()."""

from __future__ import annotations

import json

import pytest
import torch

from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.research_distillation import cli

INPUT = 4 * 7 * 7 + 5


def _ckpt(tmp_path, role):
    n = len(COP_ACTIONS if role == "cop" else THIEF_ACTIONS)
    net = RecurrentActorCritic(INPUT, n, 8)
    path = tmp_path / f"{role}.pt"
    torch.save(
        {
            "role": role,
            "algorithm": "RecurrentA2C-GRU",
            "input_size": INPUT,
            "n_actions": n,
            "hidden_size": 8,
            "training_steps": 1,
            "state_dict": net.state_dict(),
        },
        path,
    )
    return path


def _patch_heavy(monkeypatch):
    seqs = [(torch.zeros(3, INPUT), torch.zeros(3, dtype=torch.int64))]
    monkeypatch.setattr(cli, "collect_teacher_sequences", lambda *a, **kw: seqs)
    monkeypatch.setattr(cli, "train_sequence_distillation", lambda *a, **kw: {"updates": 2})
    monkeypatch.setattr(cli, "evaluate_crossplay", lambda *a, **kw: {"games": 0})
    monkeypatch.setattr(cli, "evaluate_families", lambda *a, **kw: {"role": "cop"})


def _argv(tmp_path, role, teacher, base, incumbent, extra=()):
    return [
        "prog",
        "--role",
        role,
        "--teacher",
        teacher,
        "--base",
        str(base),
        "--incumbent-opponent",
        str(incumbent),
        "--episodes",
        "1",
        "--updates",
        "1",
        "--output",
        str(tmp_path / "out.pt"),
        "--metrics",
        str(tmp_path / "metrics.json"),
        *extra,
    ]


def _run(monkeypatch, argv):
    monkeypatch.setattr("sys.argv", argv)
    cli.main()


def test_anti_loop_teacher_thief(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    base, incumbent = _ckpt(tmp_path, "thief"), _ckpt(tmp_path, "cop")
    _run(monkeypatch, _argv(tmp_path, "thief", "anti_loop", base, incumbent))
    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert metrics["teacher"] == "anti_loop" and metrics["role"] == "thief"
    assert (tmp_path / "out.pt").exists()


def test_population_oracle_cop(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    base, incumbent = _ckpt(tmp_path, "cop"), _ckpt(tmp_path, "thief")
    _run(monkeypatch, _argv(tmp_path, "cop", "population_oracle", base, incumbent))
    assert json.loads((tmp_path / "metrics.json").read_text())["teacher"] == "population_oracle"


def test_search_hybrid_teacher(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    base, incumbent = _ckpt(tmp_path, "thief"), _ckpt(tmp_path, "cop")
    _run(monkeypatch, _argv(tmp_path, "thief", "search_hybrid", base, incumbent))
    assert (tmp_path / "out.pt").exists()


def test_population_oracle_rejects_thief(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    base, incumbent = _ckpt(tmp_path, "thief"), _ckpt(tmp_path, "cop")
    with pytest.raises(ValueError, match="only for cop"):
        _run(monkeypatch, _argv(tmp_path, "thief", "population_oracle", base, incumbent))


def test_ddqn_teacher_with_artifact(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    monkeypatch.setattr(cli, "load_dqn_policy", lambda artifact, role: object())
    base, incumbent = _ckpt(tmp_path, "thief"), _ckpt(tmp_path, "cop")
    artifact = tmp_path / "teacher_dqn.pt"
    artifact.write_bytes(b"x")
    _run(
        monkeypatch,
        _argv(
            tmp_path,
            "thief",
            "ddqn",
            base,
            incumbent,
            extra=["--teacher-artifact", str(artifact)],
        ),
    )
    assert (tmp_path / "out.pt").exists()
